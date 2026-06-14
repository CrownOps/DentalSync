"""PATCH /api/orders/{id}/confirm — HITL 확정 e2e 테스트.

검증 항목:
- 수정값 반영 + corrected_by=human
- FieldAuditLog 기록
- training_labels 적재 (raw, corrected, field_type, lab_id, corrected_by)
- 전 필드 confirmed, orders.status=confirmed
- REQ-002: 필수값 누락 시 422 거부
- 수정 없는 필드는 training_label 미적재
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_settings_dep, get_storage
from app.core.config import Settings
from app.db.base import Base
from app.db.models import FieldAuditLog, Lab, Order, OrderField, TrainingLabel
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
        s.add(Lab(name="테스트기공소", code="lab1", password_hash="x"))
        s.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    settings = Settings(blur_laplacian_min=5.0, min_image_width=200, min_image_height=200)

    def _db() -> Iterator[Session]:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_storage] = lambda: _FakeStorage()
    app.dependency_overrides[get_settings_dep] = lambda: settings
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_order(
    session_factory: sessionmaker[Session],
    fields: list[dict[str, Any]],
) -> int:
    with session_factory() as s:
        order = Order(
            lab_id=1,
            image_url="orders/test.jpg",
            image_hash="abc123",
            status=OrderStatus.needs_review,
        )
        s.add(order)
        s.flush()
        for f in fields:
            s.add(
                OrderField(
                    order_id=order.id,
                    field_key=f["field_key"],
                    field_type=FieldType.C,
                    raw_text=f.get("raw_text"),
                    corrected_value=f.get("corrected_value"),
                    score=f.get("score", 0.5),
                    status=FieldStatus.needs_review,
                )
            )
        s.commit()
        return order.id


def test_confirm_updates_fields_and_status(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    order_id = _seed_order(
        session_factory,
        [
            {"field_key": "tooth_number", "raw_text": "1#", "corrected_value": "1#"},
            {"field_key": "material", "raw_text": "지르코니아", "corrected_value": "지르코니아"},
        ],
    )

    resp = client.patch(
        f"/api/orders/{order_id}/confirm",
        json={
            "fields": [
                {"field_key": "tooth_number", "corrected_value": "11"},
                {"field_key": "material", "corrected_value": "지르코니아"},
            ],
            "actor": "staff_1",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["updated_fields"] == 1  # tooth_number만 변경

    with session_factory() as s:
        order = s.get(Order, order_id)
        assert order is not None
        assert order.status == OrderStatus.confirmed
        fields = {f.field_key: f for f in order.fields}
        assert fields["tooth_number"].corrected_value == "11"
        assert fields["tooth_number"].corrected_by == CorrectedBy.human
        assert fields["tooth_number"].status == FieldStatus.confirmed
        assert fields["material"].status == FieldStatus.confirmed


def test_confirm_inserts_training_labels(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    order_id = _seed_order(
        session_factory,
        [{"field_key": "shade", "raw_text": "A1", "corrected_value": "A1"}],
    )

    resp = client.patch(
        f"/api/orders/{order_id}/confirm",
        json={"fields": [{"field_key": "shade", "corrected_value": "A2"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["training_labels_inserted"] == 1

    with session_factory() as s:
        labels = s.query(TrainingLabel).all()
        assert len(labels) == 1
        label = labels[0]
        assert label.raw_text == "A1"
        assert label.corrected_value == "A2"
        assert label.corrected_by == CorrectedBy.human
        assert label.lab_id == 1
        assert label.field_type == FieldType.C


def test_confirm_records_audit_log(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    order_id = _seed_order(
        session_factory,
        [{"field_key": "due_date", "raw_text": "2025-07-01", "corrected_value": "2025-07-01"}],
    )

    client.patch(
        f"/api/orders/{order_id}/confirm",
        json={"fields": [{"field_key": "due_date", "corrected_value": "2025-07-15"}]},
    )

    with session_factory() as s:
        logs = s.query(FieldAuditLog).all()
        assert len(logs) == 1
        log = logs[0]
        assert log.before is not None
        assert log.after is not None
        assert log.before["corrected_value"] == "2025-07-01"
        assert log.after["corrected_value"] == "2025-07-15"
        assert log.actor == "human"


def test_confirm_no_change_skips_training_label(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """수정 없는 필드는 training_label 미적재."""
    order_id = _seed_order(
        session_factory,
        [{"field_key": "material", "raw_text": "PFM", "corrected_value": "PFM"}],
    )

    resp = client.patch(
        f"/api/orders/{order_id}/confirm",
        json={"fields": [{"field_key": "material", "corrected_value": "PFM"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["training_labels_inserted"] == 0

    with session_factory() as s:
        assert s.query(TrainingLabel).count() == 0


def test_req_002_missing_required_field_rejected(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """REQ-002: needs_review 필드에 값 없으면 422."""
    order_id = _seed_order(
        session_factory,
        [
            {"field_key": "tooth_number", "raw_text": "11", "corrected_value": "11"},
            {"field_key": "material", "raw_text": None, "corrected_value": None},
        ],
    )

    resp = client.patch(
        f"/api/orders/{order_id}/confirm",
        json={
            "fields": [
                {"field_key": "tooth_number", "corrected_value": "11"},
                # material 누락
            ]
        },
    )
    assert resp.status_code == 422
    assert "material" in resp.json()["detail"]


def test_confirm_order_not_found(client: TestClient) -> None:
    resp = client.patch(
        "/api/orders/9999/confirm",
        json={"fields": []},
    )
    assert resp.status_code == 404
