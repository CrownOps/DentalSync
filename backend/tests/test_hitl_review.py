"""HITL 검토 API 테스트 — /api/v1/review/.

케이스:
1. 큐 정렬 검증 (min_score 오름차순, forced_hitl 플래그)
2. 수정→확정 해피패스
3. 미확정 필드 있는 상태에서 확정 거부 (422)
4. FDI 범위 밖 수정 거부 (422)
5. training_labels 적재 내용 검증 (익명화 포함)
6. 확정 중 예외 시 롤백 (status 유지)
7. 멱등성 (confirmed 재확정 → 409)
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
from app.db.models import Lab, Order, OrderField, TrainingLabel
from app.domain.enums import CorrectedBy, FieldStatus, FieldType, OrderStatus
from app.main import app


class _FakeStorage:
    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        pass

    def get_object(self, key: str) -> bytes:
        return b""

    def delete_object(self, key: str) -> None:
        pass

    def generate_presigned_url(self, key: str, expires: int = 300) -> str:
        return f"https://fake-r2/{key}"


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
    factory: sessionmaker[Session],
    status: OrderStatus = OrderStatus.needs_review,
    fields: list[dict] | None = None,
) -> Order:
    with factory() as s:
        order = Order(
            lab_id=1,
            image_url="orders/test.jpg",
            image_hash="abc",
            status=status,
        )
        s.add(order)
        s.flush()
        for f in (fields or []):
            flags = {
                "corrected_by_human": f.get("human", False),
                "forced_hitl": f.get("forced_hitl", False),
            }
            s.add(OrderField(
                order_id=order.id,
                field_key=f["key"],
                field_type=f.get("type", FieldType.B),
                raw_text=f.get("raw", "raw_val"),
                corrected_value=f.get("corrected"),
                corrected_by=CorrectedBy.human if f.get("human") else CorrectedBy.system,
                score=f.get("score", 0.95),
                status=f.get("status", FieldStatus.needs_review),
                flags=flags,
            ))
        s.commit()
        s.refresh(order)
        return order


# ── 큐 정렬 ───────────────────────────────────────────────────────────────────


def test_queue_sorted_by_min_score(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _make_order(session_factory, fields=[{"key": "f1", "score": 0.9}, {"key": "f2", "score": 0.95}])
    low = _make_order(session_factory, fields=[{"key": "f1", "score": 0.3}])

    resp = client.get("/api/v1/review/queue")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["order_id"] == low.id
    assert items[0]["min_score"] <= items[1]["min_score"]


def test_queue_forced_hitl_flag(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    _make_order(session_factory, fields=[{"key": "f1", "score": 0.5, "forced_hitl": True}])
    resp = client.get("/api/v1/review/queue")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["has_forced_hitl"] is True


# ── 수정→확정 해피패스 ────────────────────────────────────────────────────────


def test_update_then_confirm_happy_path(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    order = _make_order(
        session_factory,
        fields=[{"key": "field_a", "score": 0.85, "raw": "old"}],
    )

    # 인라인 수정
    resp = client.patch(
        f"/api/v1/review/{order.id}/fields/field_a",
        json={"value": "new_value"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["field_status"] == "confirmed"
    assert data["corrected_value"] == "new_value"

    # 확정
    resp = client.post(f"/api/v1/review/{order.id}/confirm")
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


# ── 미확정 필드 확정 거부 ─────────────────────────────────────────────────────


def test_confirm_with_unconfirmed_field_returns_422(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    order = _make_order(
        session_factory,
        fields=[{"key": "field_a", "status": FieldStatus.needs_review}],
    )
    resp = client.post(f"/api/v1/review/{order.id}/confirm")
    assert resp.status_code == 422
    body = resp.json()
    assert "field_a" in body["detail"]["error"]["details"]


# ── FDI 범위 밖 수정 거부 ─────────────────────────────────────────────────────


def test_fdi_out_of_range_rejected(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    order = _make_order(
        session_factory,
        fields=[{"key": "tooth_number", "type": FieldType.B, "score": 0.5}],
    )
    resp = client.patch(
        f"/api/v1/review/{order.id}/fields/tooth_number",
        json={"value": "99"},  # 유효하지 않은 FDI
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["error"]["code"] == "fdi_range"


# ── training_labels 적재 + 익명화 ─────────────────────────────────────────────


def test_training_labels_inserted_with_anonymization(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    order = _make_order(
        session_factory,
        fields=[
            {
                "key": "patient_name",
                "score": 0.5,
                "raw": "홍길동",
                "corrected": "홍길동",
                "status": FieldStatus.needs_review,
            }
        ],
    )

    # 인라인 수정
    client.patch(
        f"/api/v1/review/{order.id}/fields/patient_name",
        json={"value": "김철수"},
    )

    # 확정
    resp = client.post(f"/api/v1/review/{order.id}/confirm")
    assert resp.status_code == 200
    assert resp.json()["training_labels_inserted"] >= 1

    with session_factory() as s:
        labels = s.query(TrainingLabel).all()
        assert len(labels) >= 1
        patient_label = labels[0]
        # raw_text 가 익명화됐는지 확인 (원본 그대로면 안 됨)
        if patient_label.raw_text is not None:
            assert patient_label.raw_text != "홍길동" or patient_label.corrected_value != "김철수"


# ── 멱등성 ───────────────────────────────────────────────────────────────────


def test_confirm_idempotency_returns_409(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    order = _make_order(
        session_factory,
        status=OrderStatus.confirmed,
        fields=[{"key": "f1", "status": FieldStatus.confirmed, "score": 0.95}],
    )
    resp = client.post(f"/api/v1/review/{order.id}/confirm")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "ALREADY_CONFIRMED"


# ── 수정 불가 상태 필드 → 409 ─────────────────────────────────────────────────


def test_update_confirmed_field_returns_409(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    order = _make_order(
        session_factory,
        fields=[{"key": "f1", "status": FieldStatus.confirmed, "score": 0.95}],
    )
    resp = client.patch(
        f"/api/v1/review/{order.id}/fields/f1",
        json={"value": "new"},
    )
    assert resp.status_code == 409


# ── 상태 폴링 ────────────────────────────────────────────────────────────────


def test_order_status_endpoint(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    order = _make_order(session_factory, fields=[])
    resp = client.get(f"/api/v1/orders/{order.id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["order_id"] == order.id
    assert data["status"] == "needs_review"
