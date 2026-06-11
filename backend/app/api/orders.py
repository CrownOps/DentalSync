"""의뢰서 업로드 / HITL 검토 엔드포인트."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import (
    get_cache,
    get_db,
    get_ocr_engine,
    get_settings_dep,
    get_storage,
)
from app.core.config import Settings
from app.db.models import Order, OrderField
from app.domain.enums import OrderStatus
from app.domain.errors import (
    LabNotFoundError,
    OrderNotFoundError,
    StorageError,
)
from app.infra.cache import CacheClient
from app.infra.ocr.base import OCREngine, OCRExtractionError
from app.infra.storage import StorageClient
from app.schemas.orders import (
    ConfirmOrderRequest,
    ConfirmOrderResponse,
    OCRRunResponse,
    OrderDetailResponse,
    OrderFieldDetail,
    OrderIntakeResponse,
    ReviewQueueItem,
)
from app.schemas.review import OrderStatusResponse
from app.services.ocr_runner import run_ocr
from app.services.order_confirm import confirm_order
from app.services.order_intake import intake_order

router = APIRouter(prefix="/api", tags=["orders"])


@router.post("/orders", response_model=OrderIntakeResponse, status_code=201)
async def create_order(
    image: Annotated[UploadFile, File()],
    lab_id: Annotated[int, Form()],
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageClient, Depends(get_storage)],
    cache: Annotated[CacheClient, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> OrderIntakeResponse:
    data = await image.read()
    try:
        result = intake_order(
            session=session,
            lab_id=lab_id,
            data=data,
            storage=storage,
            cache=cache,
            settings=settings,
        )
    except LabNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=f"스토리지 오류: {exc}") from exc

    return OrderIntakeResponse.from_result(result)


@router.get("/orders", response_model=list[ReviewQueueItem])
def list_review_queue(
    session: Annotated[Session, Depends(get_db)],
) -> list[ReviewQueueItem]:
    """needs_review / ocr_failed 의뢰서 목록 — 신뢰도 낮은 순."""
    subq = (
        session.query(
            OrderField.order_id,
            func.min(OrderField.score).label("min_score"),
            func.count(OrderField.id).label("field_count"),
        )
        .group_by(OrderField.order_id)
        .subquery()
    )

    rows = (
        session.query(Order, subq.c.min_score, subq.c.field_count)
        .outerjoin(subq, Order.id == subq.c.order_id)
        .filter(Order.status.in_([OrderStatus.needs_review, OrderStatus.ocr_failed]))
        .order_by(subq.c.min_score.asc().nulls_last())
        .all()
    )

    return [
        ReviewQueueItem(
            order_id=order.id,
            lab_id=order.lab_id,
            status=order.status.value,
            received_at=order.received_at.isoformat() if order.received_at else None,
            due_date=order.due_date.isoformat() if order.due_date else None,
            min_score=min_score,
            field_count=field_count or 0,
        )
        for order, min_score, field_count in rows
    ]


@router.get("/orders/{order_id}", response_model=OrderDetailResponse)
def get_order_detail(
    order_id: int,
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageClient, Depends(get_storage)],
) -> OrderDetailResponse:
    """의뢰서 상세 + R2 presigned URL."""
    order: Order | None = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"주문을 찾을 수 없음: {order_id}")

    try:
        image_url = storage.generate_presigned_url(order.image_url, expires=300)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=f"스토리지 오류: {exc}") from exc

    return OrderDetailResponse(
        order_id=order.id,
        lab_id=order.lab_id,
        status=order.status.value,
        image_url=image_url,
        received_at=order.received_at.isoformat() if order.received_at else None,
        due_date=order.due_date.isoformat() if order.due_date else None,
        fields=[
            OrderFieldDetail(
                id=f.id,
                field_key=f.field_key,
                field_type=f.field_type.value,
                raw_text=f.raw_text,
                raw_bbox=f.raw_bbox,
                raw_ocr_conf=f.raw_ocr_conf,
                corrected_value=f.corrected_value,
                corrected_by=f.corrected_by.value if f.corrected_by else None,
                score=f.score,
                score_components=f.score_components,
                flags=f.flags,
                status=f.status.value,
            )
            for f in order.fields
        ],
    )


@router.patch("/orders/{order_id}/confirm", response_model=ConfirmOrderResponse)
def confirm_order_endpoint(
    order_id: int,
    body: ConfirmOrderRequest,
    session: Annotated[Session, Depends(get_db)],
) -> ConfirmOrderResponse:
    """HITL 검토 확정 — 수정값 반영 + training_labels 적재."""
    updates = {item.field_key: item.corrected_value for item in body.fields}
    try:
        result = confirm_order(
            session=session,
            order_id=order_id,
            field_updates=updates,
            actor=body.actor,
        )
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ConfirmOrderResponse(
        order_id=result.order_id,
        status=result.status.value,
        updated_fields=result.updated_fields,
        training_labels_inserted=result.training_labels_inserted,
    )


@router.get("/v1/orders/{order_id}/status", response_model=OrderStatusResponse)
def get_order_status(
    order_id: int,
    session: Annotated[Session, Depends(get_db)],
) -> OrderStatusResponse:
    """상태 폴링 전용 경량 엔드포인트 — 프론트 TanStack Query 폴링용."""
    order: Order | None = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"주문을 찾을 수 없음: {order_id}")
    return OrderStatusResponse(
        order_id=order.id,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )


@router.post("/orders/{order_id}/retry-ocr", response_model=OCRRunResponse)
async def retry_ocr(
    order_id: int,
    session: Annotated[Session, Depends(get_db)],
    engine: Annotated[OCREngine, Depends(get_ocr_engine)],
    storage: Annotated[StorageClient, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> OCRRunResponse:
    try:
        result = await run_ocr(
            session=session,
            order_id=order_id,
            engine=engine,
            storage=storage,
            settings=settings,
        )
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=f"스토리지 오류: {exc}") from exc
    except OCRExtractionError as exc:
        raise HTTPException(
            status_code=502, detail=f"OCR 실패(ocr_failed): {exc}"
        ) from exc

    return OCRRunResponse(
        order_id=result.order_id,
        status=result.status.value,
        field_count=len(result.fields),
    )
