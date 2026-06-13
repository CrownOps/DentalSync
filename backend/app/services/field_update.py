"""인라인 필드 수정 서비스 — PATCH /api/v1/review/{order_id}/fields/{field_key}.

수정 시 training_labels 는 적재하지 않는다 (확정 시 일괄 적재).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.db.models import Order

from app.services.type_b_rules import (
    PASS_FULL,
    TOOTH_NUMBER_KEYS,
    normalize_date,
    score_tooth_numbers,
)


class FieldValidationError(Exception):
    """필드 값 검증 실패 — 422 로 매핑."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule
        self.message = message


class FieldNotReviewableError(Exception):
    """수정 불가 상태 — 409 로 매핑."""


# VITA 클래식 코드 + VITA 3D-Master 코드
_VITA_CLASSIC = {"A1", "A2", "A3", "A3.5", "A4", "B1", "B2", "B3", "B4",
                 "C1", "C2", "C3", "C4", "D2", "D3", "D4"}
_VITA_3D = {f"{m}{s}{c}" for m in ["0", "1", "2", "3", "4", "5"]
            for s in ["M", "L", "R"] for c in ["1", "2", "3"]}
_VITA_CODES = _VITA_CLASSIC | _VITA_3D


def validate_tooth_number(value: str) -> None:
    """FDI 치아번호 검증 — 라우팅 룰(score_tooth_numbers)과 동일 파서 사용.

    쉼표/공백/세미콜론 구분 복수 치아와 브릿지 범위("36-37") 표기를 허용한다.
    사람이 입력하는 확정값이므로 모호한 범위(사분면 교차/역순)는 거부한다.
    """
    result = score_tooth_numbers(value)
    if result.rule_pass != PASS_FULL:
        raise FieldValidationError(
            rule="fdi_range",
            message=(
                f"유효하지 않은 치아번호 표기: {value!r} "
                "(FDI 11~48, 예: '36, 37' 또는 '36-37')"
            ),
        )


def validate_date_value(value: str) -> date:
    """날짜 형식 검증 + ISO 정규화 — 라우팅 룰(normalize_date)과 동일 파서 사용.

    점/슬래시/한글("2026.06.15", "2026년 6월 15일") 등 의뢰서·OCR 원본 표기를
    그대로 수용해 ISO(YYYY-MM-DD)로 정규화한다. 연/월/일이 모두 있어야 한다.
    """
    iso = normalize_date(value)
    if iso is None:
        raise FieldValidationError(
            rule="date_format",
            message=f"날짜 형식 오류: {value!r} (예: '2026-06-15', '2026.6.15', '2026년 6월 15일')",
        )
    return date.fromisoformat(iso)


def validate_shade(value: str) -> None:
    """VITA 셰이드 코드 검증."""
    normalized = value.strip().upper().replace(" ", "")
    if normalized not in {c.upper() for c in _VITA_CODES}:
        raise FieldValidationError(
            rule="vita_shade",
            message=f"유효하지 않은 VITA 셰이드 코드: {value!r}",
        )


def validate_due_date_after_received(due: date, received: date | None) -> None:
    if received and due < received:
        raise FieldValidationError(
            rule="due_date_after_received",
            message=f"납기일({due})이 접수일({received})보다 이전입니다",
        )


@dataclass
class FieldUpdateResult:
    order_id: int
    field_key: str
    corrected_value: str
    field_status: str


def apply_field_update(
    session: Session,
    order_id: int,
    field_key: str,
    new_value: str,
    actor: str,
) -> FieldUpdateResult:
    from app.db.models import FieldAuditLog, Order, OrderField
    from app.domain.enums import CorrectedBy, FieldStatus, FieldType, OrderStatus

    order: Order | None = session.get(Order, order_id)
    if order is None:
        from app.domain.errors import OrderNotFoundError
        raise OrderNotFoundError(order_id)

    field: OrderField | None = (
        session.query(OrderField)
        .filter_by(order_id=order_id, field_key=field_key)
        .first()
    )
    if field is None:
        raise FieldValidationError(
            rule="field_not_found",
            message=f"필드를 찾을 수 없음: {field_key}",
        )

    # 의뢰서 확정 전(needs_review)에는 이미 확정한 필드도 재수정 허용(오타 복구).
    # 의뢰서가 확정/자동확정된 뒤에는 수정 불가 — 409.
    if (
        field.status != FieldStatus.needs_review
        and order.status != OrderStatus.needs_review
    ):
        raise FieldNotReviewableError(
            f"수정 불가 상태: {field.field_key} "
            f"(field={field.status.value}, order={order.status.value})"
        )

    # 타입별 값 검증. 날짜는 ISO 정규화 결과를 저장값으로 채택(라우팅 출력과 동일).
    if field.field_type == FieldType.B:
        normalized = _validate_type_b_field(field_key, new_value, order)
        if normalized is not None:
            new_value = normalized
    elif field.field_type == FieldType.SHADE:
        validate_shade(new_value)

    before_snapshot = {
        "corrected_value": field.corrected_value,
        "corrected_by": field.corrected_by.value if field.corrected_by else None,
        "status": field.status.value,
    }

    field.corrected_value = new_value
    field.corrected_by = CorrectedBy.human
    field.status = FieldStatus.confirmed

    # flags 에 corrected_by_human 기록
    flags = dict(field.flags or {})
    flags["corrected_by_human"] = True
    field.flags = flags

    session.add(
        FieldAuditLog(
            order_field_id=field.id,
            before=before_snapshot,
            after={"corrected_value": new_value, "corrected_by": "human", "status": "confirmed"},
            actor=actor,
        )
    )

    session.commit()
    session.refresh(field)

    return FieldUpdateResult(
        order_id=order_id,
        field_key=field_key,
        corrected_value=new_value,
        field_status=field.status.value,
    )


def _validate_type_b_field(field_key: str, value: str, order: Order) -> str | None:
    """Type B 필드별 검증 — field_key 패턴으로 분기.

    날짜/납기 필드는 ISO(YYYY-MM-DD)로 정규화한 문자열을 반환한다.
    그 외(치아번호 등)는 저장값을 바꾸지 않으므로 None.
    """
    key_lower = field_key.lower()

    if any(k in key_lower for k in TOOTH_NUMBER_KEYS):
        validate_tooth_number(value)
        return None

    if "due" in key_lower or "납기" in key_lower:
        parsed = validate_date_value(value)
        received = order.received_at.date() if order.received_at else None
        validate_due_date_after_received(parsed, received)
        return parsed.isoformat()

    if "date" in key_lower or "날짜" in key_lower or "접수" in key_lower:
        return validate_date_value(value).isoformat()

    return None
