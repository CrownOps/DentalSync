"""scoring.yaml 로더 — 가중치 합/필수 키 검증."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.config import get_settings
from app.domain.scoring import ScoringConfig

_REQUIRED_THRESHOLDS = ("general", "critical")


def load_scoring_config(path: Path | None = None) -> ScoringConfig:
    """YAML 을 읽어 ScoringConfig 로 검증/반환.

    - weights 합계가 1.0 인지 (ScoringConfig 모델에서 검증)
    - thresholds 에 general/critical 키가 모두 존재하는지
    """
    cfg_path = path or get_settings().scoring_config_path
    if not cfg_path.exists():
        raise FileNotFoundError(f"scoring 설정 파일이 없습니다: {cfg_path}")

    raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    thresholds = raw.get("thresholds", {})
    missing = [k for k in _REQUIRED_THRESHOLDS if k not in thresholds]
    if missing:
        raise ValueError(f"thresholds 필수 키 누락: {missing}")

    return ScoringConfig.model_validate(raw)


@lru_cache
def get_scoring_config() -> ScoringConfig:
    return load_scoring_config()
