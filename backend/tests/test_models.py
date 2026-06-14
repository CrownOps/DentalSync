"""모델 스키마/제약 검증 — sqlite(in-memory, 외부 의존 0).

Postgres 전용 타입(JSONB)은 sqlite 변형(JSON)으로 폴백되므로 모델 정의를 그대로
검증할 수 있다. alembic upgrade head(Postgres) 검증과는 별개로 모델 무결성을 본다.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import (
    FieldAuditLog,
    Lab,
    Order,
    OrderField,
    TrainingLabel,
    User,
)
from app.domain.enums import CorrectedBy, FieldStatus, FieldType, OrderStatus, UserRole

# 만들어선 안 되는 개인정보 컬럼 패턴 (환자명 외 PII 컬럼 금지)
FORBIDDEN_PII = ("phone", "tel", "mobile", "ssn", "resident", "jumin", "birth", "rrn")


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


def _seed_order_field(session: Session) -> OrderField:
    lab = Lab(name="서울미소치과", template_id="tmpl-1", code="lab1", password_hash="x")
    session.add(lab)
    session.flush()
    order = Order(lab_id=lab.id, image_url="r2://orders/abc.jpg", image_hash="abc123")
    session.add(order)
    session.flush()
    field = OrderField(
        order_id=order.id,
        field_key="shade",
        field_type=FieldType.SHADE,
        raw_text="A2",
        raw_bbox={"vertices": [{"x": 1, "y": 2}]},
        raw_ocr_conf=0.97,
        score=0.95,
        score_components={"ocr_conf": 0.97, "rule_pass": 1.0, "dict_match": 1.0},
        flags={"needs_review": False},
        status=FieldStatus.confirmed,
    )
    session.add(field)
    session.flush()
    return field


def test_insert_full_chain(session: Session) -> None:
    field = _seed_order_field(session)
    session.add(
        User(lab_id=field.order.lab_id, name="홍원장", role=UserRole.owner)
    )
    session.add(
        TrainingLabel(
            order_field_id=field.id,
            raw_text="A2",
            corrected_value="A2",
            field_type=FieldType.SHADE,
            lab_id=field.order.lab_id,
            corrected_by=CorrectedBy.human,
        )
    )
    session.add(
        FieldAuditLog(
            order_field_id=field.id,
            before={"corrected_value": None},
            after={"corrected_value": "A2"},
            actor="user:1",
        )
    )
    session.commit()

    assert session.query(Lab).count() == 1
    assert session.query(OrderField).count() == 1
    assert session.query(TrainingLabel).count() == 1
    # JSONB(→JSON) 라운드트립
    reloaded = session.get(OrderField, field.id)
    assert reloaded is not None
    assert reloaded.score_components == {"ocr_conf": 0.97, "rule_pass": 1.0, "dict_match": 1.0}


def test_order_field_unique_constraint(session: Session) -> None:
    field = _seed_order_field(session)
    session.add(
        OrderField(order_id=field.order_id, field_key="shade", field_type=FieldType.SHADE)
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_order_status_default_is_uploaded(session: Session) -> None:
    lab = Lab(name="lab", code="lab1", password_hash="x")
    session.add(lab)
    session.flush()
    order = Order(lab_id=lab.id, image_url="r2://x", image_hash="h")
    session.add(order)
    session.commit()
    assert order.status is OrderStatus.uploaded


def test_no_pii_columns_anywhere() -> None:
    """환자명 외 개인정보(주민번호/전화번호 등) 컬럼이 존재하지 않아야 한다."""
    offenders: list[str] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            lowered = column.name.lower()
            if any(token in lowered for token in FORBIDDEN_PII):
                offenders.append(f"{table.name}.{column.name}")
    assert offenders == [], f"금지된 PII 컬럼 발견: {offenders}"
