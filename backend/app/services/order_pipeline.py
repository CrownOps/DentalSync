"""OrderPipeline — Step 2~7 을 연결하는 오케스트레이터.

업로드 완료 후 FastAPI BackgroundTasks 로 비동기 실행한다 (QStash 금지 — Phase 1 결정).

흐름(각 단계 진입 시 orders.status 갱신·커밋 → 폴링 API 가 진행 상황을 본다):
    preprocessing → ocr_running(CLOVA 1회 또는 캐시 재사용) → routing
    (A→마킹/선택지 검증, B→룰 엔진, SHADE→색상/사전, C→LLM 승급 체인)
    → 스코어링 → 분기 → DB 저장(auto_confirmed / needs_review)

실패 정책:
- 필드 단위 실패는 격리(try/except) — 해당 필드만 forced_hitl, 의뢰서는 계속 진행.
- CLOVA 호출/스토리지 실패는 의뢰서 전체 ocr_failed.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import structlog
from pydantic import TypeAdapter
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.models import Lab, Order
from app.domain.enums import CorrectedBy, FieldType, OrderStatus
from app.domain.errors import OrderNotFoundError, StorageError
from app.domain.scoring import ScoringConfig
from app.infra.cache import CacheClient
from app.infra.llm.base import LLMStructurer
from app.infra.ocr.base import OCREngine, OCRExtractionError, OCRField
from app.infra.storage import StorageClient
from app.services import type_b_rules
from app.services.dictionary import DictMatcher
from app.services.scoring import (
    FieldScoreInput,
    ScoredFieldRecord,
    persist_scored_fields,
    score_field,
)
from app.services.template_routing import FieldRoute, load_field_routes
from app.services.type_c_structuring import TypeCRatioMonitor, structure_type_c

logger = structlog.get_logger("dentalsync.pipeline")

_OCR_FIELDS_ADAPTER = TypeAdapter(list[OCRField])


def ocr_cache_key(image_hash: str) -> str:
    return f"imgocr:{image_hash}"


@dataclass
class PipelineRunResult:
    order_id: int
    status: OrderStatus
    field_count: int
    llm_calls: int
    ocr_cache_hit: bool
    stages: list[str] = field(default_factory=list)  # 상태 전이 궤적(테스트/관측용)


@dataclass
class _HandlerOut:
    corrected_value: str | None
    rule_pass: float
    dict_match: float | None
    corrected_by: CorrectedBy | None
    forced_hitl: bool = False
    extra_flags: dict[str, Any] = field(default_factory=dict)
    llm_calls: int = 0


class OrderPipeline:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        ocr: OCREngine,
        llm: LLMStructurer,
        storage: StorageClient,
        cache: CacheClient,
        matcher: DictMatcher,
        settings: Settings,
        scoring_config: ScoringConfig,
        routes: dict[str, FieldRoute] | None = None,
        monitor: TypeCRatioMonitor | None = None,
    ) -> None:
        self._sf = session_factory
        self._ocr = ocr
        self._llm = llm
        self._storage = storage
        self._cache = cache
        self._matcher = matcher
        self._settings = settings
        self._scoring = scoring_config
        self._routes = routes or load_field_routes()
        self._monitor = monitor

    # ------------------------------------------------------------------ #
    # 실행
    # ------------------------------------------------------------------ #
    async def run(self, order_id: int) -> PipelineRunResult:
        log = logger.bind(order_id=order_id)
        stages: list[str] = []
        started = time.monotonic()

        with self._sf() as session:
            order = session.get(Order, order_id)
            if order is None:
                raise OrderNotFoundError(order_id)

            # --- 1) preprocessing -------------------------------------------
            self._set_status(session, order, OrderStatus.preprocessing, stages, log)
            try:
                image_bytes = self._storage.get_object(order.image_url)
            except StorageError as exc:
                return self._fail_ocr(session, order, stages, log, reason=str(exc))

            # --- 2) ocr_running (CLOVA 1회 또는 캐시) -------------------------
            self._set_status(session, order, OrderStatus.ocr_running, stages, log)
            t_ocr = time.monotonic()
            try:
                ocr_fields, cache_hit = await self._run_ocr(session, order, image_bytes)
            except OCRExtractionError as exc:
                return self._fail_ocr(session, order, stages, log, reason=str(exc))
            log.info(
                "stage_done",
                stage="ocr",
                duration_ms=int((time.monotonic() - t_ocr) * 1000),
                cache_hit=cache_hit,
                field_count=len(ocr_fields),
            )

            # --- 3) routing + 스코어링 (필드 실패 격리) ------------------------
            self._set_status(session, order, OrderStatus.routing, stages, log)
            t_route = time.monotonic()
            records, llm_calls = await self._route_fields(order, ocr_fields, log)
            log.info(
                "stage_done",
                stage="routing",
                duration_ms=int((time.monotonic() - t_route) * 1000),
                llm_calls=llm_calls,
            )

            # --- 4) 분기 + 저장(4종 일괄) ------------------------------------
            final = persist_scored_fields(session, order, records)
            stages.append(final.value)

        if self._monitor is not None:
            self._monitor.record(used_llm=llm_calls > 0)

        log.info(
            "pipeline_done",
            status=final.value,
            field_count=len(records),
            llm_calls=llm_calls,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return PipelineRunResult(
            order_id=order_id,
            status=final,
            field_count=len(records),
            llm_calls=llm_calls,
            ocr_cache_hit=cache_hit,
            stages=stages,
        )

    async def run_safe(self, order_id: int) -> None:
        """BackgroundTasks 진입점 — 예외를 로그로 흡수(요청 응답과 무관)."""
        try:
            await self.run(order_id)
        except Exception:
            logger.bind(order_id=order_id).exception("pipeline_crashed")

    # ------------------------------------------------------------------ #
    # 단계 구현
    # ------------------------------------------------------------------ #
    def _set_status(
        self,
        session: Session,
        order: Order,
        status: OrderStatus,
        stages: list[str],
        log: Any,
    ) -> None:
        order.status = status
        session.commit()  # 폴링 API 가 단계 진행을 즉시 보도록 단계마다 커밋
        stages.append(status.value)
        log.info("stage_enter", stage=status.value)

    def _fail_ocr(
        self,
        session: Session,
        order: Order,
        stages: list[str],
        log: Any,
        *,
        reason: str,
    ) -> PipelineRunResult:
        order.status = OrderStatus.ocr_failed
        session.commit()
        stages.append(OrderStatus.ocr_failed.value)
        log.error("pipeline_failed", stage="ocr", reason=reason)
        return PipelineRunResult(
            order_id=order.id,
            status=OrderStatus.ocr_failed,
            field_count=0,
            llm_calls=0,
            ocr_cache_hit=False,
            stages=stages,
        )

    async def _run_ocr(
        self, session: Session, order: Order, image_bytes: bytes
    ) -> tuple[list[OCRField], bool]:
        """이미지 해시 캐시 HIT 면 CLOVA 호출 생략, MISS 면 1회 호출 후 캐시 적재."""
        key = ocr_cache_key(order.image_hash)
        cached = self._cache.get(key)
        if cached is not None:
            return _OCR_FIELDS_ADAPTER.validate_json(cached), True

        lab = session.get(Lab, order.lab_id)
        template_id = (
            lab.template_id if lab and lab.template_id else ""
        ) or self._settings.clova_template_id

        fields = await self._ocr.extract(image_bytes, template_id)  # 의뢰서당 1회
        self._cache.set(
            key,
            json.dumps([f.model_dump() for f in fields], ensure_ascii=False),
            self._settings.image_cache_ttl_seconds,
        )
        return fields, False

    async def _route_fields(
        self, order: Order, ocr_fields: list[OCRField], log: Any
    ) -> tuple[list[ScoredFieldRecord], int]:
        records: list[ScoredFieldRecord] = []
        llm_calls = 0

        for ocr_field in ocr_fields:
            route = self._routes.get(ocr_field.field_key)
            if route is None:
                log.info("field_skipped", field=ocr_field.field_key, reason="unmapped")
                continue

            try:
                out = await self._dispatch(route, ocr_field, order)
            except Exception as exc:
                log.warning(
                    "field_failed", field=ocr_field.field_key, error=str(exc)
                )
                out = _HandlerOut(
                    corrected_value=None,
                    rule_pass=0.0,
                    dict_match=None,
                    corrected_by=None,
                    forced_hitl=True,
                    extra_flags={"handler_error": str(exc)},
                )

            llm_calls += out.llm_calls
            score = score_field(
                FieldScoreInput(
                    field_key=route.field_key,
                    ocr_conf=ocr_field.confidence,
                    rule_pass=out.rule_pass,
                    dict_match=out.dict_match,
                    forced_hitl=out.forced_hitl,
                    extra_flags=out.extra_flags,
                ),
                self._scoring,
            )
            records.append(
                ScoredFieldRecord(
                    field_type=route.field_type,
                    score=score,
                    raw_text=ocr_field.text,
                    raw_bbox=ocr_field.bbox,
                    corrected_value=out.corrected_value,
                    corrected_by=out.corrected_by,
                )
            )
        return records, llm_calls

    # --- 타입별 핸들러 ---------------------------------------------------- #
    async def _dispatch(
        self, route: FieldRoute, ocr_field: OCRField, order: Order
    ) -> _HandlerOut:
        if route.field_type is FieldType.B:
            return self._handle_type_b(route, ocr_field.text, order)
        if route.field_type in (FieldType.A, FieldType.SHADE):
            return self._handle_choice(route, ocr_field.text)
        return await self._handle_type_c(route, ocr_field.text)

    def _handle_type_b(self, route: FieldRoute, text: str, order: Order) -> _HandlerOut:
        """B: 결정론적 룰 엔진(치식/날짜/납기). LLM 0회."""
        if route.field_key == "tooth_numbers":
            tooth = type_b_rules.score_tooth_numbers(text)
            return _HandlerOut(
                corrected_value=",".join(tooth.teeth) or None,
                rule_pass=tooth.rule_pass,
                dict_match=None,
                corrected_by=CorrectedBy.system,
            )
        if route.field_key == "due_date":
            due = type_b_rules.score_due_date(text, order.received_at)
            return _HandlerOut(
                corrected_value=due.iso,
                rule_pass=due.rule_pass,
                dict_match=None,
                corrected_by=CorrectedBy.system,
            )
        parsed = type_b_rules.score_date(text)
        return _HandlerOut(
            corrected_value=parsed.iso,
            rule_pass=parsed.rule_pass,
            dict_match=None,
            corrected_by=CorrectedBy.system,
        )

    def _handle_choice(self, route: FieldRoute, text: str) -> _HandlerOut:
        """A/SHADE: 선택지·사전 기반 결정론 검증. LLM 0회.

        사전 카테고리가 있으면 표준어 정규화 + 멤버십을 rule_pass 로 사용.
        (템플릿 bbox 기반 마킹/색상 감지는 bbox 정의가 제공되는 템플릿에서
        marking_detection/shade_detection 모듈로 대체된다 — Phase 1 기본 경로는 사전.)
        """
        cleaned = " ".join(text.split()).strip()
        if route.dict_category and self._matcher.applies(route.dict_category):
            match = self._matcher.match(route.dict_category, cleaned)
            matched = match.matched_term is not None
            return _HandlerOut(
                corrected_value=match.matched_term if matched else (cleaned or None),
                rule_pass=1.0 if matched else 0.0,
                dict_match=match.score,
                corrected_by=CorrectedBy.system,
            )
        # 사전 미보유 선택지: 파싱은 됐으나 검증 기준 없음 → 부분 통과
        return _HandlerOut(
            corrected_value=cleaned or None,
            rule_pass=0.5 if cleaned else 0.0,
            dict_match=None,
            corrected_by=CorrectedBy.system,
        )

    async def _handle_type_c(self, route: FieldRoute, text: str) -> _HandlerOut:
        """C: LLM 승급 체인(텍스트 전용)."""
        outcome = await structure_type_c(
            structurer=self._llm,
            field_key=route.field_key,
            raw_text=text,
            settings=self._settings,
        )
        return _HandlerOut(
            corrected_value=outcome.value,
            rule_pass=outcome.rule_pass,
            dict_match=None,
            corrected_by=CorrectedBy.llm if outcome.succeeded else None,
            forced_hitl=bool(outcome.flags.get("forced_hitl")),
            extra_flags={"model_escalated": outcome.flags.get("model_escalated", False)},
            llm_calls=outcome.call_count,
        )
