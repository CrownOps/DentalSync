"""OCR 결과 → 라우팅 결과 매핑 — store_routing_result 입력 생성.

레이아웃 기반 라우팅(v5): layout_v1_1_0.json 의 필드 스펙(type/source/options)으로
타입을 결정한다. LLM 호출 대상(Type C)은 레이아웃이 LLM 을 허용한(source 에
'llm' 포함) 자유텍스트 필드로 한정한다 — 호출률 ~25% 설계 준수.

- Type A: select/boolean/다중 선택(options 보유) → 텍스트 옵션 매칭 룰, LLM 0회
- Type B: date/datetime/치아번호 → 정규식 룰. source 가 OCR 단독인 일반 텍스트도
  CLOVA 확정 대상으로 B 에 귀속(룰 없음, ocr_conf 단독 점수), LLM 0회
- Shade: PIL 색상 인식(별도 단계) 대상
- Type C: 레이아웃이 LLM 허용한 자유텍스트만 — LLM 구조화 단계의 유일한 입력

레이아웃에 없는 키는 절대 스킵하지 않고 경고 로그 후 키워드 휴리스틱으로 폴백한다.
Type A 의 이미지(OpenCV) 체크박스 감지와 Type C LLM 구조화는 별도 파이프라인
단계에서 corrected_value 를 갱신한다 (ADR-0002 참고).
"""

from __future__ import annotations

import logging

from app.domain.enums import CorrectedBy, FieldType
from app.domain.scoring import ScoringConfig
from app.infra.ocr.base import OCRField
from app.services.field_catalog import FieldSpec, get_field_spec
from app.services.note_extraction import NoteExtraction, extract_from_note
from app.services.routing_store import (
    FieldConfidence,
    FieldFlags,
    RawOCR,
    RoutingFieldResult,
)
from app.services.type_a_rules import (
    score_boolean,
    score_multi_select,
    score_select,
)
from app.services.type_b_rules import (
    TOOTH_NUMBER_KEYS,
    score_date,
    score_tooth_numbers,
)

logger = logging.getLogger("dentalsync.routing")

_TOOTH_KEYS = TOOTH_NUMBER_KEYS
_DATE_KEYS = ("date", "due", "날짜", "납기", "접수")
_SHADE_KEYS = ("shade", "셰이드", "색상")
_DATE_LAYOUT_TYPES = ("date", "datetime")

# note(자유텍스트) 백필: 의사가 전용 칸 대신 note 본문에 적은 핵심 3종을 역추출한다.
_NOTE_SOURCE_KEY = "ocr_raw_text"
# (대상 field_key, 합성 시 field_type) — 채움/합성 대상 (비어있을 때만).
_NOTE_BACKFILL_TARGETS: tuple[tuple[str, FieldType], ...] = (
    ("shade", FieldType.SHADE),
    ("tooth_numbers", FieldType.B),
    ("material", FieldType.A),
)
# note 추출값은 항상 사람 확인(forced_hitl) 대상이므로 점수는 '확인 필요' 신호로 고정한다.
_INFERRED_SCORE = 0.5


def _classify_fallback(key: str) -> FieldType:
    """레이아웃 미등록 키 전용 키워드 휴리스틱 (구버전 동작 유지)."""
    if any(k in key for k in _TOOTH_KEYS) or any(k in key for k in _DATE_KEYS):
        return FieldType.B
    return FieldType.C


def classify_field_type(field_key: str, spec: FieldSpec | None) -> FieldType:
    key = field_key.lower()
    if any(k in key for k in _SHADE_KEYS):
        return FieldType.SHADE
    if spec is None:
        fallback = _classify_fallback(key)
        # 스킵 금지 — 레이아웃 누락은 라우팅 회귀 신호이므로 로그로 드러낸다
        logger.warning(
            "field_unmapped field=%s fallback=%s — layout_v1_1_0.json 에 정의 없음",
            field_key,
            fallback.value,
        )
        return fallback
    if spec.layout_type in _DATE_LAYOUT_TYPES or any(k in key for k in _TOOTH_KEYS):
        return FieldType.B
    if spec.layout_type == "boolean" or spec.has_options:
        return FieldType.A
    if spec.llm_allowed:
        return FieldType.C
    # source 가 OCR 단독인 일반 텍스트(치과명/환자명/원문류) — CLOVA 확정, LLM 금지
    return FieldType.B


