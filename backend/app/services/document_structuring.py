"""문서 레벨 LLM 구조화 — General OCR 전체 텍스트 → 필드 envelope(RoutingFieldResult).

Template 경로(route_ocr_fields)와 달리, 양식이 제각각인 의뢰서의 전체 텍스트를 LLM 으로
한 번에 구조화해 핵심 필드를 뽑는다. 자유양식은 위험이 크므로 추출 필드는 **전부
needs_review(forced_hitl)** 로 보내 검수자가 항목별로 확인한다.

- LLM 인터페이스(LLMStructurer)에만 의존(벤더 무관). 모델명은 Settings 로 지정(하드코딩 금지).
- 승급 체인: primary → primary_retry → escalation (type_c_structuring 와 동일 패턴).
- 마지막에 routing.backfill_from_note 로 LLM 이 놓친 쉐이드/치식/재료를 결정론 보강.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.domain.enums import CorrectedBy, FieldType
from app.infra.llm.base import LLMCallError, LLMStructurer
from app.infra.ocr.base import OCRField
from app.infra.ocr.clova_general import RAW_TEXT_KEY
from app.services.field_catalog import get_field_spec
from app.services.routing import backfill_from_note, classify_field_type
from app.services.routing_store import (
    FieldConfidence,
    FieldFlags,
    RawOCR,
    RoutingFieldResult,
)
from app.services.type_c_structuring import ChainStage

logger = logging.getLogger("dentalsync.document")

# 핵심 subset — LLM 이 자유텍스트에서 뽑을 필드. (key, is_array)
_FIELD_PLAN: tuple[tuple[str, bool], ...] = (
    ("clinic_name", False),
    ("patient_name", False),
    ("doctor_name", False),
    ("prosthesis_category", False),
    ("material", True),
    ("shade", False),
    ("tooth_numbers", True),
    ("due_date", False),
)

_NULLABLE_STR = {"type": ["string", "null"]}
_STR_ARRAY = {"type": "array", "items": {"type": "string"}}

# Structured Outputs strict: 전 프로퍼티 required + additionalProperties false
DOCUMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "clinic_name": _NULLABLE_STR,
        "patient_name": _NULLABLE_STR,
        "doctor_name": _NULLABLE_STR,
        "prosthesis_category": _NULLABLE_STR,
        "material": _STR_ARRAY,
        "shade": _NULLABLE_STR,
        "tooth_numbers": _STR_ARRAY,
        "due_date": _NULLABLE_STR,
        "note": _NULLABLE_STR,
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "clinic_name", "patient_name", "doctor_name", "prosthesis_category",
        "material", "shade", "tooth_numbers", "due_date", "note", "confidence",
    ],
    "additionalProperties": False,
}


class DocumentExtraction(BaseModel):
    """2차 방어 — Structured Outputs 통과 출력도 재검증."""

    model_config = ConfigDict(extra="forbid")

    clinic_name: str | None
    patient_name: str | None
    doctor_name: str | None
    prosthesis_category: str | None
    material: list[str]
    shade: str | None
    tooth_numbers: list[str]
    due_date: str | None
    note: str | None
    confidence: float = Field(ge=0.0, le=1.0)


def _field_value(extraction: DocumentExtraction, key: str, is_array: bool) -> str | None:
    """추출 결과에서 저장 문자열 변환. 비면 None(해당 필드 스킵)."""
    raw = getattr(extraction, key)
    if is_array:
        return " ".join(raw) if raw else None
    return raw if (raw and raw.strip()) else None


def _llm_result(
    field_key: str, value: str, score: float, escalated: bool
) -> RoutingFieldResult:
    """LLM 추출 필드 → RoutingFieldResult (전부 forced_hitl)."""
    field_type = classify_field_type(field_key, get_field_spec(field_key))
    return RoutingFieldResult(
        field_key=field_key,
        field_type=field_type,
        raw=RawOCR(text=None, bbox=None, infer_confidence=None),
        corrected_value=value,
        corrected_by=CorrectedBy.llm,
        confidence=FieldConfidence(score=score),
        flags=FieldFlags(
            field_type=field_type.value,
            forced_hitl=True,
            structured_by_llm=True,
            model_escalated=escalated,
        ),
    )


def _raw_text_result(raw_field: OCRField) -> RoutingFieldResult:
    """전체 OCR 텍스트 보존 필드 — note 백필 입력 + 검수 표시용."""
    return RoutingFieldResult(
        field_key=RAW_TEXT_KEY,
        field_type=FieldType.B,
        raw=RawOCR(
            text=raw_field.text, bbox=raw_field.bbox, infer_confidence=raw_field.confidence
        ),
        corrected_value=raw_field.text,
        corrected_by=CorrectedBy.system,
        confidence=FieldConfidence(score=raw_field.confidence, ocr_conf=raw_field.confidence),
        flags=FieldFlags(field_type=FieldType.B.value, forced_hitl=True),
    )


async def structure_document(
    *,
    structurer: LLMStructurer,
    raw_field: OCRField,
    settings: Settings,
) -> list[RoutingFieldResult]:
    """전체 텍스트 → 필드 envelope 목록. 추출 필드는 전부 needs_review."""
    results: list[RoutingFieldResult] = [_raw_text_result(raw_field)]

    plan: tuple[tuple[ChainStage, str], ...] = (
        (ChainStage.primary, settings.llm_model_primary),
        (ChainStage.primary_retry, settings.llm_model_primary),
        (ChainStage.escalation, settings.llm_model_escalation),
    )

    extraction: DocumentExtraction | None = None
    escalated = False
    for stage, model in plan:
        try:
            raw = await structurer.structure(
                text=raw_field.text, schema=DOCUMENT_SCHEMA, model=model
            )
            extraction = DocumentExtraction.model_validate(raw.data)
        except (LLMCallError, ValidationError) as exc:
            logger.warning("document_structure stage=%s model=%s 실패: %s", stage, model, exc)
            continue
        escalated = stage is ChainStage.escalation
        logger.info(
            "document_structure ok stage=%s model=%s confidence=%.2f",
            stage, raw.model, extraction.confidence,
        )
        break

    if extraction is not None:
        for key, is_array in _FIELD_PLAN:
            value = _field_value(extraction, key, is_array)
            if value is not None:
                results.append(_llm_result(key, value, extraction.confidence, escalated))
    else:
        logger.warning("document_structure 전 단계 실패 — 전체 텍스트만 검수 큐로 보냄")

    # LLM 이 놓친 쉐이드/치식/재료를 전체 텍스트에서 결정론 보강(빈 칸만).
    backfill_from_note(results)
    return results
