"""의뢰서 단위 상태 전이 규칙 테스트."""

from __future__ import annotations

import pytest

from app.db.models import Order, OrderField
from app.domain.enums import FieldStatus, FieldType, OrderStatus
from app.services.order_status import derive_order_status, recompute_order_status


def test_all_confirmed_means_auto_confirmed() -> None:
    statuses = [FieldStatus.confirmed, FieldStatus.confirmed, FieldStatus.confirmed]
    assert derive_order_status(statuses) is OrderStatus.auto_confirmed


def test_any_needs_review_means_needs_review() -> None:
    statuses = [FieldStatus.confirmed, FieldStatus.needs_review, FieldStatus.confirmed]
    assert derive_order_status(statuses) is OrderStatus.needs_review


def test_single_confirmed() -> None:
    assert derive_order_status([FieldStatus.confirmed]) is OrderStatus.auto_confirmed


def test_empty_raises() -> None:
    with pytest.raises(ValueError, match="필드"):
        derive_order_status([])


def _field(status: FieldStatus) -> OrderField:
    return OrderField(field_key="k", field_type=FieldType.A, status=status)


def test_recompute_sets_order_status_auto_confirmed() -> None:
    order = Order(image_url="r2://x", image_hash="h")
    order.fields = [_field(FieldStatus.confirmed), _field(FieldStatus.confirmed)]
    result = recompute_order_status(order)
    assert result is OrderStatus.auto_confirmed
    assert order.status is OrderStatus.auto_confirmed


def test_recompute_sets_order_status_needs_review() -> None:
    order = Order(image_url="r2://x", image_hash="h")
    order.fields = [_field(FieldStatus.confirmed), _field(FieldStatus.needs_review)]
    result = recompute_order_status(order)
    assert result is OrderStatus.needs_review
    assert order.status is OrderStatus.needs_review
