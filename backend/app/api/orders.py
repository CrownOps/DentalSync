"""의뢰서 업로드 엔드포인트 — POST /api/orders (multipart)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import (
    get_cache,
    get_db,
    get_ocr_engine,
    get_settings_dep,
    get_storage,
)
from app.core.config import Settings
from app.domain.errors import (
    LabNotFoundError,
    OrderNotFoundError,
    StorageError,
)
from app.infra.cache import CacheClient
from app.infra.ocr.base import OCREngine, OCRExtractionError
from app.infra.storage import StorageClient
from app.schemas.orders import OCRRunResponse, OrderIntakeResponse
from app.services.ocr_runner import run_ocr
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
