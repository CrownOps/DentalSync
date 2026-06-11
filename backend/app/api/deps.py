"""FastAPI 의존성 — DB 세션 / 스토리지 / 캐시 / 설정.

기본 구현은 운영 백엔드(R2/Redis)를 생성한다. 테스트는 이 의존성들을
override 하여 외부 의존 없이 동작한다.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.infra.cache import CacheClient, RedisCache
from app.infra.ocr.base import OCREngine
from app.infra.ocr.clova import CLOVAOCREngine
from app.infra.storage import R2Storage, StorageClient


def get_settings_dep() -> Settings:
    return get_settings()


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_storage(settings: Settings = Depends(get_settings_dep)) -> StorageClient:  # noqa: B008
    return R2Storage.from_settings(settings)


def get_cache(settings: Settings = Depends(get_settings_dep)) -> CacheClient:  # noqa: B008
    return RedisCache.from_url(settings.redis_url)


def get_ocr_engine(settings: Settings = Depends(get_settings_dep)) -> OCREngine:  # noqa: B008
    # 구체 엔진 선택은 API(조립) 레이어에서만. 서비스는 OCREngine 인터페이스에만 의존.
    return CLOVAOCREngine.from_settings(settings)
