"""document_structuring.py — General 경로 LLM 문서 구조화 테스트."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from app.core.config import Settings
from app.domain.enums import CorrectedBy, FieldType
from app.infra.llm.base import LLMCallError, RawStructuredOutput
from app.infra.ocr.base import OCRField
from app.services.document_structuring import structure_document

_SETTINGS = Settings(llm_model_primary="m-primary", llm_model_escalation="m-escalation")


class _FakeStructurer:
    """고정 dict 를 반환하는 LLMStructurer 스텁."""

    def __init__(self, data: dict[str, Any] | None = None, *, fail: bool = False) -> None:
        self._data = data
        self._fail = fail
        self.calls: list[str] = []

    async def structure(
        self, *, text: str, schema: Mapping[str, Any], model: str
    ) -> RawStructuredOutput:
        self.calls.append(model)
        if self._fail or self._data is None:
            raise LLMCallError("boom")
        return RawStructuredOutput(data=self._data, model=model)


def _raw(text: str) -> OCRField:
    return OCRField(field_key="ocr_raw_text", text=text, confidence=0.9)


_FULL = {
    "clinic_name": "청구치과의원",
    "patient_name": "홍길동",
    "doctor_name": "김민수",
    "prosthesis_category": "crown",
    "material": ["zirconia"],
    "shade": "A3",
    "tooth_numbers": ["36", "37"],
    "due_date": "2026-06-20",
    "note": "전체 메모",
    "confidence": 0.82,
}


async def test_structure_document_maps_fields() -> None:
    structurer = _FakeStructurer(_FULL)
    results = await structure_document(
        structurer=structurer, raw_field=_raw("#36 37 지르코니아 A3"), settings=_SETTINGS
    )
    by_key = {r.field_key: r for r in results}

    # 전체 텍스트 보존 필드
    assert "ocr_raw_text" in by_key
    assert by_key["ocr_raw_text"].corrected_by == CorrectedBy.system

    # LLM 추출 필드 — 전부 forced_hitl + structured_by_llm + corrected_by=llm
    for key in ("clinic_name", "patient_name", "shade", "tooth_numbers", "material", "due_date"):
        r = by_key[key]
        assert r.flags.forced_hitl is True
        assert r.flags.structured_by_llm is True
        assert r.corrected_by == CorrectedBy.llm

    # 타입 분류 + array 공백조인
    assert by_key["shade"].field_type == FieldType.SHADE
    assert by_key["tooth_numbers"].field_type == FieldType.B
    assert by_key["tooth_numbers"].corrected_value == "36 37"
    assert by_key["material"].field_type == FieldType.A
    assert by_key["material"].corrected_value == "zirconia"
    assert by_key["shade"].corrected_value == "A3"
    assert by_key["shade"].confidence.score == pytest.approx(0.82)


async def test_primary_model_used_first() -> None:
    structurer = _FakeStructurer(_FULL)
    await structure_document(structurer=structurer, raw_field=_raw("x"), settings=_SETTINGS)
    assert structurer.calls[0] == "m-primary"  # 1차는 경량 모델


async def test_empty_llm_fields_backfilled_from_raw_text() -> None:
    """LLM 이 쉐이드/치식/재료를 비워도 전체 텍스트에서 결정론 보강(빈 칸만)."""
    sparse = {**_FULL, "shade": None, "tooth_numbers": [], "material": []}
    structurer = _FakeStructurer(sparse)
    results = await structure_document(
        structurer=structurer,
        raw_field=_raw("#36, 37 zirconia cr. shade A3"),
        settings=_SETTINGS,
    )
    by_key = {r.field_key: r for r in results}
    assert by_key["tooth_numbers"].corrected_value == "36 37"
    assert by_key["material"].corrected_value == "zirconia"
    assert by_key["shade"].corrected_value == "A3"
    assert by_key["tooth_numbers"].flags.inferred_from_note is True


async def test_all_stages_fail_keeps_raw_text_only() -> None:
    """LLM 전 단계 실패 → 전체 텍스트만 검수 큐로(LLM 필드 없음). 3회 호출."""
    structurer = _FakeStructurer(fail=True)
    results = await structure_document(
        structurer=structurer, raw_field=_raw("특이사항 없음"), settings=_SETTINGS
    )
    assert len(structurer.calls) == 3  # primary, retry, escalation
    assert {r.field_key for r in results} == {"ocr_raw_text"}
    assert not any(r.flags.structured_by_llm for r in results)
