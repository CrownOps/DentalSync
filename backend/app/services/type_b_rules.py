"""Type B 결정론적 보정 룰 — 치식/날짜/납기. 순수 함수(외부 I/O 0), LLM 0회.

rule_pass: 완전 통과 1.0 / 부분(파싱됐으나 모호) 0.5 / 실패·범위밖 0.0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

PASS_FULL = 1.0
PASS_PARTIAL = 0.5
PASS_FAIL = 0.0

# 치아번호(FDI) 필드 키 패턴 — 'tooth' 단독 매칭 금지.
# tooth_notation/tooth_region/tooth_side/tooth_vitality 등 범주형 필드가
# FDI 검증에 걸려 HITL 확정이 불가능해지는 오분류를 방지한다(layout v1.1.0).
TOOTH_NUMBER_KEYS = ("tooth_number", "치아번호", "치식")

# --------------------------------------------------------------------------- #
# 치식 (FDI 11~48)
# --------------------------------------------------------------------------- #
_FDI_RE = re.compile(r"^[1-4][1-8]$")
_SEGMENT_SPLIT = re.compile(r"[,\s;]+")
_RANGE_SPLIT = re.compile(r"[-~–]")


@dataclass(frozen=True)
class ToothRuleResult:
    teeth: tuple[str, ...]
    rule_pass: float


def _is_fdi(token: str) -> bool:
    return bool(_FDI_RE.match(token))


def score_tooth_numbers(raw: str) -> ToothRuleResult:
    """치식 표기 파싱 + FDI 범위 검증. 복수/브릿지(범위) 지원."""
    segments = [s for s in _SEGMENT_SPLIT.split(raw.strip()) if s]
    if not segments:
        return ToothRuleResult((), PASS_FAIL)

    teeth: list[str] = []
    ambiguous = False

    for seg in segments:
        if _RANGE_SPLIT.search(seg):
            parts = [p for p in _RANGE_SPLIT.split(seg) if p]
            if len(parts) != 2 or not (_is_fdi(parts[0]) and _is_fdi(parts[1])):
                return ToothRuleResult((), PASS_FAIL)  # 범위 밖/파싱 실패 → HITL 직행
            start, end = parts
            if start[0] != end[0] or int(start) > int(end):
                # 사분면을 넘거나 역순 → 해석 모호
                ambiguous = True
                teeth.extend([start, end])
            else:
                teeth.extend(str(n) for n in range(int(start), int(end) + 1))
        elif _is_fdi(seg):
            teeth.append(seg)
        else:
            return ToothRuleResult((), PASS_FAIL)  # 범위 밖 값

    ordered = tuple(dict.fromkeys(teeth))  # 중복 제거, 순서 유지
    return ToothRuleResult(ordered, PASS_PARTIAL if ambiguous else PASS_FULL)


# --------------------------------------------------------------------------- #
# 날짜 정규화 → ISO 8601
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DateRuleResult:
    iso: str | None
    rule_pass: float


_FULL_PATTERNS = (
    re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$"),  # 2026-06-15
    re.compile(r"^(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일$"),  # 2026년 6월 15일
    re.compile(r"^(\d{2})[-./](\d{1,2})[-./](\d{1,2})$"),  # 26.6.15
    re.compile(r"^(\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일$"),  # 26년 6월 15일
    re.compile(r"^(\d{4})(\d{2})(\d{2})$"),  # 20260615
)
_MD_PATTERNS = (
    re.compile(r"^(\d{1,2})[-./](\d{1,2})$"),  # 6/15
    re.compile(r"^(\d{1,2})월\s*(\d{1,2})일$"),  # 6월 15일
)

# 납기(datetime) 시간 접미 — "2026-06-04T09:00:00", "6/4 09:00", "6월 4일 오전 9시" 등.
# 날짜부만 정규화 대상으로 삼고 시간부는 제거한다.
_TIME_SUFFIX_RE = re.compile(
    r"(?:[T\s]+(?:오전|오후|AM|PM)?\s*\d{1,2}(?::\d{2}(?::\d{2})?|시(?:\s*\d{1,2}분?)?))\s*$",
    re.IGNORECASE,
)


def _strip_time_suffix(text: str) -> str:
    return _TIME_SUFFIX_RE.sub("", text).strip()


def _build_iso(year: int, month: int, day: int) -> str | None:
    if year < 100:
        year += 2000
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def normalize_date(raw: str) -> str | None:
    """연/월/일이 모두 있는 표기를 ISO(YYYY-MM-DD)로. 실패/연도없음 → None."""
    text = _strip_time_suffix(raw.strip())
    for pat in _FULL_PATTERNS:
        m = pat.match(text)
        if m:
            return _build_iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def score_date(raw: str) -> DateRuleResult:
    text = _strip_time_suffix(raw.strip())
    for pat in _FULL_PATTERNS:
        m = pat.match(text)
        if m:
            iso = _build_iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return DateRuleResult(iso, PASS_FULL if iso else PASS_FAIL)

    # 연도 없는 월/일 → 파싱은 됐으나 연도 모호 → 부분 통과
    for pat in _MD_PATTERNS:
        m = pat.match(text)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return DateRuleResult(None, PASS_PARTIAL)
            return DateRuleResult(None, PASS_FAIL)

    return DateRuleResult(None, PASS_FAIL)


# --------------------------------------------------------------------------- #
# 납기 (due_date >= received_at)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DueDateRuleResult:
    iso: str | None
    rule_pass: float


def score_due_date(due_raw: str, received_at: date | datetime | None) -> DueDateRuleResult:
    parsed = score_date(due_raw)
    if parsed.iso is None:
        return DueDateRuleResult(None, parsed.rule_pass)  # 0.0(무효) 또는 0.5(연도모호) 전파

    due = date.fromisoformat(parsed.iso)
    if received_at is None:
        return DueDateRuleResult(parsed.iso, PASS_FULL)  # 날짜 자체는 유효(비교 불가)

    received = received_at.date() if isinstance(received_at, datetime) else received_at
    if due >= received:
        return DueDateRuleResult(parsed.iso, PASS_FULL)
    return DueDateRuleResult(parsed.iso, PASS_FAIL)  # 납기 역전 위반 → HITL
