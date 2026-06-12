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


def _classify_fallback(key: str) -> FieldType:
    """레이아웃 미등록 키 전용 키워드 휴리스틱 (구버전 동작 유지)."""
    if any(k in key for k in _TOOTH_KEYS) or any(k in key for k in _DATE_KEYS):
        return FieldType.B
    return FieldType.C


def _classify(field_key: str, spec: FieldSpec | None) -> FieldType:
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
        field_type = _classify(f.field_key, spec)
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
    return results
