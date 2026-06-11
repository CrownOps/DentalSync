"""GET /api/orders — 검토 큐 목록 테스트.

needs_review / ocr_failed 필터, min_score 오름차순 정렬 검증.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_settings_dep, get_storage
from app.core.config import Settings
from app.db.base import Base
from app.db.models import Lab, Order, OrderField
from app.domain.enums import FieldStatus, FieldType, OrderStatus
from app.main import app


class _FakeStorage:
    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        pass

    def get_object(self, key: str) -> bytes:
        return b""

    def delete_object(self, key: str) -> None:
        pass

    def generate_presigned_url(self, key: str, expires: int = 300) -> str:
        return f"https://fake-r2/{key}?expires={expires}"


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        s.add(Lab(name="테스트기공소"))
        s.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    storage = _FakeStorage()
    settings = Settings(blur_laplacian_min=5.0, min_image_width=200, min_image_height=200)

    def _db() -> Iterator[Session]:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_settings_dep] = lambda: settings
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _make_order(
    session: Session,
    status: OrderStatus,
    scores: list[float],
    lab_id: int = 1,
) -> Order:
    order = Order(
        lab_id=lab_id,
        image_url="orders/test.jpg",
        image_hash="abc",
        status=status,
    )
    session.add(order)
    session.flush()
    for i, score in enumerate(scores):
        session.add(
            OrderField(
                order_id=order.id,
                field_key=f"field_{i}",
                field_type=FieldType.B,
                score=score,
                status=FieldStatus.needs_review,
            )
        )
    session.commit()
    return order


def test_queue_filters_status(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as s:
        _make_order(s, OrderStatus.needs_review, [0.5, 0.8])
        _make_order(s, OrderStatus.confirmed, [0.9])

    resp = client.get("/api/orders")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["status"] == "needs_review"


def test_queue_includes_ocr_failed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as s:
        _make_order(s, OrderStatus.ocr_failed, [])

    resp = client.get("/api/orders")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["status"] == "ocr_failed"


def test_queue_sorted_by_min_score_asc(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as s:
        _make_order(s, OrderStatus.needs_review, [0.9, 0.95])
        low = _make_order(s, OrderStatus.needs_review, [0.3, 0.7])

    resp = client.get("/api/orders")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert items[0]["min_score"] <= items[1]["min_score"]
    assert items[0]["order_id"] == low.id
