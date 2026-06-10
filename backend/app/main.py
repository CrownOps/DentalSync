"""FastAPI 진입점 — CORS + /health (Step 0)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.scoring import get_scoring_config


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

    app.include_router(health_router)
    return app


app = create_app()
