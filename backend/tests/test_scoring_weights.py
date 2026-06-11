"""가중치 재정규화 — dict_match 제외 시 남은 가중치가 1.0 으로 재정규화되는지."""

from __future__ import annotations

import pytest

from app.domain.scoring import ScoringWeights


def _weights() -> ScoringWeights:
    return ScoringWeights(ocr_conf=0.5, rule_pass=0.3, dict_match=0.2)


def test_full_components_unchanged() -> None:
    out = _weights().normalized_for(["ocr_conf", "rule_pass", "dict_match"])
    assert out == pytest.approx({"ocr_conf": 0.5, "rule_pass": 0.3, "dict_match": 0.2})
    assert sum(out.values()) == pytest.approx(1.0)


def test_dict_excluded_renormalizes_to_one() -> None:
    out = _weights().normalized_for(["ocr_conf", "rule_pass"])
    # 0.5/0.8=0.625, 0.3/0.8=0.375
    assert out == pytest.approx({"ocr_conf": 0.625, "rule_pass": 0.375})
    assert sum(out.values()) == pytest.approx(1.0)


def test_single_component_normalizes_to_one() -> None:
    out = _weights().normalized_for(["rule_pass"])
    assert out == pytest.approx({"rule_pass": 1.0})


def test_unknown_component_raises() -> None:
    with pytest.raises(ValueError, match="알 수 없는"):
        _weights().normalized_for(["ocr_conf", "bogus"])


def test_empty_components_raises() -> None:
    with pytest.raises(ValueError, match="비어"):
        _weights().normalized_for([])


def test_zero_total_raises() -> None:
    weights = ScoringWeights(ocr_conf=0.0, rule_pass=0.0, dict_match=0.0)
    with pytest.raises(ValueError, match="합이 0"):
        weights.normalized_for(["dict_match"])


def test_duplicates_collapse() -> None:
    out = _weights().normalized_for(["rule_pass", "rule_pass"])
    assert out == pytest.approx({"rule_pass": 1.0})
