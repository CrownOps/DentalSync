"""POST /api/orders 업로드 파이프라인 테스트.

정상 업로드 / 블러 반려 / 캐시 HIT·MISS / R2 실패 롤백 / lab 없음.
외부 의존(R2/Redis/Postgres)은 Fake/InMemory/sqlite 로 대체.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_cache, get_db, get_settings_dep, get_storage
from app.core.config import Settings
from app.db.base import Base
from app.db.models import Lab, Order
from app.domain.errors import StorageError
from app.infra.cache import InMemoryCache
from app.main import app
from app.services.hashing import sha256_hex
from app.services.order_intake import cache_key
from tests.imaging_utils import flat_jpeg, sharp_jpeg


class FakeStorage:
    """StorageClient 프로토콜 구현(테스트). fail_put 으로 R2 실패 시뮬레이션."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.fail_put = False

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        if self.fail_put:
            raise StorageError("R2 unavailable")
        self.objects[key] = data

    def delete_object(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)


@dataclass
class Harness:
    client: TestClient
    storage: FakeStorage
    cache: InMemoryCache
    sessions: sessionmaker[Session]


@pytest.fixture
def harness() -> Iterator[Harness]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    with session_local() as s:
        s.add(Lab(name="테스트기공소"))
        s.commit()

    storage = FakeStorage()
    cache = InMemoryCache()
    # 결정적 테스트: 임계값을 낮춰 합성 이미지가 통과하도록(블러는 별도 테스트)
    settings = Settings(blur_laplacian_min=5.0, min_image_width=200, min_image_height=200)

    def _db() -> Iterator[Session]:
        s = session_local()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_settings_dep] = lambda: settings
    try:
        yield Harness(TestClient(app), storage, cache, session_local)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _post(client: TestClient, data: bytes, lab_id: int = 1) -> httpx.Response:
    response: httpx.Response = client.post(
        "/api/orders",
        data={"lab_id": str(lab_id)},
        files={"image": ("req.jpg", data, "image/jpeg")},
    )
    return response


def test_normal_upload(harness: Harness) -> None:
    resp = _post(harness.client, sharp_jpeg())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "uploaded"
    assert body["cache_hit"] is False
    assert body["ocr_cached"] is False

    with harness.sessions() as s:
        assert s.query(Order).count() == 1
    assert len(harness.storage.objects) == 1  # R2 업로드됨


def test_blur_rejected_with_guidance(harness: Harness) -> None:
    resp = _post(harness.client, flat_jpeg())  # variance 0 < blur_min(5)
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "IMAGE_TOO_BLURRY"
    assert body["guidance"]  # 재촬영 안내
    with harness.sessions() as s:
        assert s.query(Order).count() == 0  # 검증 실패 → 저장 안 됨


def test_cache_miss(harness: Harness) -> None:
    resp = _post(harness.client, sharp_jpeg())
    body = resp.json()
    assert body["cache_hit"] is False
    assert body["ocr_cached"] is False


def test_cache_hit_sets_skip_flag(harness: Harness) -> None:
    data = sharp_jpeg()
    harness.cache.set(cache_key(sha256_hex(data)), '{"fields": []}', 100)

    resp = _post(harness.client, data)
    assert resp.status_code == 201
    body = resp.json()
    assert body["cache_hit"] is True
    assert body["ocr_cached"] is True  # CLOVA 호출 생략 플래그


def test_r2_failure_rolls_back(harness: Harness) -> None:
    harness.storage.fail_put = True
    resp = _post(harness.client, sharp_jpeg())
    assert resp.status_code == 502
    with harness.sessions() as s:
        assert s.query(Order).count() == 0  # 부분 저장 금지(롤백)


def test_lab_not_found(harness: Harness) -> None:
    resp = _post(harness.client, sharp_jpeg(), lab_id=999)
    assert resp.status_code == 404
