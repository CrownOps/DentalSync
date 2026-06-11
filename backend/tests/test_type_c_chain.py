"""승급 체인 상태 머신 테스트 — 모든 분기 + 비용 가드.

FakeStructurer(LLMStructurer Protocol 구현)를 주입해 외부 API 없이 검증한다.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import pytest

from app.core.config import Settings
from app.infra.llm.base import LLMCallError, LLMRefusalError, RawStructuredOutput
from app.services.type_c_structuring import (
    ChainStage,
    TypeCRatioMonitor,
    structure_type_c,
)

OK = {"value": "교합 높지 않게", "confidence": 0.9}
BAD_CONFIDENCE = {"value": "x", "confidence": 1.5}  # pydantic 범위 위반
BLANK_VALUE = {"value": "   ", "confidence": 0.9}  # 도메인 제약 위반(빈 값)


class FakeStructurer:
    """LLMStructurer 구현 — 시나리오 스크립트(dict=성공, Exception=실패) 재생."""

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def structure(
        self, *, text: str, schema: Mapping[str, Any], model: str
    ) -> RawStructuredOutput:
        self.calls.append({"text": text, "model": model, "schema": dict(schema)})
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return RawStructuredOutput(data=item, model=model)


def _settings(**kwargs: Any) -> Settings:
    return Settings(
        llm_model_primary="model-primary",
        llm_model_escalation="model-escalation",
        **kwargs,
    )


async def _run(fake: FakeStructurer, settings: Settings | None = None) -> Any:
    return await structure_type_c(
        structurer=fake,
        field_key="request_note",
        raw_text="교합 높지않게 부탁드립니다",
        settings=settings or _settings(),
    )


# --- 1) 정상 구조화 ----------------------------------------------------------
async def test_primary_success() -> None:
    fake = FakeStructurer([OK])
    out = await _run(fake)
    assert out.value == "교합 높지 않게"
    assert out.call_count == 1
    assert out.model_used == "model-primary"
    assert out.flags == {"model_escalated": False, "forced_hitl": False}
    assert out.rule_pass == pytest.approx(0.9)  # 검증통과(1.0) × confidence(0.9)
    assert [a.stage for a in out.attempts] == [ChainStage.primary]


# --- 2) 검증 실패 → 경량 재시도 성공 ----------------------------------------
async def test_validation_failure_then_retry_success() -> None:
    fake = FakeStructurer([BAD_CONFIDENCE, OK])
    out = await _run(fake)
    assert out.value == "교합 높지 않게"
    assert out.call_count == 2
    assert out.flags["model_escalated"] is False
    assert out.flags["forced_hitl"] is False
    assert [c["model"] for c in fake.calls] == ["model-primary", "model-primary"]
    assert [a.ok for a in out.attempts] == [False, True]


async def test_refusal_then_retry_success() -> None:
    fake = FakeStructurer([LLMRefusalError("거부"), OK])
    out = await _run(fake)
    assert out.call_count == 2
    assert out.value == "교합 높지 않게"
    assert out.attempts[0].error is not None


async def test_blank_value_is_domain_violation() -> None:
    """빈 문자열 값은 2차 방어(pydantic)가 잡아 재시도를 유발한다."""
    fake = FakeStructurer([BLANK_VALUE, OK])
    out = await _run(fake)
    assert out.call_count == 2
    assert out.attempts[0].ok is False


# --- 3) 재시도 실패 → 상위 모델 승급 성공 ------------------------------------
async def test_escalation_success_forces_hitl() -> None:
    fake = FakeStructurer([LLMCallError("fail1"), BAD_CONFIDENCE, OK])
    out = await _run(fake)
    assert out.value == "교합 높지 않게"
    assert out.call_count == 3
    assert out.model_used == "model-escalation"
    assert out.flags == {"model_escalated": True, "forced_hitl": True}  # 점수 무관 HITL
    assert out.rule_pass == pytest.approx(0.9)
    assert [a.stage for a in out.attempts] == [
        ChainStage.primary,
        ChainStage.primary_retry,
        ChainStage.escalation,
    ]


# --- 4) 상위 모델도 실패 → raw 만 저장 + HITL --------------------------------
async def test_total_failure_keeps_raw_and_forces_hitl() -> None:
    fake = FakeStructurer([LLMCallError("1"), LLMCallError("2"), LLMRefusalError("3")])
    out = await _run(fake)
    assert out.value is None
    assert out.raw_text == "교합 높지않게 부탁드립니다"  # raw 보존(저장 대상)
    assert out.rule_pass == 0.0
    assert out.confidence == 0.0
    assert out.call_count == 3
    assert out.flags["forced_hitl"] is True
    assert out.succeeded is False
    assert all(a.ok is False for a in out.attempts)


# --- 5) 모델 교체 가능성 — 설정만 바꿔도 체인 로직 무변 -----------------------
async def test_model_swap_via_settings_only() -> None:
    """모델명을 바꿔도 호출 패턴(상태 머신)은 동일 — 설정 변경만으로 교체 가능."""
    swapped = Settings(
        llm_model_primary="vendor-x-light",
        llm_model_escalation="vendor-x-heavy",
    )
    fake = FakeStructurer([LLMCallError("1"), LLMCallError("2"), OK])
    out = await _run(fake, settings=swapped)
    # 체인 로직 무변: primary 2회 → escalation 1회
    assert [c["model"] for c in fake.calls] == [
        "vendor-x-light",
        "vendor-x-light",
        "vendor-x-heavy",
    ]
    assert out.model_used == "vendor-x-heavy"
    assert out.flags["model_escalated"] is True


# --- 비용 가드 ---------------------------------------------------------------
async def test_cost_logging(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="dentalsync.type_c"):
        await _run(FakeStructurer([OK]))
    record = next(r for r in caplog.records if "type_c_llm" in r.message)
    assert "calls=1" in record.getMessage()
    assert "model-primary" in record.getMessage()


def test_ratio_monitor_warns_when_exceeded(caplog: pytest.LogCaptureFixture) -> None:
    monitor = TypeCRatioMonitor(design_ratio=0.25, warn_margin=0.15, min_samples=10)
    with caplog.at_level(logging.WARNING, logger="dentalsync.type_c"):
        for _ in range(10):
            monitor.record(used_llm=True)  # 100% ≫ 40%
    assert any("type_c_ratio_exceeded" in r.message for r in caplog.records)
    assert monitor.observed_ratio == 1.0


def test_ratio_monitor_quiet_within_design(caplog: pytest.LogCaptureFixture) -> None:
    monitor = TypeCRatioMonitor(design_ratio=0.25, warn_margin=0.15, min_samples=10)
    with caplog.at_level(logging.WARNING, logger="dentalsync.type_c"):
        for i in range(20):
            monitor.record(used_llm=(i % 5 == 0))  # 20% < 40%
    assert not any("type_c_ratio_exceeded" in r.message for r in caplog.records)


def test_ratio_monitor_respects_min_samples(caplog: pytest.LogCaptureFixture) -> None:
    monitor = TypeCRatioMonitor(design_ratio=0.25, warn_margin=0.15, min_samples=50)
    with caplog.at_level(logging.WARNING, logger="dentalsync.type_c"):
        for _ in range(10):
            monitor.record(used_llm=True)
    assert not any("type_c_ratio_exceeded" in r.message for r in caplog.records)
