"""의뢰서 업로드 엔드포인트 — POST /api/orders (multipart)."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_cache,
    get_db,
    get_ocr_engine,
    get_order_pipeline,
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
    OCRRunResponse,
    OrderDetailResponse,
    OrderFieldOut,
    OrderIntakeResponse,
    OrderSummaryOut,
)
from app.services.ocr_runner import run_ocr
from app.services.order_intake import intake_order
from app.services.order_pipeline import OrderPipeline

router = APIRouter(prefix="/api", tags=["orders"])


@router.post("/orders", response_model=OrderIntakeResponse, status_code=201)
async def create_order(
    image: Annotated[UploadFile, File()],
    lab_id: Annotated[int, Form()],
    background: BackgroundTasks,
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageClient, Depends(get_storage)],
    cache: Annotated[CacheClient, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    pipeline: Annotated[OrderPipeline, Depends(get_order_pipeline)],
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

    # 업로드 완료 → 파이프라인 비동기 실행 (QStash 금지 — Phase 1 결정)
    background.add_task(pipeline.run_safe, result.order_id)
    return OrderIntakeResponse.from_result(result)


@router.get("/orders/{order_id}", response_model=OrderDetailResponse)
async def get_order(
    order_id: int,
    session: Annotated[Session, Depends(get_db)],
) -> OrderDetailResponse:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"order {order_id} not found")
    return OrderDetailResponse(
        order_id=order.id,
        lab_id=order.lab_id,
        status=order.status.value,
        image_hash=order.image_hash,
        fields=[
            OrderFieldOut(
                field_key=f.field_key,
                field_type=f.field_type.value,
                raw_text=f.raw_text,
                corrected_value=f.corrected_value,
                corrected_by=f.corrected_by.value if f.corrected_by else None,
                score=f.score,
                score_components=f.score_components,
                status=f.status.value,
                flags=f.flags,
            )
            for f in sorted(order.fields, key=lambda x: x.field_key)
        ],
    )


@router.get("/orders", response_model=list[OrderSummaryOut])
async def list_orders(
    session: Annotated[Session, Depends(get_db)],
    status: Annotated[OrderStatus | None, Query()] = None,
    lab_id: Annotated[int | None, Query()] = None,
) -> list[OrderSummaryOut]:
    """검토 큐 등 목록 조회 — 신뢰도(최저 필드 점수) 낮은 순 정렬."""
    min_score = (
        select(OrderField.order_id, func.min(OrderField.score).label("min_score"))
        .group_by(OrderField.order_id)
        .subquery()
    )
    stmt = (
        select(Order, min_score.c.min_score)
        .outerjoin(min_score, Order.id == min_score.c.order_id)
        .order_by(min_score.c.min_score.asc().nulls_last(), Order.id.asc())
    )
    if status is not None:
        stmt = stmt.where(Order.status == status)
    if lab_id is not None:
        stmt = stmt.where(Order.lab_id == lab_id)

    rows = session.execute(stmt).all()
    return [
        OrderSummaryOut(
            order_id=order.id,
            lab_id=order.lab_id,
            status=order.status.value,
            min_score=score,
        )
        for order, score in rows
    ]


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
