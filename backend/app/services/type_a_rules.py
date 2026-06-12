"""Type A 텍스트 레벨 옵션 매칭 룰 — select/boolean/다중 선택. 순수 함수, LLM 0회.

이미지(OpenCV) 체크박스 감지는 marking_detection.py 의 별도 단계가 담당하고,
여기서는 CLOVA 가 읽은 텍스트를 레이아웃 options/item_options 에 결정론적으로
매칭한다. rule_pass: 전부 매칭 1.0 / 일부만 매칭 0.5 / 미매칭·무입력 0.0.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

PASS_FULL = 1.0
PASS_PARTIAL = 0.5
PASS_FAIL = 0.0

_TRUE_TOKENS = frozenset({"true", "yes", "y", "o", "v", "1", "예", "유", "체크", "check"})
_FALSE_TOKENS = frozenset({"false", "no", "n", "x", "0", "아니오", "아니요", "무"})

_TOKEN_SPLIT = re.compile(r"[,;/\s]+")


@dataclass(frozen=True)
class OptionRuleResult:
    value: str | None  # 매칭된 표준 옵션 값 (다중 선택은 JSON 배열 문자열)
    rule_pass: float


def _normalize(text: str) -> str:
    # 옵션 표준어가 snake_case 라 공백/하이픈 표기 변형을 흡수한다 (non vital → non_vital)
    return re.sub(r"[\s\-]+", "_", text.strip().lower())


def score_boolean(raw: str) -> OptionRuleResult:
    norm = _normalize(raw)
    if norm in _TRUE_TOKENS:
        return OptionRuleResult("true", PASS_FULL)
    if norm in _FALSE_TOKENS:
        return OptionRuleResult("false", PASS_FULL)
    return OptionRuleResult(None, PASS_FAIL)


def score_select(raw: str, options: tuple[str, ...]) -> OptionRuleResult:
    """단일 선택 — 정규화 후 정확 매칭만 통과. 모호하면 HITL 직행."""
    norm = _normalize(raw)
    if not norm:
        return OptionRuleResult(None, PASS_FAIL)
    for option in options:
        if norm == _normalize(option):
            return OptionRuleResult(option, PASS_FULL)
    return OptionRuleResult(None, PASS_FAIL)


def _tokens(raw: str) -> list[str]:
    """JSON 배열 표기(["scrp"]) 우선, 아니면 구분자 분리."""
    text = raw.strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return [t for t in _TOKEN_SPLIT.split(text) if t]


def score_multi_select(raw: str, item_options: tuple[str, ...]) -> OptionRuleResult:
    """다중 선택(예: special_flags SCRP/Hook) — 토큰별 옵션 매칭.

    전 토큰 매칭 → 1.0 / 일부 매칭 → 0.5(미해석 토큰 존재, HITL 후보) /
    매칭 0개 → 0.0.
    """
    tokens = _tokens(raw)
    if not tokens:
        return OptionRuleResult(None, PASS_FAIL)

    normalized_options = {_normalize(o): o for o in item_options}
    matched: list[str] = []
    for token in tokens:
        standard = normalized_options.get(_normalize(token))
        if standard is not None and standard not in matched:
            matched.append(standard)

    if not matched:
        return OptionRuleResult(None, PASS_FAIL)

    value = json.dumps(matched, ensure_ascii=False)
    if len(matched) == len({_normalize(t) for t in tokens}):
        return OptionRuleResult(value, PASS_FULL)
    return OptionRuleResult(value, PASS_PARTIAL)
