"""구조화 로깅(structlog) 설정.

local 환경은 콘솔 렌더러, 그 외(production 등)는 JSON 렌더러를 사용한다.
"""

from __future__ import annotations

import logging

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer()
        if settings.environment == "local"
        else structlog.processors.JSONRenderer(ensure_ascii=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
