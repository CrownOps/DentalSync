"""FastAPI 진입점 — CORS + /health (Step 0)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.api.health import router as health_router
from app.api.orders import router as orders_router
from app.api.v1.review import router as review_router
from app.core.config import get_settings
from app.core.scoring import get_scoring_config
from app.domain.errors import ImageValidationError
from app.schemas.orders import ImageRejectResponse

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
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

    async def on_database_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        # DB 예외를 명시적 타입으로 처리해야 ExceptionMiddleware(=CORS 미들웨어 안쪽)에서
        # 응답이 만들어져 CORS 헤더가 붙는다. 미처리로 두면 ServerErrorMiddleware(CORS 바깥)가
        # 500을 만들어 브라우저가 'No Access-Control-Allow-Origin'(CORS 차단)으로 오인한다.
        logger.exception("Database error: %s", exc)
        if isinstance(exc, OperationalError):
            # 연결 실패/타임아웃 등 일시적 장애 → 재시도 가능
            msg = "데이터베이스에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
            return JSONResponse(status_code=503, content={"detail": msg})
        # 스키마 누락(ProgrammingError) 등 서버 측 DB 오류
        return JSONResponse(
            status_code=500, content={"detail": "데이터베이스 처리 중 오류가 발생했습니다."}
        )

    async def on_unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
        # CORS 미들웨어가 헤더를 붙일 수 있도록 예외를 JSONResponse로 변환
        logger.exception("Unhandled server error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.add_exception_handler(ImageValidationError, on_image_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(SQLAlchemyError, on_database_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, on_unhandled_error)

    app.include_router(health_router)
    app.include_router(orders_router)
    app.include_router(review_router)

    # storage_backend=local: LocalDirStorage 가 만드는 URL(/local-files/)을 서빙
    if settings.storage_backend == "local":
        settings.local_storage_dir.mkdir(parents=True, exist_ok=True)
        app.mount(
            "/local-files",
            StaticFiles(directory=settings.local_storage_dir),
            name="local-files",
        )
    return app


app = create_app()
