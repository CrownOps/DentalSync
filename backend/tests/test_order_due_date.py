"""orders.due_date 도출 로직 테스트 — parse/resolve + store_routing_result 통합."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Lab, Order
from app.domain.enums import CorrectedBy, FieldType, OrderStatus
from app.domain.scoring import ScoringConfig, ScoringThresholds, ScoringWeights
from app.services.order_due_date import parse_due_date, resolve_due_date
from app.services.routing_store import (
    FieldConfidence,
    FieldFlags,
    RawOCR,
    RoutingFieldResult,
    store_routing_result,
)

_SCORING_CFG = ScoringConfig(
    weights=ScoringWeights(ocr_conf=0.5, rule_pass=0.3, dict_match=0.2),
    thresholds=ScoringThresholds(general=0.90, critical=0.95),
    critical_fields=["due_date"],
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-06-20", date(2026, 6, 20)),
        ("2026.06.20", date(2026, 6, 20)),
        ("2026년 6월 20일", date(2026, 6, 20)),
        ("2026-06-20T09:00:00", date(2026, 6, 20)),  # LLM ISO datetime
        ("20260620", date(2026, 6, 20)),
        ("6/20", None),  # 연도 없음 → 모호
        ("", None),
        (None, None),
        ("내일까지", None),
    ],
)
def test_parse_due_date(raw: str | None, expected: date | None) -> None:
    assert parse_due_date(raw) == expected


def test_resolve_prefers_due_date_over_internal() -> None:
    candidates = {"internal_due_date": "2026-07-01", "due_date": "2026-06-20"}
    assert resolve_due_date(candidates) == date(2026, 6, 20)


def test_resolve_falls_back_to_internal_when_body_unparseable() -> None:
    candidates = {"due_date": "미정", "internal_due_date": "2026-07-01"}
    assert resolve_due_date(candidates) == date(2026, 7, 1)


def test_resolve_none_when_no_due_fields() -> None:
    assert resolve_due_date({"shade": "A2"}) is None


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


def _due_field(value: str, key: str = "due_date") -> RoutingFieldResult:
    return RoutingFieldResult(
        field_key=key,
        field_type=FieldType.B,
        raw=RawOCR(text=value, bbox=None, infer_confidence=0.95),
        corrected_value=value,
        corrected_by=CorrectedBy.system,
        confidence=FieldConfidence(score=0.99, ocr_conf=0.95),
        flags=FieldFlags(field_type=FieldType.B.value),
    )


def test_store_routing_result_populates_order_due_date(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as s:
        order = Order(
            lab_id=1, image_url="orders/t.jpg", image_hash="h", status=OrderStatus.routing
        )
        s.add(order)
        s.commit()
        order_id = order.id

    with session_factory() as s:
        store_routing_result(
            session=s,
            order_id=order_id,
            field_results=[_due_field("2026-06-20")],
            scoring_cfg=_SCORING_CFG,
        )

    with session_factory() as s:
        stored = s.get(Order, order_id)
        assert stored is not None
        assert stored.due_date == date(2026, 6, 20)
