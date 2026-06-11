"""FastAPI 진입점 — CORS + /health (Step 0)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.orders import router as orders_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.scoring import get_scoring_config
from app.domain.errors import ImageValidationError
from app.schemas.orders import ImageRejectResponse


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title="DentalSync API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 시작 시점에 스코어링 설정을 1회 검증/로드(설정 오류를 부팅에서 조기 발견).
    get_scoring_config()

    async def on_image_validation_error(
        _request: Request, exc: ImageValidationError
    ) -> JSONResponse:
        body = ImageRejectResponse(
            error_code=str(exc.code), message=exc.message, guidance=exc.guidance
        )
        return JSONResponse(status_code=422, content=body.model_dump())

    app.add_exception_handler(ImageValidationError, on_image_validation_error)  # type: ignore[arg-type]

    app.include_router(health_router)
    app.include_router(orders_router)
    return app


app = create_app()
