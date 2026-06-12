"""FastAPI 의존성 — DB 세션 / 스토리지 / 캐시 / 설정.

기본 구현은 운영 백엔드(R2/Redis)를 생성한다. 테스트는 이 의존성들을
override 하여 외부 의존 없이 동작한다.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.infra.cache import CacheClient, InMemoryCache, RedisCache
from app.infra.llm.base import LLMStructurer
from app.infra.llm.openai_structurer import OpenAIStructurer
from app.infra.ocr.base import OCREngine
from app.infra.ocr.clova import CLOVAOCREngine
from app.infra.ocr.mock import MockOCREngine
from app.infra.storage import LocalDirStorage, R2Storage, StorageClient


def get_settings_dep() -> Settings:
    return get_settings()


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_db_session_factory() -> sessionmaker[Session]:
    """백그라운드 태스크용 세션 팩토리.

    요청 스코프 세션(get_db)은 응답 직후 닫히므로, 응답 이후 실행되는
    BackgroundTasks 는 이 팩토리로 자체 세션을 생성해야 한다.
    """
    return get_session_factory()


def get_storage(settings: Settings = Depends(get_settings_dep)) -> StorageClient:  # noqa: B008
    if settings.storage_backend == "local":
        return LocalDirStorage.from_settings(settings)
    return R2Storage.from_settings(settings)


# memory 캐시는 요청 간 공유되어야 하므로 프로세스 싱글턴으로 유지
_memory_cache: InMemoryCache | None = None


def get_cache(settings: Settings = Depends(get_settings_dep)) -> CacheClient:  # noqa: B008
    if settings.cache_backend == "memory":
        global _memory_cache
        if _memory_cache is None:
            _memory_cache = InMemoryCache()
        return _memory_cache
    return RedisCache.from_url(settings.redis_url)


def get_ocr_engine(settings: Settings = Depends(get_settings_dep)) -> OCREngine:  # noqa: B008
    # 구체 엔진 선택은 API(조립) 레이어에서만. 서비스는 OCREngine 인터페이스에만 의존.
    if settings.ocr_provider == "mock":
        return MockOCREngine()
    return CLOVAOCREngine.from_settings(settings)


def get_llm_structurer(settings: Settings = Depends(get_settings_dep)) -> LLMStructurer:  # noqa: B008
    # 서비스는 LLMStructurer 인터페이스에만 의존 — 벤더 교체 시 이 함수만 변경.
    return OpenAIStructurer.from_settings(settings)


# --- 인증 (Phase 1: 단일 베어러 토큰. Phase 2 에서 RBAC 으로 이 dependency 만 교체) ---

_bearer_scheme = HTTPBearer(auto_error=False)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),  # noqa: B008
    settings: Settings = Depends(get_settings_dep),  # noqa: B008
) -> None:
    """API 인증 검증.

    api_auth_token 미설정(로컬 개발)이면 통과. 설정 시 Bearer 토큰 일치 필수.
    Phase 2: 이 dependency 를 lab/role 기반 검증으로 교체한다 — 라우터는 변경 불필요.
    """
    if not settings.api_auth_token:
        return
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, settings.api_auth_token
    ):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "인증 실패", "details": []}},
        )
