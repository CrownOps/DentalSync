"""라우팅 결과 저장 서비스 — OCR 파이프라인 마지막 단계에서 호출.

BackgroundTasks 파이프라인에서 호출되며 HTTP 엔드포인트가 아니다.
단일 트랜잭션으로 order_fields INSERT + orders.status 갱신.
실패 시 롤백 후 orders.status = routing 유지.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.scoring import get_scoring_config
from app.db.models import Order, OrderField
from app.domain.enums import CorrectedBy, FieldStatus, FieldType, OrderStatus
from app.domain.errors import OrderNotFoundError
from app.domain.scoring import ScoringConfig


@dataclass
class RawOCR:
    text: str | None
    bbox: dict[str, Any] | None
    infer_confidence: float | None


@dataclass
class FieldConfidence:
    score: float
    ocr_conf: float | None = None
    rule_pass: float | None = None
    dict_match: float | None = None


@dataclass
class FieldFlags:
    needs_review: bool = False
    forced_hitl: bool = False
    model_escalated: bool = False
    field_type: str = ""


@dataclass
class RoutingFieldResult:
    field_key: str
    field_type: FieldType
    raw: RawOCR
    corrected_value: str | None
    corrected_by: CorrectedBy
    confidence: FieldConfidence
    flags: FieldFlags


@dataclass
class RoutingStoreResult:
    order_id: int
    status: OrderStatus
    field_count: int
    needs_review_count: int


def _determine_field_status(
    field_key: str,
    confidence: FieldConfidence,
    flags: FieldFlags,
    cfg: ScoringConfig,
) -> FieldStatus:
    if flags.forced_hitl:
        return FieldStatus.needs_review
    threshold = cfg.threshold_for(field_key)
    if confidence.score >= threshold:
        return FieldStatus.confirmed
    return FieldStatus.needs_review


def store_routing_result(
    session: Session,
    order_id: int,
    field_results: list[RoutingFieldResult],
    scoring_cfg: ScoringConfig | None = None,
) -> RoutingStoreResult:
    """order_fields INSERT + orders.status 갱신 (단일 트랜잭션).

    실패 시 orders.status 는 routing 으로 유지되며 롤백된다.
    """
    order: Order | None = session.get(Order, order_id)
    if order is None:
        raise OrderNotFoundError(order_id)

    cfg = scoring_cfg or get_scoring_config()

    try:
        # OCR 재시도 등 재실행 시 (order_id, field_key) 유니크 제약 충돌 방지
        session.query(OrderField).filter_by(order_id=order_id).delete()

        needs_review_count = 0
        for fr in field_results:
            field_status = _determine_field_status(fr.field_key, fr.confidence, fr.flags, cfg)
            if field_status == FieldStatus.needs_review:
                needs_review_count += 1

            flags_dict: dict[str, Any] = {
                "field_type": fr.flags.field_type or fr.field_type.value,
                "needs_review": fr.flags.needs_review,
                "forced_hitl": fr.flags.forced_hitl,
                "model_escalated": fr.flags.model_escalated,
                "corrected_by_human": False,
            }

            score_components: dict[str, Any] = {}
            if fr.confidence.ocr_conf is not None:
                score_components["ocr_conf"] = fr.confidence.ocr_conf
            if fr.confidence.rule_pass is not None:
                score_components["rule_pass"] = fr.confidence.rule_pass
            if fr.confidence.dict_match is not None:
                score_components["dict_match"] = fr.confidence.dict_match

            order_field = OrderField(
                order_id=order_id,
                field_key=fr.field_key,
                field_type=fr.field_type,
                raw_text=fr.raw.text,
                raw_bbox=fr.raw.bbox,
                raw_ocr_conf=fr.raw.infer_confidence,
                corrected_value=fr.corrected_value,
                corrected_by=fr.corrected_by,
                score=fr.confidence.score,
                score_components=score_components or None,
                ocr_conf=fr.confidence.ocr_conf,
                rule_pass=fr.confidence.rule_pass,
                dict_match=fr.confidence.dict_match,
                flags=flags_dict,
                status=field_status,
            )
            session.add(order_field)

        order_status = (
            OrderStatus.needs_review if needs_review_count > 0 else OrderStatus.auto_confirmed
        )
        order.status = order_status

        session.commit()

    except Exception:
        session.rollback()
        order.status = OrderStatus.routing
        session.commit()
        raise

    return RoutingStoreResult(
        order_id=order_id,
        status=order_status,
        field_count=len(field_results),
        needs_review_count=needs_review_count,
    )
