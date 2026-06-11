"""routing.py — OCR 결과 → 라우팅 결과 매핑 테스트."""

from __future__ import annotations

from app.domain.enums import FieldType
from app.domain.scoring import ScoringConfig, ScoringThresholds, ScoringWeights
from app.infra.ocr.base import OCRField
from app.services.routing import route_ocr_fields

_CFG = ScoringConfig(
    weights=ScoringWeights(ocr_conf=0.5, rule_pass=0.3, dict_match=0.2),
    thresholds=ScoringThresholds(general=0.90, critical=0.95),
    critical_fields=["shade", "tooth_numbers", "due_date"],
)


def _ocr(key: str, text: str, conf: float = 0.95) -> OCRField:
    return OCRField(field_key=key, text=text, confidence=conf)


def test_tooth_field_routes_to_type_b_with_rule() -> None:
    results = route_ocr_fields([_ocr("tooth_numbers", "11 12")], _CFG)
    r = results[0]
    assert r.field_type == FieldType.B
    assert r.confidence.rule_pass == 1.0
    assert r.corrected_value == "11 12"


def test_invalid_tooth_lowers_score() -> None:
    results = route_ocr_fields([_ocr("tooth_numbers", "99", conf=0.99)], _CFG)
    r = results[0]
    assert r.confidence.rule_pass == 0.0
    # ocr_conf(0.5)+rule_pass(0.3) 재정규화: 0.99*0.625 + 0*0.375 ≈ 0.62
    assert r.confidence.score < 0.90


def test_date_field_normalized() -> None:
    results = route_ocr_fields([_ocr("due_date", "2026.06.15")], _CFG)
    r = results[0]
    assert r.field_type == FieldType.B
    assert r.corrected_value == "2026-06-15"


def test_shade_field_classified() -> None:
    results = route_ocr_fields([_ocr("shade", "A2")], _CFG)
    assert results[0].field_type == FieldType.SHADE


def test_free_text_routes_to_type_c_ocr_conf_only() -> None:
    results = route_ocr_fields([_ocr("notes", "크라운 제작 요청", conf=0.8)], _CFG)
    r = results[0]
    assert r.field_type == FieldType.C
    assert r.confidence.rule_pass is None
    # ocr_conf 단독 재정규화 → score == ocr_conf
    assert abs(r.confidence.score - 0.8) < 1e-9
