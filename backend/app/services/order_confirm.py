"""HITL 확정 서비스 — PATCH /api/orders/{id}/confirm.

처리 순서:
1. 수정된 필드 → corrected_value 갱신, corrected_by=human
2. 수정 발생 필드마다 FieldAuditLog + TrainingLabel INSERT
3. 필수 필드 누락 검증 (REQ-002): needs_review 필드 중 값 없는 것이 있으면 ValueError
4. 전 필드 status=confirmed, orders.status=confirmed
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import FieldAuditLog, Order, OrderField, TrainingLabel
from app.domain.enums import CorrectedBy, FieldStatus, OrderStatus
from app.domain.errors import OrderNotFoundError


@dataclass
class ConfirmResult:
    order_id: int
    status: OrderStatus
    updated_fields: int
    training_labels_inserted: int


def confirm_order(
    session: Session,
    order_id: int,
    field_updates: dict[str, str],
    actor: str = "human",
) -> ConfirmResult:
    """
    field_updates: {field_key: corrected_value}
    actor: 감사 로그에 기록할 사용자 식별자
    """
    order: Order | None = session.get(Order, order_id)
    if order is None:
        raise OrderNotFoundError(order_id)

    fields: list[OrderField] = order.fields
    field_map = {f.field_key: f for f in fields}

    updated_count = 0
    labels_count = 0

    for key, new_value in field_updates.items():
        field = field_map.get(key)
        if field is None:
            continue

        old_value = field.corrected_value
        if old_value == new_value:
            continue

        before_snapshot = {
            "corrected_value": old_value,
            "corrected_by": field.corrected_by.value if field.corrected_by else None,
            "status": field.status.value,
        }

        field.corrected_value = new_value
        field.corrected_by = CorrectedBy.human
        updated_count += 1

        session.add(
            FieldAuditLog(
                order_field_id=field.id,
                before=before_snapshot,
                after={"corrected_value": new_value, "corrected_by": "human"},
                actor=actor,
            )
        )

        # 수정 발생 시에만 학습셋 적재
        session.add(
            TrainingLabel(
                order_field_id=field.id,
                raw_text=field.raw_text,
                corrected_value=new_value,
                field_type=field.field_type,
                lab_id=order.lab_id,
                corrected_by=CorrectedBy.human,
            )
        )
        labels_count += 1

    # REQ-002: needs_review 필드 중 corrected_value 없는 것이 있으면 저장 거부
    missing = [
        f.field_key
        for f in fields
        if f.status == FieldStatus.needs_review
        and not (f.corrected_value or field_updates.get(f.field_key))
    ]
    if missing:
        raise ValueError(f"필수 필드 누락: {', '.join(missing)}")

    # 전 필드 confirmed
    for field in fields:
        field.status = FieldStatus.confirmed

    order.status = OrderStatus.confirmed
    session.commit()

    return ConfirmResult(
        order_id=order.id,
        status=order.status,
        updated_fields=updated_count,
        training_labels_inserted=labels_count,
    )
