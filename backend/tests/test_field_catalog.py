"""field_catalog.py — 레이아웃 필드 카탈로그 테스트."""

from __future__ import annotations

from app.services.field_catalog import get_field_catalog, get_field_spec


def test_catalog_loads_all_sections() -> None:
    catalog = get_field_catalog()
    # 레이아웃 v1.1.0 대표 필드들이 모두 등재되어야 한다
    for key in ("clinic_name", "tooth_numbers", "shade", "special_flags", "priority"):
        assert key in catalog, key


def test_special_flags_spec() -> None:
    spec = get_field_spec("special_flags")
    assert spec is not None
    assert spec.layout_type == "array"
    assert spec.has_options
    assert "scrp" in spec.item_options
    assert spec.llm_allowed  # source=ocr_or_llm — 단, 라우팅은 옵션 매칭(A)을 우선한다


def test_plain_ocr_text_spec_disallows_llm() -> None:
    spec = get_field_spec("clinic_name")
    assert spec is not None
    assert spec.layout_type == "text"
    assert not spec.has_options
    assert not spec.llm_allowed


def test_unknown_key_returns_none() -> None:
    assert get_field_spec("없는_키") is None
