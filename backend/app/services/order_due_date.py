"""주문 납기일(orders.due_date) 도출 — OCR/구조화·HITL 확정 양 경로 공용.

order_fields 의 납기 필드(corrected_value)를 파싱해 orders.due_date(Date)에 반영한다.
이 컬럼이 비어 있으면 납기일 달력(/calendar)에서 모든 의뢰서가 '미지정'으로 떨어진다.

- 우선순위: 본문 납기(due_date) → 내부 납품 요구일(internal_due_date).
- template 경로는 이미 ISO(YYYY-MM-DD)로 보정되고, general(LLM) 경로는 자유 문자열일
  수 있으므로 normalize_date 로 한 번 더 정규화한 뒤 ISO 직파싱으로 폴백한다.
"""

from __future__ import annotations

from datetime import date

from app.services.type_b_rules import normalize_date

# 본문 납기 우선, 없으면 내부 납품 요구일(빨간펜 등).
DUE_DATE_FIELD_KEYS: tuple[str, ...] = ("due_date", "internal_due_date")


def parse_due_date(value: str | None) -> date | None:
    """납기 문자열 → date. 연·월·일이 모두 있는 표기만 인정, 실패 시 None.

    연도 없는 월/일(예: '6/15')은 모호하므로 None(달력 '미지정').
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    iso = normalize_date(text)
    if iso:
        return date.fromisoformat(iso)
    # 이미 ISO(YYYY-MM-DD 또는 그 뒤에 시간) 인 경우 — LLM 이 ISO 로 준 케이스.
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def resolve_due_date(candidates: dict[str, str | None]) -> date | None:
    """필드키→값 매핑에서 우선순위대로 첫 파싱 성공 date 를 반환."""
    for key in DUE_DATE_FIELD_KEYS:
        if key in candidates:
            parsed = parse_due_date(candidates[key])
            if parsed is not None:
                return parsed
    return None
