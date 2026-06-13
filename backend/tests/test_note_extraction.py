"""note_extraction.py — 자유텍스트 쉐이드/치식/재료 추출 테스트."""

from __future__ import annotations

from app.services.note_extraction import (
    extract_from_note,
    extract_materials,
    extract_shades,
    extract_tooth_numbers,
)

# 실제 의뢰서 note 본문에 가까운 예시
_NOTE = "#36, 37 custom abutment + zirconia cr. shade A3. 컨택과 교합 신경써주세요."


def test_extract_from_note_full() -> None:
    res = extract_from_note(_NOTE)
    assert res.shade == "A3"
    assert res.tooth_numbers == ("36", "37")
    assert res.materials == ("zirconia",)


def test_shade_variants() -> None:
    assert extract_shades("color a3.5 부탁") == ("A3.5",)
    assert extract_shades("3D-Master 2L1.5 적용") == ("2L1.5",)
    # 비표준 토큰(D1 은 VITA 에 없음)은 추출하지 않는다
    assert extract_shades("D1 어쩌고") == ()


def test_first_shade_only() -> None:
    assert extract_from_note("A2 then B1 cervical").shade == "A2"


def test_tooth_fdi_extraction() -> None:
    assert extract_tooth_numbers("#36, 37 그리고 24") == ("36", "37", "24")


def test_tooth_no_false_positive_from_numbers() -> None:
    # 연도/차트번호/Platform Size 등은 FDI 로 오인하지 않는다
    assert extract_tooth_numbers("2026-06-04 접수, chart 2160, TS III 5.0x6.0") == ()


def test_material_zir_keyword() -> None:
    assert extract_materials("Zir cr.") == ("zirconia",)
    assert extract_materials("지르코니아 크라운") == ("zirconia",)
    assert extract_materials("PFM 보철") == ("pfm",)


def test_material_dedupe_and_order() -> None:
    assert extract_materials("zirconia and gold, 지르 추가") == ("zirconia", "gold")


def test_empty_note() -> None:
    res = extract_from_note("   ")
    assert res.shade is None
    assert res.tooth_numbers == ()
    assert res.materials == ()
