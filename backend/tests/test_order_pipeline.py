"""OrderPipeline e2e 테스트 — Mock OCR + Mock LLM (외부 API 0).

전체 흐름, 상태 전이 순서, 필드 실패 격리, CLOVA 실패 → ocr_failed,
캐시 HIT 시 CLOVA 생략, 폴링 API, 검토 큐 정렬, 구조화 로깅.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest
import structlog.testing
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import (
    get_cache,
    get_db,
    get_order_pipeline,
    get_settings_dep,
    get_storage,
)
from app.core.config import Settings
from app.core.scoring import load_scoring_config
from app.db.base import Base
from app.db.models import Lab, Order
from app.domain.enums import FieldStatus, OrderStatus
from app.domain.errors import StorageError
from app.infra.cache import InMemoryCache
from app.infra.llm.base import RawStructuredOutput
from app.infra.ocr.base import OCRExtractionError, OCRField
from app.main import app
from app.services.dictionary import DictMatcher
from app.services.order_pipeline import OrderPipeline, ocr_cache_key
from app.services.scoring import persist_scored_fields, score_field
from tests.imaging_utils import sharp_jpeg

# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
HAPPY_FIELDS = [
    OCRField(field_key="clinic_name", text="서울미소치과", confidence=0.97),
    OCRField(field_key="patient_name", text="김민준", confidence=0.97),
    OCRField(field_key="tooth_numbers", text="11, 12", confidence=0.97),
    OCRField(field_key="due_date", text="2026-12-01", confidence=0.97),
    OCRField(field_key="prosthesis_type", text="크라운", confidence=0.97),
    OCRField(field_key="material", text="지르코니아", confidence=0.97),
    OCRField(field_key="shade", text="A2", confidence=0.97),
]


class FakeOCR:
    def __init__(self, fields: list[OCRField] | None = None, *, fail: bool = False) -> None:
        self._fields = fields if fields is not None else HAPPY_FIELDS
        self._fail = fail
        self.calls = 0

    async def extract(self, image_bytes: bytes, template_id: str) -> list[OCRField]:
        self.calls += 1
        if self._fail:
            raise OCRExtractionError("CLOVA down")
        return [f.model_copy() for f in self._fields]


class FakeLLM:
    """항상 성공하는 echo 구조화. fail_marker 포함 텍스트는 핸들러 예외 유발."""

    def __init__(self, fail_marker: str | None = None) -> None:
        self._fail_marker = fail_marker
        self.calls = 0

    async def structure(
        self, *, text: str, schema: Mapping[str, Any], model: str
    ) -> RawStructuredOutput:
        self.calls += 1
        if self._fail_marker and self._fail_marker in text:
            raise RuntimeError("unexpected handler crash")  # LLMCallError 아님 → 체인 밖 예외
        return RawStructuredOutput(
            data={"value": " ".join(text.split()), "confidence": 0.95}, model=model
        )


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get_object(self, key: str) -> bytes:
        if key not in self.objects:
            raise StorageError(f"missing {key}")
        return self.objects[key]

    def delete_object(self, key: str) -> None:
        self.objects.pop(key, None)


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
@dataclass
class Harness:
    sessions: sessionmaker[Session]
    storage: FakeStorage
    cache: InMemoryCache
    ocr: FakeOCR
    llm: FakeLLM
    settings: Settings

    def pipeline(self, *, ocr: FakeOCR | None = None, llm: FakeLLM | None = None) -> OrderPipeline:
        return OrderPipeline(
            session_factory=self.sessions,
            ocr=ocr or self.ocr,
            llm=llm or self.llm,
            storage=self.storage,
            cache=self.cache,
            matcher=DictMatcher.from_settings(self.settings),
            settings=self.settings,
            scoring_config=load_scoring_config(),
        )

    def seed_order(self, image: bytes = b"img-bytes", image_hash: str = "hash-1") -> int:
        with self.sessions() as s:
            lab = Lab(name="lab", template_id="tmpl-1")
            s.add(lab)
            s.flush()
            key = f"orders/{image_hash}.jpg"
            self.storage.put_object(key, image, "image/jpeg")
            order = Order(lab_id=lab.id, image_url=key, image_hash=image_hash)
            s.add(order)
            s.commit()
            return order.id


@pytest.fixture
def harness() -> Iterator[Harness]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield Harness(
        sessions=sessionmaker(bind=engine, expire_on_commit=False),
        storage=FakeStorage(),
        cache=InMemoryCache(),
        ocr=FakeOCR(),
        llm=FakeLLM(),
        settings=Settings(blur_laplacian_min=5.0, min_image_width=200, min_image_height=200),
    )
    engine.dispose()


# --------------------------------------------------------------------------- #
# e2e: 업로드 산출물(order) → auto_confirmed / needs_review 자동 진행
# --------------------------------------------------------------------------- #
async def test_e2e_auto_confirmed(harness: Harness) -> None:
    order_id = harness.seed_order()
    result = await harness.pipeline().run(order_id)

    assert result.status is OrderStatus.auto_confirmed
    assert result.field_count == len(HAPPY_FIELDS)
    assert result.llm_calls == 2  # C 필드 2개 × 경량 1회

    with harness.sessions() as s:
        order = s.get(Order, order_id)
        assert order is not None
        assert order.status is OrderStatus.auto_confirmed
        fields = {f.field_key: f for f in order.fields}
        # 4종 저장 확인 (대표 필드)
        shade = fields["shade"]
        assert shade.raw_text == "A2"
        assert shade.corrected_value == "A2"
        assert shade.score is not None and shade.score >= 0.95
        assert shade.score_components is not None
        assert shade.flags is not None and shade.flags["critical"] is True
        tooth = fields["tooth_numbers"]
        assert tooth.corrected_value == "11,12"
        clinic = fields["clinic_name"]
        assert clinic.corrected_by is not None  # llm


async def test_e2e_needs_review_on_bad_shade(harness: Harness) -> None:
    bad = [
        f if f.field_key != "shade" else OCRField(field_key="shade", text="Z9", confidence=0.97)
        for f in HAPPY_FIELDS
    ]
    order_id = harness.seed_order()
    result = await harness.pipeline(ocr=FakeOCR(bad)).run(order_id)

    assert result.status is OrderStatus.needs_review
    with harness.sessions() as s:
        order = s.get(Order, order_id)
        assert order is not None
        shade = next(f for f in order.fields if f.field_key == "shade")
        assert shade.status is FieldStatus.needs_review
        # 다른 필드는 정상 confirmed — 실패 전파 없음
        tooth = next(f for f in order.fields if f.field_key == "tooth_numbers")
        assert tooth.status is FieldStatus.confirmed


# --------------------------------------------------------------------------- #
# 상태 전이 순서
# --------------------------------------------------------------------------- #
async def test_status_transition_order(harness: Harness) -> None:
    order_id = harness.seed_order()
    result = await harness.pipeline().run(order_id)
    assert result.stages == [
        OrderStatus.preprocessing.value,
        OrderStatus.ocr_running.value,
        OrderStatus.routing.value,
        OrderStatus.auto_confirmed.value,
    ]


# --------------------------------------------------------------------------- #
# 필드 실패 격리
# --------------------------------------------------------------------------- #
async def test_field_failure_isolated(harness: Harness) -> None:
    """patient_name 핸들러가 폭발해도 의뢰서는 계속 — 해당 필드만 forced_hitl."""
    order_id = harness.seed_order()
    result = await harness.pipeline(llm=FakeLLM(fail_marker="김민준")).run(order_id)

    assert result.status is OrderStatus.needs_review  # 실패 필드 때문에 검토 큐
    with harness.sessions() as s:
        order = s.get(Order, order_id)
        assert order is not None
        assert len(order.fields) == len(HAPPY_FIELDS)  # 전 필드 저장됨(중단 없음)
        failed = next(f for f in order.fields if f.field_key == "patient_name")
        assert failed.status is FieldStatus.needs_review
        assert failed.flags is not None
        assert failed.flags["forced_hitl"] is True
        assert "handler_error" in failed.flags
        # 다른 C 필드는 정상 처리
        clinic = next(f for f in order.fields if f.field_key == "clinic_name")
        assert clinic.status is FieldStatus.confirmed


# --------------------------------------------------------------------------- #
# CLOVA 실패 → 의뢰서 전체 ocr_failed
# --------------------------------------------------------------------------- #
async def test_clova_failure_sets_ocr_failed(harness: Harness) -> None:
    order_id = harness.seed_order()
    result = await harness.pipeline(ocr=FakeOCR(fail=True)).run(order_id)

    assert result.status is OrderStatus.ocr_failed
    assert result.field_count == 0
    assert result.stages[-1] == OrderStatus.ocr_failed.value
    with harness.sessions() as s:
        order = s.get(Order, order_id)
        assert order is not None
        assert order.status is OrderStatus.ocr_failed
        assert order.fields == []


# --------------------------------------------------------------------------- #
# 이미지 해시 캐시 — HIT 시 CLOVA 생략, MISS 시 1회 호출 후 적재
# --------------------------------------------------------------------------- #
async def test_ocr_cache_hit_skips_clova(harness: Harness) -> None:
    order_id = harness.seed_order(image_hash="cached-hash")
    cached_json = "[" + ",".join(f.model_dump_json() for f in HAPPY_FIELDS) + "]"
    harness.cache.set(ocr_cache_key("cached-hash"), cached_json, 100)

    engine = FakeOCR(fail=True)  # 호출되면 실패 → 호출 안 됨을 보장
    result = await harness.pipeline(ocr=engine).run(order_id)

    assert result.ocr_cache_hit is True
    assert engine.calls == 0  # CLOVA 호출 생략
    assert result.status is OrderStatus.auto_confirmed


async def test_ocr_result_cached_after_run(harness: Harness) -> None:
    order_id = harness.seed_order(image_hash="fresh-hash")
    result = await harness.pipeline().run(order_id)
    assert result.ocr_cache_hit is False
    assert harness.ocr.calls == 1  # 의뢰서당 정확히 1회
    assert harness.cache.get(ocr_cache_key("fresh-hash")) is not None  # TTL 적재


# --------------------------------------------------------------------------- #
# 폴링 API + 검토 큐 정렬
# --------------------------------------------------------------------------- #
def test_upload_triggers_pipeline_then_poll(harness: Harness) -> None:
    """업로드(201) → BackgroundTasks 파이프라인 → GET 폴링으로 최종 상태 확인."""
    with harness.sessions() as s:
        s.add(Lab(name="lab"))
        s.commit()

    def _db() -> Iterator[Session]:
        s = harness.sessions()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_storage] = lambda: harness.storage
    app.dependency_overrides[get_cache] = lambda: harness.cache
    app.dependency_overrides[get_settings_dep] = lambda: harness.settings
    app.dependency_overrides[get_order_pipeline] = lambda: harness.pipeline()
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/orders",
            data={"lab_id": "1"},
            files={"image": ("req.jpg", sharp_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 201, resp.text
        order_id = resp.json()["order_id"]

        # TestClient 는 응답 후 BackgroundTasks 를 동기 실행 → 폴링으로 최종 상태 확인
        detail = client.get(f"/api/orders/{order_id}").json()
        assert detail["status"] in ("auto_confirmed", "needs_review")
        assert len(detail["fields"]) == len(HAPPY_FIELDS)
        assert {f["field_key"] for f in detail["fields"]} >= {"shade", "tooth_numbers"}
    finally:
        app.dependency_overrides.clear()


def test_review_queue_sorted_by_lowest_score(harness: Harness) -> None:
    """GET /api/orders?status=needs_review — 신뢰도 낮은 순."""
    config = load_scoring_config()
    with harness.sessions() as s:
        lab = Lab(name="lab")
        s.add(lab)
        s.flush()
        scores = {1: 0.50, 2: 0.30, 3: 0.70}
        for n, value in scores.items():
            order = Order(lab_id=lab.id, image_url=f"orders/{n}.jpg", image_hash=f"h{n}")
            s.add(order)
            s.flush()
            from app.domain.enums import CorrectedBy, FieldType
            from app.services.scoring import FieldScoreInput, ScoredFieldRecord

            record = ScoredFieldRecord(
                field_type=FieldType.C,
                score=score_field(
                    FieldScoreInput(
                        field_key="work_item_raw",
                        ocr_conf=value,
                        rule_pass=value,
                        dict_match=value,
                    ),
                    config,
                ),
                raw_text="x",
                corrected_value="x",
                corrected_by=CorrectedBy.system,
            )
            persist_scored_fields(s, order, [record])
        lab_id = lab.id

    def _db() -> Iterator[Session]:
        s = harness.sessions()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        body = client.get(f"/api/orders?status=needs_review&lab_id={lab_id}").json()
        assert [round(o["min_score"], 2) for o in body] == [0.30, 0.50, 0.70]  # 낮은 순
        assert all(o["status"] == "needs_review" for o in body)
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# 구조화 로깅 — order_id / 단계 / 소요시간 / LLM 호출 수
# --------------------------------------------------------------------------- #
async def test_structlog_events(harness: Harness) -> None:
    order_id = harness.seed_order()
    with structlog.testing.capture_logs() as logs:
        await harness.pipeline().run(order_id)

    stage_events = [e for e in logs if e["event"] == "stage_enter"]
    assert [e["stage"] for e in stage_events] == ["preprocessing", "ocr_running", "routing"]
    assert all(e["order_id"] == order_id for e in stage_events)

    done = next(e for e in logs if e["event"] == "pipeline_done")
    assert done["llm_calls"] == 2
    assert "duration_ms" in done

    ocr_done = next(e for e in logs if e["event"] == "stage_done" and e["stage"] == "ocr")
    assert "duration_ms" in ocr_done
