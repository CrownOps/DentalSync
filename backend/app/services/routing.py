"""OCR 결과 → 라우팅 결과 매핑 — store_routing_result 입력 생성.

Phase 1 텍스트 기반 라우팅: field_key 패턴으로 Type B(치아번호/날짜) 규칙을
적용하고, 그 외 필드는 OCR 신뢰도만으로 점수를 산출한다(가중치 재정규화).
Type A(체크박스)/Shade 의 이미지 기반 감지와 Type C LLM 구조화는 별도
파이프라인 단계에서 corrected_value 를 갱신한다 (ADR-0002 참고).
"""

from __future__ import annotations

from app.domain.enums import CorrectedBy, FieldType
from app.domain.scoring import ScoringConfig
from app.infra.ocr.base import OCRField
from app.services.routing_store import (
    FieldConfidence,
    FieldFlags,
    RawOCR,
    RoutingFieldResult,
)
from app.services.type_b_rules import score_date, score_tooth_numbers

_TOOTH_KEYS = ("tooth", "치아", "치식")
_DATE_KEYS = ("date", "due", "날짜", "납기", "접수")
_SHADE_KEYS = ("shade", "셰이드", "색상")


def _classify(field_key: str) -> FieldType:
    key = field_key.lower()
    if any(k in key for k in _SHADE_KEYS):
        return FieldType.SHADE
    if any(k in key for k in _TOOTH_KEYS) or any(k in key for k in _DATE_KEYS):
        return FieldType.B
    return FieldType.C


def route_ocr_fields(
    ocr_fields: list[OCRField],
    cfg: ScoringConfig,
) -> list[RoutingFieldResult]:
    """OCRField 리스트를 RoutingFieldResult 리스트로 변환.

    - Type B: 규칙(rule_pass) 적용 + 보정값 산출
    - 그 외: ocr_conf 단독 점수 (가중치 재정규화)
    """
    results: list[RoutingFieldResult] = []
    for f in ocr_fields:
        field_type = _classify(f.field_key)
        key = f.field_key.lower()

        rule_pass: float | None = None
        corrected: str | None = None

        if field_type == FieldType.B:
            if any(k in key for k in _TOOTH_KEYS):
                tooth = score_tooth_numbers(f.text)
                rule_pass = tooth.rule_pass
                corrected = " ".join(tooth.teeth) if tooth.teeth else None
            else:
                d = score_date(f.text)
                rule_pass = d.rule_pass
                corrected = d.iso

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
