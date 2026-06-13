"""routing.py — OCR 결과 → 라우팅 결과 매핑 테스트."""

from __future__ import annotations

import logging

import pytest

from app.domain.enums import FieldType
from app.domain.scoring import ScoringConfig, ScoringThresholds, ScoringWeights
from app.infra.ocr.base import OCRField
from app.infra.ocr.mock import load_layout_fields
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


def test_unmapped_key_falls_back_to_type_c_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """레이아웃 미등록 키 — 스킵 금지, 경고 로그 + 휴리스틱 폴백."""
    with caplog.at_level(logging.WARNING, logger="dentalsync.routing"):
        results = route_ocr_fields([_ocr("notes", "크라운 제작 요청", conf=0.8)], _CFG)
    r = results[0]
    assert r.field_type == FieldType.C
    assert r.confidence.rule_pass is None
    # ocr_conf 단독 재정규화 → score == ocr_conf
    assert abs(r.confidence.score - 0.8) < 1e-9
    assert any("field_unmapped" in rec.message for rec in caplog.records)


def test_select_field_routes_to_type_a_with_option_match() -> None:
    results = route_ocr_fields([_ocr("tooth_vitality", "vital")], _CFG)
    r = results[0]
    assert r.field_type == FieldType.A
    assert r.confidence.rule_pass == 1.0
    assert r.corrected_value == "vital"


def test_boolean_field_routes_to_type_a() -> None:
    results = route_ocr_fields([_ocr("is_remake", "false")], _CFG)
    r = results[0]
    assert r.field_type == FieldType.A
    assert r.confidence.rule_pass == 1.0
    assert r.corrected_value == "false"


def test_special_flags_mapped_as_type_a_multi_select() -> None:
    """special_flags — 다중 선택 매핑 (스킵 회귀 방지: 반드시 결과에 포함)."""
    results = route_ocr_fields([_ocr("special_flags", '["scrp"]')], _CFG)
    assert len(results) == 1
    r = results[0]
    assert r.field_type == FieldType.A
    assert r.confidence.rule_pass == 1.0
    assert r.corrected_value == '["scrp"]'


def test_special_flags_unknown_token_is_partial_pass() -> None:
    results = route_ocr_fields([_ocr("special_flags", "scrp 알수없음")], _CFG)
    r = results[0]
    assert r.confidence.rule_pass == 0.5
    assert r.corrected_value == '["scrp"]'


def test_plain_ocr_text_routes_to_type_b_without_llm() -> None:
    """source=ocr 단순 텍스트(치과명 등) — CLOVA 확정, LLM 대상(C) 제외."""
    results = route_ocr_fields([_ocr("clinic_name", "서울미소치과", conf=0.9)], _CFG)
    r = results[0]
    assert r.field_type == FieldType.B
    assert r.confidence.rule_pass is None
    assert abs(r.confidence.score - 0.9) < 1e-9


def test_llm_allowed_free_text_routes_to_type_c() -> None:
    results = route_ocr_fields([_ocr("contact_instruction", "컨택 신경써주세요")], _CFG)
    assert results[0].field_type == FieldType.C


# --------------------------------------------------------------------------- #
# note 백필 — 자유텍스트에만 적힌 쉐이드/치식/재료 역추출
# --------------------------------------------------------------------------- #
def test_note_backfill_synthesizes_missing_fields() -> None:
    note = "#36, 37 custom abutment + zirconia cr. shade A3"
    results = route_ocr_fields([_ocr("ocr_raw_text", note)], _CFG)
    by_key = {r.field_key: r for r in results}

    assert by_key["shade"].corrected_value == "A3"
    assert by_key["shade"].field_type == FieldType.SHADE
    assert by_key["shade"].flags.inferred_from_note is True
    assert by_key["shade"].flags.forced_hitl is True  # 항상 사람 확인 대상

    assert by_key["tooth_numbers"].corrected_value == "36 37"
    assert by_key["material"].corrected_value == "zirconia"


def test_note_backfill_does_not_overwrite_existing() -> None:
    """이미 인식된 칸은 덮어쓰지 않는다(비어있을 때만 채움)."""
    note = "#36, 37 zirconia cr. A3"
    results = route_ocr_fields(
        [_ocr("ocr_raw_text", note), _ocr("shade", "B2")], _CFG
    )
    by_key = {r.field_key: r for r in results}

    assert by_key["shade"].corrected_value == "B2"  # 기존값 유지
    assert by_key["shade"].flags.inferred_from_note is False
    assert by_key["tooth_numbers"].corrected_value == "36 37"  # 비어 있던 칸만 백필


def test_note_backfill_skips_when_nothing_extracted() -> None:
    results = route_ocr_fields([_ocr("ocr_raw_text", "특이사항 없음")], _CFG)
    assert {r.field_key for r in results} == {"ocr_raw_text"}


def test_llm_call_ratio_within_design_target() -> None:
    """레이아웃 전 필드 라우팅 시 Type C(LLM 대상) 비중 ≤ 설계치 25%."""
    fields = list(load_layout_fields())
    results = route_ocr_fields(fields, _CFG)
    type_c = [r for r in results if r.field_type == FieldType.C]
    assert len(results) == len(fields)  # 어떤 필드도 스킵하지 않는다
    assert len(type_c) / len(results) <= 0.25
