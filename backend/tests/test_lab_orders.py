"""GET /api/labs/{lab_id}/orders — 기공소별 의뢰서 목록 테스트.

전체 상태 반환 + status 쿼리 필터 + lab_id 격리 + 최신순 정렬 검증.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

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
        s.add(Lab(name="기공소1"))
        s.add(Lab(name="기공소2"))
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
    received_at: datetime | None = None,
) -> Order:
    order = Order(
        lab_id=lab_id,
        image_url="orders/test.jpg",
        image_hash="abc",
        status=status,
        received_at=received_at,
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
                status=FieldStatus.confirmed,
            )
        )
    session.commit()
    return order


def test_returns_all_statuses_for_lab(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as s:
        _make_order(s, OrderStatus.needs_review, [0.5])
        _make_order(s, OrderStatus.auto_confirmed, [0.95])
        _make_order(s, OrderStatus.ocr_failed, [])

    resp = client.get("/api/labs/1/orders")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 3
    statuses = {i["status"] for i in items}
    assert statuses == {"needs_review", "auto_confirmed", "ocr_failed"}


def test_status_filter(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as s:
        _make_order(s, OrderStatus.needs_review, [0.5])
        _make_order(s, OrderStatus.auto_confirmed, [0.95])
        _make_order(s, OrderStatus.confirmed, [0.99])

    resp = client.get(
        "/api/labs/1/orders",
        params=[("status", "auto_confirmed"), ("status", "confirmed")],
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert {i["status"] for i in items} == {"auto_confirmed", "confirmed"}


def test_lab_isolation(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as s:
        _make_order(s, OrderStatus.needs_review, [0.5], lab_id=1)
        _make_order(s, OrderStatus.needs_review, [0.5], lab_id=2)

    resp = client.get("/api/labs/2/orders")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["lab_id"] == 2


def test_sorted_by_received_at_desc(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as s:
        older = _make_order(
            s,
            OrderStatus.confirmed,
            [0.9],
            received_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        newer = _make_order(
            s,
            OrderStatus.confirmed,
            [0.9],
            received_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )

    resp = client.get("/api/labs/1/orders")
    assert resp.status_code == 200
    items = resp.json()
    assert [i["order_id"] for i in items] == [newer.id, older.id]


def test_empty_when_no_orders(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    resp = client.get("/api/labs/1/orders")
    assert resp.status_code == 200
    assert resp.json() == []
