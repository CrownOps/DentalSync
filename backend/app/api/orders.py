"""의뢰서 업로드 엔드포인트 — POST /api/orders (multipart)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_cache, get_db, get_settings_dep, get_storage
from app.core.config import Settings
from app.domain.errors import LabNotFoundError, StorageError
from app.infra.cache import CacheClient
from app.infra.storage import StorageClient
from app.schemas.orders import OrderIntakeResponse
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
