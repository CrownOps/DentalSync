"""scoring.yaml 로더 검증."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from app.core.scoring import load_scoring_config


def test_load_default_scoring_config() -> None:
    cfg = load_scoring_config()
    assert cfg.weights.ocr_conf == 0.5
    assert cfg.weights.rule_pass == 0.3
    assert cfg.weights.dict_match == 0.2
    assert abs(cfg.weights.total() - 1.0) < 1e-6
    assert cfg.thresholds.general == 0.90
    assert cfg.thresholds.critical == 0.95
    assert set(cfg.critical_fields) == {"shade", "tooth_numbers", "due_date"}


def test_threshold_for_critical_vs_general() -> None:
    cfg = load_scoring_config()
    assert cfg.threshold_for("shade") == 0.95  # critical
    assert cfg.threshold_for("patient_name") == 0.90  # general


def test_weights_must_sum_to_one(tmp_path: Path) -> None:
    bad = tmp_path / "scoring.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "weights": {"ocr_conf": 0.5, "rule_pass": 0.3, "dict_match": 0.5},
                "thresholds": {"general": 0.9, "critical": 0.95},
                "critical_fields": ["shade"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="가중치 합"):
        load_scoring_config(bad)


def test_missing_threshold_key_raises(tmp_path: Path) -> None:
    bad = tmp_path / "scoring.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "weights": {"ocr_conf": 0.5, "rule_pass": 0.3, "dict_match": 0.2},
                "thresholds": {"general": 0.9},  # critical 누락
                "critical_fields": ["shade"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="critical"):
        load_scoring_config(bad)
