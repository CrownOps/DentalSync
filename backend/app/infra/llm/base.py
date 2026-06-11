"""LLM 구조화 추상 인터페이스 — 벤더 교체 가능(OpenAI ↔ 기타).

승급 체인(서비스 레이어)은 이 Protocol 에만 의존한다. 입력은 **텍스트 전용** —
시그니처에 이미지 파라미터가 존재하지 않는 것이 이미지 입력 금지의 1차 강제다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class RawStructuredOutput:
    """벤더 응답의 최소 정규화 — 파싱된 JSON + 사용 모델."""

    data: dict[str, Any]
    model: str


@runtime_checkable
class LLMStructurer(Protocol):
    """텍스트 + JSON Schema → 구조화 JSON. 텍스트 전용(이미지 입력 절대 금지)."""

    async def structure(
        self,
        *,
        text: str,
        schema: Mapping[str, Any],
        model: str,
    ) -> RawStructuredOutput: ...


class LLMCallError(Exception):
    """API 호출/JSON 파싱 실패."""


class LLMRefusalError(LLMCallError):
    """모델이 응답을 거부(refusal)함."""
