"""HITL 확정 서비스 — POST /api/v1/review/{order_id}/confirm.

기존 order_confirm.py 와 달리:
- 전 필드 status 검증 (confirmed/auto_confirmed 여부)
- 이미 confirmed 의뢰서 → AlreadyConfirmedError (409)
- 수정 필드(corrected_by_human=true 또는 raw ≠ corrected)마다 training_labels INSERT
- 환자 식별정보 익명화 후 적재
- 단일 트랜잭션
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models import FieldAuditLog, Order, OrderField, TrainingLabel
from app.domain.enums import CorrectedBy, FieldStatus, OrderStatus
from app.domain.errors import OrderNotFoundError
from app.services.order_due_date import DUE_DATE_FIELD_KEYS, resolve_due_date


class AlreadyConfirmedError(Exception):
    """이미 confirmed 상태 — 409."""


class ConfirmValidationError(Exception):
    """확정 전 검증 실패 — 422."""

    def __init__(self, message: str, violations: list[str]) -> None:
        super().__init__(message)
        self.violations = violations


_PII_FIELD_KEYS = frozenset({"patient_name", "patient_id", "ssn", "phone"})


def _anonymize(value: str | None, field_key: str) -> str | None:
    """PII 필드 값 익명화 — 환자명은 마스킹, 그 외 PII 는 None 처리."""
    if value is None:
        return None
    if field_key in _PII_FIELD_KEYS:
        if len(value) <= 1:
            return "*"
        return value[0] + "*" * (len(value) - 1)
    return value


@dataclass
class ReviewConfirmResult:
    order_id: int
    status: OrderStatus
    training_labels_inserted: int
    unconfirmed_fields: list[str] = field(default_factory=list)


def confirm_review_order(
    session: Session,
    order_id: int,
    actor: str = "human",
) -> ReviewConfirmResult:
    """HITL 검토 확정.

    1. 이미 confirmed → AlreadyConfirmedError (409)
    2. 전 필드 status != needs_review 검증 (미확정 있으면 ConfirmValidationError)
    3. 필수값 검증 (REQ-002)
    4. training_labels 일괄 INSERT (corrected_by_human=true 또는 raw ≠ corrected)
    5. orders.status → confirmed
    """
    order: Order | None = session.get(Order, order_id)
    if order is None:
        raise OrderNotFoundError(order_id)

    if order.status == OrderStatus.confirmed:
        raise AlreadyConfirmedError(f"이미 확정된 의뢰서: {order_id}")

    fields: list[OrderField] = order.fields

    # 전 필드 confirmed/auto_confirmed 여부 검증
    unconfirmed = [f.field_key for f in fields if f.status == FieldStatus.needs_review]
    if unconfirmed:
        raise ConfirmValidationError(
            f"미확정 필드가 있습니다: {', '.join(unconfirmed)}",
            violations=unconfirmed,
        )

    # REQ-002: error 등급 — corrected_value 누락 필드 검증
    missing_values = [f.field_key for f in fields if not f.corrected_value and not f.raw_text]
    if missing_values:
        raise ConfirmValidationError(
            f"필수값 누락: {', '.join(missing_values)}",
            violations=missing_values,
        )

    labels_count = 0
    for f in fields:
        flags = f.flags or {}
        corrected_by_human = flags.get("corrected_by_human", False)

        # 자동값과 최종값이 다르거나 사람이 수정한 경우 학습셋 적재
        raw_val = f.raw_text
        final_val = f.corrected_value or f.raw_text
        if corrected_by_human or (raw_val and final_val and raw_val != final_val):
            anon_raw = _anonymize(raw_val, f.field_key)
            anon_corrected = _anonymize(final_val, f.field_key)

            session.add(
                TrainingLabel(
                    order_field_id=f.id,
                    raw_text=anon_raw,
                    corrected_value=anon_corrected or "",
                    field_type=f.field_type,
                    lab_id=order.lab_id,
                    corrected_by=CorrectedBy.human if corrected_by_human else CorrectedBy.system,
                )
            )
            labels_count += 1

    session.add(
        FieldAuditLog(
            order_field_id=fields[0].id if fields else 0,
            before={"status": order.status.value},
            after={"status": OrderStatus.confirmed.value},
            actor=actor,
        )
    )

    # 사람이 납기 필드를 수정했을 수 있으므로 orders.due_date 를 최종값으로 재동기화.
    due_candidates = {
        f.field_key: (f.corrected_value or f.raw_text)
        for f in fields
        if f.field_key in DUE_DATE_FIELD_KEYS
    }
    resolved_due = resolve_due_date(due_candidates)
    if resolved_due is not None:
        order.due_date = resolved_due

    order.status = OrderStatus.confirmed
    session.commit()

    return ReviewConfirmResult(
        order_id=order_id,
        status=OrderStatus.confirmed,
        training_labels_inserted=labels_count,
    )
