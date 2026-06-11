"""RoutingResultStore 서비스 테스트.

케이스:
1. 전 필드 고신뢰 → auto_confirmed
2. 1개 필드 일반 임계값 미달 → needs_review
3. 치명 필드 0.92 (일반 0.90 통과, 치명 0.95 미달) → needs_review
4. forced_hitl=true → 점수 무관 needs_review
5. 저장 중 예외 → 전체 롤백 (orders.status = routing 유지)
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Lab, Order
from app.domain.enums import CorrectedBy, FieldType, OrderStatus
from app.domain.scoring import ScoringConfig, ScoringThresholds, ScoringWeights
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
    critical_fields=["shade", "tooth_numbers", "due_date"],
)


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


def _make_order(factory: sessionmaker[Session], status: OrderStatus = OrderStatus.routing) -> int:
    with factory() as s:
        order = Order(lab_id=1, image_url="orders/test.jpg", image_hash="abc", status=status)
        s.add(order)
        s.commit()
        return order.id


def _make_field(
    key: str,
    score: float,
    forced_hitl: bool = False,
    field_type: FieldType = FieldType.B,
) -> RoutingFieldResult:
    return RoutingFieldResult(
        field_key=key,
        field_type=field_type,
        raw=RawOCR(text="raw_val", bbox=None, infer_confidence=score),
        corrected_value="corrected_val",
        corrected_by=CorrectedBy.system,
        confidence=FieldConfidence(score=score, ocr_conf=score),
        flags=FieldFlags(forced_hitl=forced_hitl),
    )


def test_all_high_confidence_auto_confirmed(session_factory: sessionmaker[Session]) -> None:
    order_id = _make_order(session_factory)
    with session_factory() as s:
        result = store_routing_result(
            session=s,
            order_id=order_id,
            field_results=[
                _make_field("field_a", 0.95),
                _make_field("field_b", 0.92),
            ],
            scoring_cfg=_SCORING_CFG,
        )
    assert result.status == OrderStatus.auto_confirmed
    assert result.needs_review_count == 0


def test_one_field_below_general_threshold_needs_review(session_factory: sessionmaker[Session]) -> None:
    order_id = _make_order(session_factory)
    with session_factory() as s:
        result = store_routing_result(
            session=s,
            order_id=order_id,
            field_results=[
                _make_field("field_a", 0.95),
                _make_field("field_b", 0.85),  # 0.90 미달
            ],
            scoring_cfg=_SCORING_CFG,
        )
    assert result.status == OrderStatus.needs_review
    assert result.needs_review_count == 1


def test_critical_field_below_critical_threshold_needs_review(
    session_factory: sessionmaker[Session],
) -> None:
    """치명 필드 0.92 — 일반 기준(0.90) 통과, 치명 기준(0.95) 미달."""
    order_id = _make_order(session_factory)
    with session_factory() as s:
        result = store_routing_result(
            session=s,
            order_id=order_id,
            field_results=[
                _make_field("shade", 0.92),  # critical 필드 0.92 < 0.95
            ],
            scoring_cfg=_SCORING_CFG,
        )
    assert result.status == OrderStatus.needs_review
    assert result.needs_review_count == 1


def test_forced_hitl_overrides_score(session_factory: sessionmaker[Session]) -> None:
    """forced_hitl=True → 점수 무관 needs_review."""
    order_id = _make_order(session_factory)
    with session_factory() as s:
        result = store_routing_result(
            session=s,
            order_id=order_id,
            field_results=[
                _make_field("field_a", 0.99, forced_hitl=True),
            ],
            scoring_cfg=_SCORING_CFG,
        )
    assert result.status == OrderStatus.needs_review


def test_exception_rolls_back_order_status_to_routing(
    session_factory: sessionmaker[Session],
) -> None:
    """저장 중 예외 → orders.status = routing 유지."""
    order_id = _make_order(session_factory, status=OrderStatus.routing)

    with (
        session_factory() as s,
        patch("app.services.routing_store.OrderField", side_effect=Exception("DB 오류")),
        pytest.raises(Exception, match="DB 오류"),
    ):
        store_routing_result(
            session=s,
            order_id=order_id,
            field_results=[_make_field("field_a", 0.95)],
            scoring_cfg=_SCORING_CFG,
        )

    with session_factory() as s:
        order = s.get(Order, order_id)
        assert order is not None
        assert order.status == OrderStatus.routing