def _apply_rules(
    field_type: FieldType,
    key: str,
    spec: FieldSpec | None,
    text: str,
) -> tuple[float | None, str | None]:
    """타입별 결정론 룰 적용 → (rule_pass, corrected)."""
    if field_type == FieldType.A and spec is not None:
        if spec.layout_type == "boolean":
            result = score_boolean(text)
        elif spec.item_options:
            result = score_multi_select(text, spec.item_options)
        else:
            result = score_select(text, spec.options)
        return result.rule_pass, result.value

    if field_type == FieldType.B:
        if any(k in key for k in _TOOTH_KEYS):
            tooth = score_tooth_numbers(text)
            return tooth.rule_pass, " ".join(tooth.teeth) if tooth.teeth else None
        is_date = (spec is not None and spec.layout_type in _DATE_LAYOUT_TYPES) or (
            spec is None and any(k in key for k in _DATE_KEYS)
        )
        if is_date:
            d = score_date(text)
            return d.rule_pass, d.iso

    # SHADE/Type C/룰 없는 B 텍스트: ocr_conf 단독 — 보정은 후속 단계(PIL/LLM) 담당
    return None, None


def _note_value(extraction: NoteExtraction, field_key: str) -> str | None:
    """대상 필드별 note 추출값을 저장 문자열로 변환. 없으면 None."""
    if field_key == "shade":
        return extraction.shade
    if field_key == "tooth_numbers":
        return " ".join(extraction.tooth_numbers) or None
    if field_key == "material":
        return " ".join(extraction.materials) or None
    return None


def _make_inferred_result(
    field_key: str,
    field_type: FieldType,
    value: str,
    existing: RoutingFieldResult | None,
) -> RoutingFieldResult:
    """note 추출값으로 채운/합성한 필드 결과 — forced_hitl + inferred_from_note."""
    # 빈 칸을 채우는 경우 기존 raw(bbox) 를 보존해 HITL 하이라이트가 유지되도록 한다.
    raw = (
        existing.raw
        if existing is not None
        else RawOCR(text=None, bbox=None, infer_confidence=None)
    )
    return RoutingFieldResult(
        field_key=field_key,
        field_type=field_type,
        raw=raw,
        corrected_value=value,
        corrected_by=CorrectedBy.system,
        confidence=FieldConfidence(score=_INFERRED_SCORE),
        flags=FieldFlags(
            field_type=field_type.value,
            forced_hitl=True,
            inferred_from_note=True,
        ),
    )


def backfill_from_note(results: list[RoutingFieldResult]) -> None:
    """note(ocr_raw_text)에서 쉐이드/치식/재료를 역추출해 '비어있는' 대상 칸을 채운다.

    이미 값이 있는 칸은 절대 덮어쓰지 않는다(OCR 인식값 보존). 추출값은 항상
    needs_review(forced_hitl)로 띄워 사람이 최종 확인한다. results 를 제자리 수정한다.
    """
    note_field = next((r for r in results if r.field_key == _NOTE_SOURCE_KEY), None)
    if note_field is None or not (note_field.raw.text or "").strip():
        return

    extraction = extract_from_note(note_field.raw.text)
    by_key = {r.field_key: r for r in results}

    for field_key, field_type in _NOTE_BACKFILL_TARGETS:
        value = _note_value(extraction, field_key)
        if value is None:
            continue
        existing = by_key.get(field_key)
        if existing is not None and (existing.corrected_value or "").strip():
            continue  # 비어있지 않으면 채우지 않음
        inferred = _make_inferred_result(field_key, field_type, value, existing)
        if existing is not None:
            results[results.index(existing)] = inferred
        else:
            results.append(inferred)


def route_ocr_fields(
    ocr_fields: list[OCRField],
    cfg: ScoringConfig,
) -> list[RoutingFieldResult]:
    """OCRField 리스트를 RoutingFieldResult 리스트로 변환.

    - Type A: 옵션 매칭 룰(rule_pass) + 표준값 보정
    - Type B: 날짜/치식 정규식 룰 + 보정값 산출 (일반 텍스트는 ocr_conf 단독)
    - 그 외: ocr_conf 단독 점수 (가중치 재정규화)
    """
    results: list[RoutingFieldResult] = []
    for f in ocr_fields:
        spec = get_field_spec(f.field_key)
        field_type = classify_field_type(f.field_key, spec)
        rule_pass, corrected = _apply_rules(field_type, f.field_key.lower(), spec, f.text)

        components = {"ocr_conf": f.confidence}
        if rule_pass is not None:
            components["rule_pass"] = rule_pass
        weights = cfg.weights.normalized_for(components.keys())
        score = sum(weights[c] * components[c] for c in components)

        results.append(
            RoutingFieldResult(
                field_key=f.field_key,
                field_type=field_type,
                raw=RawOCR(text=f.text, bbox=f.bbox, infer_confidence=f.confidence),
                corrected_value=corrected or f.text,
                corrected_by=CorrectedBy.system,
                confidence=FieldConfidence(
                    score=score,
                    ocr_conf=f.confidence,
                    rule_pass=rule_pass,
                ),
                flags=FieldFlags(field_type=field_type.value),
            )
        )

    # note 본문에만 적힌 쉐이드/치식/재료를 전용 칸으로 역추출(비어있을 때만).
    backfill_from_note(results)
    return results
