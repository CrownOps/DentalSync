"""의뢰서 업로드 / HITL 검토 엔드포인트."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    get_cache,
    get_db,
    get_db_session_factory,
    get_ocr_engine,
    get_settings_dep,
    get_storage,
    require_auth,
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

router = APIRouter(prefix="/api", tags=["orders"], dependencies=[Depends(require_auth)])

logger = logging.getLogger(__name__)


async def _run_ocr_pipeline(
    *,
    order_id: int,
    session_factory: sessionmaker[Session],
    engine: OCREngine,
    storage: StorageClient,
    settings: Settings,
) -> None:
    """업로드 직후 백그라운드 OCR 파이프라인 (Phase 1: BackgroundTasks, Phase 2: QStash).

    요청 스코프 세션은 응답 후 닫히므로 자체 세션을 생성한다.
    실패해도 응답에는 영향 없음 — 상태는 ocr_failed 로 남고 수동 재시도 대상.
    """
    session = session_factory()
    try:
        await run_ocr(
            session=session,
            order_id=order_id,
            engine=engine,
            storage=storage,
            settings=settings,
        )
    except OCRExtractionError:
        # run_ocr 가 이미 status=ocr_failed 커밋 — 프론트 폴링이 재시도 UI 로 분기
        logger.warning("백그라운드 OCR 실패(order_id=%s) — 수동 재시도 대상", order_id)
    except Exception:
        logger.exception("백그라운드 파이프라인 오류(order_id=%s)", order_id)
        session.rollback()
        order = session.get(Order, order_id)
        if order is not None and order.status not in (
            OrderStatus.needs_review,
            OrderStatus.auto_confirmed,
            OrderStatus.confirmed,
        ):
            order.status = OrderStatus.ocr_failed
            session.commit()
    finally:
        session.close()


@router.post("/orders", response_model=OrderIntakeResponse, status_code=201)
async def create_order(
    image: Annotated[UploadFile, File()],
    lab_id: Annotated[int, Form()],
    session: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageClient, Depends(get_storage)],
    cache: Annotated[CacheClient, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    engine: Annotated[OCREngine, Depends(get_ocr_engine)],
    session_factory: Annotated[sessionmaker[Session], Depends(get_db_session_factory)],
    background_tasks: BackgroundTasks,
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

    # 응답(201) 직후 OCR→라우팅→스코어링 파이프라인 실행 — 프론트는 상태 폴링으로 추적
    background_tasks.add_task(
        _run_ocr_pipeline,
        order_id=result.order_id,
        session_factory=session_factory,
        engine=engine,
        storage=storage,
        settings=settings,
    )

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


# 재시도 금지 상태 — 라우팅 결과(order_fields)가 이미 존재해 재실행 시
# 사람이 수정/확정한 값까지 삭제·재생성되는 상태들 (REQ: OCR 실패 건 전용 재시도)
_RETRY_BLOCKED_STATUSES = (
    OrderStatus.needs_review,
    OrderStatus.auto_confirmed,
    OrderStatus.confirmed,
)


@router.post("/orders/{order_id}/retry-ocr", response_model=OCRRunResponse)
async def retry_ocr(
    order_id: int,
    session: Annotated[Session, Depends(get_db)],
    engine: Annotated[OCREngine, Depends(get_ocr_engine)],
    storage: Annotated[StorageClient, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> OCRRunResponse:
    order: Order | None = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"주문을 찾을 수 없음: {order_id}")
    if order.status in _RETRY_BLOCKED_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"재시도 불가 상태: {order.status.value} (OCR 실패 건만 재시도 가능)",
        )

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
