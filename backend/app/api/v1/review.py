"""HITL 검토 라우터 — /api/v1/review/."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_storage, require_auth
from app.db.models import Order, OrderField
from app.domain.enums import FieldStatus, OrderStatus
from app.domain.errors import OrderNotFoundError, StorageError
from app.infra.storage import StorageClient
from app.schemas.review import (
    AccuracyResponse,
    ConfirmResponse,
    FieldAccuracyItem,
    FieldEnvelope,
    FieldUpdateRequest,
    FieldUpdateResponse,
    ReviewDetailResponse,
    ReviewQueueItem,
    ReviewQueueResponse,
)
from app.services.accuracy import compute_field_accuracy
from app.services.field_update import (
    FieldNotReviewableError,
    FieldValidationError,
    apply_field_update,
)
from app.services.order_review_confirm import (
    AlreadyConfirmedError,
    ConfirmValidationError,
    confirm_review_order,
)

router = APIRouter(
    prefix="/api/v1/review",
    tags=["review"],
    dependencies=[Depends(require_auth)],
)

# PII 필드 키 목록 — 레이아웃 정의 v1.1.0 의 pii:true 필드
_PII_FIELD_KEYS = frozenset({"patient_name", "patient_id", "ssn", "phone"})


def _to_field_envelope(f: OrderField) -> FieldEnvelope:
    flags = f.flags or {}
    return FieldEnvelope(
        field_key=f.field_key,
        field_type=f.field_type.value,
        value=f.corrected_value or f.raw_text,
        raw=f.raw_text,
        bbox=f.raw_bbox,
        confidence=f.score,
        score_components=f.score_components,
        status=f.status.value,
        flags=flags,
        corrected_by=f.corrected_by.value if f.corrected_by else None,
        corrected_at=f.updated_at.isoformat() if f.updated_at else None,
        pii=f.field_key in _PII_FIELD_KEYS,
    )


# ── 검토 큐 ───────────────────────────────────────────────────────────────────


@router.get("/queue", response_model=ReviewQueueResponse)
def get_review_queue(
    session: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ReviewQueueResponse:
    """needs_review 의뢰서 목록 — 최저 신뢰도 오름차순."""
    subq = (
        session.query(
            OrderField.order_id,
            func.min(OrderField.score).label("min_score"),
            func.count(OrderField.id).filter(
                OrderField.status == FieldStatus.needs_review
            ).label("needs_review_count"),
        )
        .group_by(OrderField.order_id)
        .subquery()
    )

    base_q = (
        session.query(Order, subq.c.min_score, subq.c.needs_review_count)
        .outerjoin(subq, Order.id == subq.c.order_id)
        .filter(Order.status == OrderStatus.needs_review)
        .order_by(subq.c.min_score.asc().nulls_last())
    )

    total = base_q.count()
    rows = base_q.offset(offset).limit(limit).all()

    items = []
    for order, min_score, needs_review_count in rows:
        has_forced = any(
            (f.flags or {}).get("forced_hitl", False) for f in order.fields
        )
        items.append(
            ReviewQueueItem(
                order_id=order.id,
                lab_id=order.lab_id,
                status=order.status.value,
                received_at=order.received_at.isoformat() if order.received_at else None,
                needs_review_count=needs_review_count or 0,
                min_score=min_score,
                has_forced_hitl=has_forced,
            )
        )

    return ReviewQueueResponse(items=items, total=total, limit=limit, offset=offset)


# ── 검토 상세 ─────────────────────────────────────────────────────────────────


@router.get("/{order_id}", response_model=ReviewDetailResponse)
def get_review_detail(
    order_id: int,
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageClient, Depends(get_storage)],
) -> ReviewDetailResponse:
    """의뢰서 상세 + R2 presigned URL + 필드 envelope."""
    order: Order | None = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"의뢰서를 찾을 수 없음: {order_id}")

    try:
        image_url = storage.generate_presigned_url(order.image_url, expires=300)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=f"스토리지 오류: {exc}") from exc

    return ReviewDetailResponse(
        order_id=order.id,
        lab_id=order.lab_id,
        status=order.status.value,
        image_url=image_url,
        received_at=order.received_at.isoformat() if order.received_at else None,
        due_date=order.due_date.isoformat() if order.due_date else None,
        fields=[_to_field_envelope(f) for f in order.fields],
    )


# ── 인라인 필드 수정 ──────────────────────────────────────────────────────────


@router.patch("/{order_id}/fields/{field_key}", response_model=FieldUpdateResponse)
def update_field(
    order_id: int,
    field_key: str,
    body: FieldUpdateRequest,
    session: Annotated[Session, Depends(get_db)],
) -> FieldUpdateResponse:
    """needs_review 필드 인라인 수정 — training_labels 미적재."""
    try:
        result = apply_field_update(
            session=session,
            order_id=order_id,
            field_key=field_key,
            new_value=body.value,
            actor="human",
        )
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FieldNotReviewableError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "FIELD_NOT_REVIEWABLE", "message": str(exc), "details": []}},
        ) from exc
    except FieldValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": exc.rule, "message": exc.message, "details": [exc.message]}},
        ) from exc

    return FieldUpdateResponse(
        order_id=result.order_id,
        field_key=result.field_key,
        corrected_value=result.corrected_value,
        field_status=result.field_status,
    )


# ── 확정 ─────────────────────────────────────────────────────────────────────


@router.post("/{order_id}/confirm", response_model=ConfirmResponse)
def confirm_order(
    order_id: int,
    session: Annotated[Session, Depends(get_db)],
    actor: str = "human",
) -> ConfirmResponse:
    """HITL 확정 — training_labels 일괄 적재. 멱등: 재호출 → 409."""
    try:
        result = confirm_review_order(session=session, order_id=order_id, actor=actor)
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AlreadyConfirmedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "ALREADY_CONFIRMED", "message": str(exc), "details": []}},
        ) from exc
    except ConfirmValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "CONFIRM_VALIDATION_FAILED",
                    "message": str(exc),
                    "details": exc.violations,
                }
            },
        ) from exc

    return ConfirmResponse(
        order_id=result.order_id,
        status=result.status.value,
        training_labels_inserted=result.training_labels_inserted,
    )


# ── 정확도 집계 ───────────────────────────────────────────────────────────────


@router.get("/accuracy/fields", response_model=AccuracyResponse)
def get_field_accuracy(
    session: Annotated[Session, Depends(get_db)],
) -> AccuracyResponse:
    """필드별 자동 정확도 집계 — 파일럿 70% 목표 측정용."""
    rows = compute_field_accuracy(session)
    return AccuracyResponse(
        items=[
            FieldAccuracyItem(
                field_key=r.field_key,
                total=r.total,
                auto_correct=r.auto_correct,
                accuracy=r.accuracy,
            )
            for r in rows
        ]
    )
