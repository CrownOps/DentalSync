"""의뢰서 단위 상태 전이 규칙.

규칙:
  - 전 필드가 confirmed  → orders.status = auto_confirmed
  - 하나라도 needs_review → orders.status = needs_review
"""

from __future__ import annotations

from collections.abc import Sequence

from app.db.models import Order
from app.domain.enums import FieldStatus, OrderStatus


def derive_order_status(field_statuses: Sequence[FieldStatus]) -> OrderStatus:
    """필드 상태 목록으로부터 의뢰서 상태를 도출한다.

    필드가 하나도 없으면 상태를 결정할 수 없으므로 ValueError.
    """
    if not field_statuses:
        raise ValueError("필드가 없는 의뢰서의 상태는 도출할 수 없습니다")

    if any(s == FieldStatus.needs_review for s in field_statuses):
        return OrderStatus.needs_review
    return OrderStatus.auto_confirmed


def recompute_order_status(order: Order) -> OrderStatus:
    """order.fields 를 근거로 order.status 를 갱신하고 새 상태를 반환한다."""
    new_status = derive_order_status([f.status for f in order.fields])
    order.status = new_status
    return new_status
