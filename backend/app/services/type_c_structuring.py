"""Type C 자유텍스트 → JSON 구조화 승급 체인 (상태 머신).

서비스는 LLMStructurer 인터페이스에만 의존한다(벤더 무관). 모델명은 Settings 에서
로드하며 하드코딩하지 않는다.

상태 전이:
    PRIMARY ──검증실패/refusal──▶ PRIMARY_RETRY ──실패──▶ ESCALATION ──실패──▶ FAILED
       │성공                         │성공                  │성공(승급)
       ▼                            ▼                     ▼
      OK                           OK            OK + model_escalated + forced_hitl

- 승급 성공: flags.model_escalated=true + forced_hitl=true (점수 무관 HITL)
- 최종 실패: value 없음(raw 만 저장 대상) + forced_hitl=true
- rule_pass = 스키마 검증 통과(1.0/0.0) × LLM 자기보고 confidence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.config import Settings
from app.infra.llm.base import LLMCallError, LLMStructurer

logger = logging.getLogger("dentalsync.type_c")

PASS_FAIL = 0.0

# Structured Outputs strict 모드 요구사항: 전 프로퍼티 required + additionalProperties false
TYPE_C_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "value": {
            "type": ["string", "null"],
            "description": "추출/정규화된 필드 값. 원문에 정보가 없으면 null.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "추출 확신도 자기보고 (0~1)",
        },
    },
    "required": ["value", "confidence"],
    "additionalProperties": False,
}


class TypeCExtraction(BaseModel):
    """2차 방어 — Structured Outputs 가 통과시킨 출력도 다시 검증한다."""

    model_config = ConfigDict(extra="forbid")

    value: str | None
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("value")
    @classmethod
    def _reject_blank(cls, v: str | None) -> str | None:
        # 빈 문자열은 '값 없음'을 가장한 도메인 제약 위반 — null 을 쓰도록 강제
        if v is not None and not v.strip():
            raise ValueError("빈 문자열 값은 허용하지 않음(null 사용)")
        return v


class ChainStage(StrEnum):
    primary = "primary"
    primary_retry = "primary_retry"
    escalation = "escalation"


@dataclass(frozen=True)
class AttemptLog:
    stage: ChainStage
    model: str
    ok: bool
    error: str | None = None


@dataclass
class TypeCOutcome:
    """스코어링/저장 단계에서 그대로 합성 가능한 결과."""

    field_key: str
    raw_text: str
    value: str | None
    confidence: float
    rule_pass: float
    model_used: str | None
    call_count: int
    flags: dict[str, Any]
    attempts: list[AttemptLog] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        # value=null 도 유효한 구조화 결과(원문에 정보 없음) — 성공 시도 여부로 판정
        return any(a.ok for a in self.attempts)


def _validate(data: dict[str, Any]) -> TypeCExtraction:
    """pydantic 2차 방어: refusal 잔재/빈 값/범위 위반 감지."""
    return TypeCExtraction.model_validate(data)


async def structure_type_c(
    *,
    structurer: LLMStructurer,
    field_key: str,
    raw_text: str,
    settings: Settings,
    schema: dict[str, Any] | None = None,
) -> TypeCOutcome:
    """승급 체인 실행. 단계 계획: primary → primary_retry → escalation."""
    target_schema = schema or TYPE_C_SCHEMA
    plan: tuple[tuple[ChainStage, str], ...] = (
        (ChainStage.primary, settings.llm_model_primary),
        (ChainStage.primary_retry, settings.llm_model_primary),
        (ChainStage.escalation, settings.llm_model_escalation),
    )

    attempts: list[AttemptLog] = []
    call_count = 0

    for stage, model in plan:
        call_count += 1
        try:
            raw = await structurer.structure(text=raw_text, schema=target_schema, model=model)
            extraction = _validate(raw.data)
        except (LLMCallError, ValidationError) as exc:
            attempts.append(AttemptLog(stage, model, ok=False, error=str(exc)))
            continue

        attempts.append(AttemptLog(stage, model, ok=True))
        escalated = stage is ChainStage.escalation
        flags: dict[str, Any] = {
            "model_escalated": escalated,
            "forced_hitl": escalated,  # 승급 성공은 점수 무관 HITL 강제
        }
        outcome = TypeCOutcome(
            field_key=field_key,
            raw_text=raw_text,
            value=extraction.value,
            confidence=extraction.confidence,
            rule_pass=1.0 * extraction.confidence,  # 검증 통과(1.0) × 자기보고 confidence
            model_used=raw.model,
            call_count=call_count,
            flags=flags,
            attempts=attempts,
        )
        _log_cost(outcome)
        return outcome

    # 최종 실패: raw 만 저장 대상 + HITL 강제
    outcome = TypeCOutcome(
        field_key=field_key,
        raw_text=raw_text,
        value=None,
        confidence=0.0,
        rule_pass=PASS_FAIL,
        model_used=None,
        call_count=call_count,
        flags={"model_escalated": True, "forced_hitl": True},
        attempts=attempts,
    )
    _log_cost(outcome)
    return outcome


def _log_cost(outcome: TypeCOutcome) -> None:
    """비용 가드 1: 필드 단위 LLM 호출 수/사용 모델 로깅."""
    logger.info(
        "type_c_llm field=%s calls=%d model_used=%s stages=%s escalated=%s",
        outcome.field_key,
        outcome.call_count,
        outcome.model_used,
        [f"{a.stage}:{'ok' if a.ok else 'fail'}" for a in outcome.attempts],
        outcome.flags.get("model_escalated", False),
    )


class TypeCRatioMonitor:
    """비용 가드 2: Type C(LLM 사용) 비중이 설계치를 크게 벗어나면 경고.

    의뢰서 단위로 record() 를 호출한다. 관측 비율이
    (설계치 + 마진) 초과 시 warning 로그 — 라우팅 회귀의 조기 신호.
    """

    def __init__(
        self,
        *,
        design_ratio: float = 0.25,
        warn_margin: float = 0.15,
        min_samples: int = 20,
    ) -> None:
        self._design_ratio = design_ratio
        self._warn_margin = warn_margin
        self._min_samples = min_samples
        self._total = 0
        self._llm_used = 0

    @classmethod
    def from_settings(cls, settings: Settings) -> TypeCRatioMonitor:
        return cls(
            design_ratio=settings.type_c_design_ratio,
            warn_margin=settings.type_c_ratio_warn_margin,
            min_samples=settings.type_c_ratio_min_samples,
        )

    @property
    def observed_ratio(self) -> float:
        return self._llm_used / self._total if self._total else 0.0

    def record(self, *, used_llm: bool) -> None:
        self._total += 1
        if used_llm:
            self._llm_used += 1
        threshold = self._design_ratio + self._warn_margin
        if self._total >= self._min_samples and self.observed_ratio > threshold:
            logger.warning(
                "type_c_ratio_exceeded observed=%.2f design=%.2f threshold=%.2f samples=%d",
                self.observed_ratio,
                self._design_ratio,
                threshold,
                self._total,
            )
