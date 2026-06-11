"""인라인 필드 수정 서비스 — PATCH /api/v1/review/{order_id}/fields/{field_key}.

수정 시 training_labels 는 적재하지 않는다 (확정 시 일괄 적재).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class FieldValidationError(Exception):
    """필드 값 검증 실패 — 422 로 매핑."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule
        self.message = message


class FieldNotReviewableError(Exception):
    """수정 불가 상태 — 409 로 매핑."""


# FDI 유효 치아 번호: 11~18, 21~28, 31~38, 41~48
_VALID_FDI = frozenset(
    f"{q}{t}" for q in range(1, 5) for t in range(1, 9)
)

# VITA 클래식 코드 + VITA 3D-Master 코드
_VITA_CLASSIC = {"A1", "A2", "A3", "A3.5", "A4", "B1", "B2", "B3", "B4",
                 "C1", "C2", "C3", "C4", "D2", "D3", "D4"}
_VITA_3D = {f"{m}{s}{c}" for m in ["0", "1", "2", "3", "4", "5"]
            for s in ["M", "L", "R"] for c in ["1", "2", "3"]}
_VITA_CODES = _VITA_CLASSIC | _VITA_3D


def validate_tooth_number(value: str) -> None:
    """FDI 치아번호 검증 — 공백 구분 복수 치아 허용."""
    tokens = value.strip().split()
    for token in tokens:
        if token not in _VALID_FDI:
            raise FieldValidationError(
                rule="fdi_range",
                message=f"유효하지 않은 FDI 치아번호: {token!r} (11~48 범위)",
            )


def validate_date_value(value: str) -> date:
    """날짜 형식 검증 — YYYY-MM-DD."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise FieldValidationError(
            rule="date_format",
            message=f"날짜 형식 오류: {value!r} (YYYY-MM-DD 필요)",
        ) from exc


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
    session,  # Session — import 순환 방지를 위해 타입 힌트 미사용
    order_id: int,
    field_key: str,
    new_value: str,
    actor: str,
) -> FieldUpdateResult:
    from app.db.models import FieldAuditLog, Order, OrderField
    from app.domain.enums import CorrectedBy, FieldStatus, FieldType

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

    if field.status != FieldStatus.needs_review:
        raise FieldNotReviewableError(
            f"수정 불가 상태: {field.field_key} (status={field.status.value})"
        )

    # 타입별 값 검증
    if field.field_type == FieldType.B:
        _validate_type_b_field(field_key, new_value, order)
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


def _validate_type_b_field(field_key: str, value: str, order) -> None:
    """Type B 필드별 검증 — field_key 패턴으로 분기."""
    key_lower = field_key.lower()

    if "tooth" in key_lower or "number" in key_lower:
        validate_tooth_number(value)

    elif "due" in key_lower or "납기" in key_lower:
        parsed = validate_date_value(value)
        received = order.received_at.date() if order.received_at else None
        validate_due_date_after_received(parsed, received)

    elif "date" in key_lower or "날짜" in key_lower or "접수" in key_lower:
        validate_date_value(value)
