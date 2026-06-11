"""POST /api/orders/{id}/retry-ocr 테스트 — DI 로 OCR 엔진 교체/주입.

인터페이스 교체 가능성(Mock/Dummy 주입), OCR 실패 시 ocr_failed 전이를 검증.
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

from app.api.deps import get_db, get_ocr_engine, get_settings_dep, get_storage
from app.core.config import Settings
from app.db.base import Base
from app.db.models import Lab, Order
from app.domain.enums import OrderStatus
from app.infra.ocr.base import OCRField, OCRTransientError
from app.infra.ocr.mock import MockOCREngine
from app.main import app


class _FakeStorage:
    def __init__(self, data: bytes = b"image-bytes") -> None:
        self._data = data

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self._data = data

    def get_object(self, key: str) -> bytes:
        return self._data

    def delete_object(self, key: str) -> None:
        pass

    def generate_presigned_url(self, key: str, expires: int = 300) -> str:
        return f"https://fake-r2/{key}"


class _FailingEngine:
    """OCREngine 구현 — 항상 실패(일시적 오류)."""

    async def extract(self, image_bytes: bytes, template_id: str) -> list[OCRField]:
        raise OCRTransientError("always fails")


class _DummyEngine:
    """OCREngine 구현 — 임의 필드 반환(인터페이스 교체 가능성 입증)."""

    async def extract(self, image_bytes: bytes, template_id: str) -> list[OCRField]:
        return [OCRField(field_key="custom_field", text="X", confidence=0.42)]


@dataclass
class Harness:
    client: TestClient
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
        lab = Lab(name="lab", template_id="tmpl-1")
        s.add(lab)
        s.flush()
        s.add(Order(id=1, lab_id=lab.id, image_url="orders/abc.jpg", image_hash="h"))
        s.commit()

    def _db() -> Iterator[Session]:
        s = session_local()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_storage] = lambda: _FakeStorage()
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    try:
        yield Harness(TestClient(app), session_local)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _order_status(harness: Harness) -> OrderStatus:
    with harness.sessions() as s:
        order = s.get(Order, 1)
        assert order is not None
        return order.status


def test_retry_ocr_success_with_mock_engine(harness: Harness) -> None:
    app.dependency_overrides[get_ocr_engine] = lambda: MockOCREngine()
    resp: httpx.Response = harness.client.post("/api/orders/1/retry-ocr")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 라우팅 결과 저장까지 연결되어 needs_review | auto_confirmed 로 전이된다
    assert body["status"] in ("needs_review", "auto_confirmed")
    assert body["field_count"] > 0
    assert _order_status(harness) in (OrderStatus.needs_review, OrderStatus.auto_confirmed)


def test_interface_swap_with_dummy_engine(harness: Harness) -> None:
    app.dependency_overrides[get_ocr_engine] = lambda: _DummyEngine()
    resp: httpx.Response = harness.client.post("/api/orders/1/retry-ocr")
    assert resp.status_code == 200, resp.text
    assert resp.json()["field_count"] == 1  # DummyEngine 의 단일 필드


def test_retry_ocr_failure_sets_ocr_failed(harness: Harness) -> None:
    app.dependency_overrides[get_ocr_engine] = lambda: _FailingEngine()
    resp: httpx.Response = harness.client.post("/api/orders/1/retry-ocr")
    assert resp.status_code == 502
    assert _order_status(harness) is OrderStatus.ocr_failed


def test_retry_ocr_order_not_found(harness: Harness) -> None:
    app.dependency_overrides[get_ocr_engine] = lambda: MockOCREngine()
    resp: httpx.Response = harness.client.post("/api/orders/999/retry-ocr")
    assert resp.status_code == 404
