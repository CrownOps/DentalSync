"""General 모드 업로드 파이프라인 — General OCR + LLM 문서 구조화 → needs_review.

외부 의존(R2/Redis/Postgres/CLOVA/OpenAI)은 Fake/InMemory/sqlite/Mock 으로 대체.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import (
    get_cache,
    get_db,
    get_db_session_factory,
    get_llm_structurer,
    get_ocr_engine,
    get_settings_dep,
    get_storage,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.models import Lab
from app.domain.enums import FieldStatus, OrderStatus
from app.infra.cache import InMemoryCache
from app.infra.llm.mock_structurer import MockLLMStructurer
from app.infra.ocr.mock_general import MockGeneralOCREngine
from app.main import app
from tests.imaging_utils import sharp_jpeg
from tests.test_orders_upload import FakeStorage


@pytest.fixture
def general_client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False)
    with session_local() as s:
        s.add(Lab(name="테스트기공소", code="lab1", password_hash="x"))
        s.commit()

    settings = Settings(
        ocr_mode="general",
        ocr_provider="mock",
        llm_provider="mock",
        blur_laplacian_min=5.0,
        min_image_width=200,
        min_image_height=200,
    )
    storage = FakeStorage()
    cache = InMemoryCache()

    def _db() -> Iterator[Session]:
        s = session_local()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_session_factory] = lambda: session_local
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_ocr_engine] = lambda: MockGeneralOCREngine()
    app.dependency_overrides[get_llm_structurer] = lambda: MockLLMStructurer()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _upload(client: TestClient) -> int:
    resp: httpx.Response = client.post(
        "/api/orders",
        data={"lab_id": "1"},
        files={"image": ("req.jpg", sharp_jpeg(), "image/jpeg")},
    )
    assert resp.status_code == 201, resp.text
    return int(resp.json()["order_id"])


def test_general_pipeline_structures_freeform_into_needs_review(
    general_client: TestClient,
) -> None:
    order_id = _upload(general_client)

    detail = general_client.get(f"/api/v1/review/{order_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    fields = {f["field_key"]: f for f in body["fields"]}

    # Mock General 텍스트("#36,37 지르코니아 크라운 / shade A3")가 구조화됨
    assert fields["shade"]["value"] == "A3"
    assert fields["tooth_numbers"]["value"] == "36 37"
    assert fields["material"]["value"] == "zirconia"
    assert "ocr_raw_text" in fields

    # 자유양식 → 추출 필드는 전부 needs_review (사람 확인)
    assert body["status"] == OrderStatus.needs_review.value


def test_general_pipeline_marks_llm_fields(general_client: TestClient) -> None:
    order_id = _upload(general_client)
    detail = general_client.get(f"/api/v1/review/{order_id}").json()
    by_key = {f["field_key"]: f for f in detail["fields"]}

    # 보철 형태는 LLM 구조화 산출 → structured_by_llm 플래그 + needs_review
    pc = by_key["prosthesis_category"]
    assert pc["flags"]["structured_by_llm"] is True
    assert pc["status"] == FieldStatus.needs_review.value


def test_general_pipeline_persists_core_fields(general_client: TestClient) -> None:
    order_id = _upload(general_client)
    detail = general_client.get(f"/api/v1/review/{order_id}").json()
    keys = {f["field_key"] for f in detail["fields"]}
    assert {"shade", "tooth_numbers", "material", "clinic_name", "ocr_raw_text"} <= keys
