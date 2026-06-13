"""Mock LLM 구조화기 — 키 없이 General 경로를 로컬 시연.

OpenAI 대신 입력 텍스트를 **실제로 경량 파싱**해 DOCUMENT_SCHEMA 모양의 dict 를 돌려준다.
쉐이드/치식/재료는 note_extraction 을 재사용하고, 치과명/환자/원장/납기/보철형태는
간단한 정규식·키워드로 뽑는다. → mock 인데도 입력을 반영해 데모가 자연스럽다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.infra.llm.base import RawStructuredOutput
from app.services.note_extraction import extract_from_note

_CLINIC_RE = re.compile(r"([가-힣A-Za-z0-9]+(?:치과의원|치과|의원))")
_PATIENT_RE = re.compile(r"환자\s*[:：]?\s*([가-힣]{2,4})")
_DOCTOR_RE = re.compile(r"원장\s*[:：]?\s*([가-힣]{2,4})")
_DUE_RE = re.compile(r"납기[^\d]*(\d{4}[-./]\d{1,2}[-./]\d{1,2})")
_ANY_DATE_RE = re.compile(r"(\d{4}[-./]\d{1,2}[-./]\d{1,2})")

# 보철 형태 키워드 → layout prosthesis_category enum
_CATEGORY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("브릿지", "bridge"), ("브리지", "bridge"), ("bridge", "bridge"),
    ("임플란트", "implant_prosthesis"), ("implant", "implant_prosthesis"),
    ("인레이", "inlay"), ("inlay", "inlay"),
    ("온레이", "onlay"), ("onlay", "onlay"),
    ("틀니", "denture"), ("의치", "denture"), ("denture", "denture"),
    ("크라운", "crown"), ("crown", "crown"),
)


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1) if m else None


def _category(text: str) -> str | None:
    lower = text.lower()
    for keyword, enum_value in _CATEGORY_KEYWORDS:
        if keyword.isascii():
            if keyword in lower:
                return enum_value
        elif keyword in text:
            return enum_value
    return None


def _due_date(text: str) -> str | None:
    return _first(_DUE_RE, text) or _first(_ANY_DATE_RE, text)


class MockLLMStructurer:
    """LLMStructurer Protocol 구현 — 입력 텍스트를 경량 파싱해 구조화 dict 반환."""

    async def structure(
        self, *, text: str, schema: Mapping[str, Any], model: str
    ) -> RawStructuredOutput:
        note = extract_from_note(text)
        data: dict[str, Any] = {
            "clinic_name": _first(_CLINIC_RE, text),
            "patient_name": _first(_PATIENT_RE, text),
            "doctor_name": _first(_DOCTOR_RE, text),
            "prosthesis_category": _category(text),
            "material": list(note.materials),
            "shade": note.shade,
            "tooth_numbers": list(note.tooth_numbers),
            "due_date": _due_date(text),
            "note": text.strip() or None,
            "confidence": 0.8,
        }
        return RawStructuredOutput(data=data, model="mock-structurer")
