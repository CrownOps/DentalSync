"""Shade — 쉐이드 표기 영역 색상/도형 마킹 인식 (PIL). LLM 0회.

쉐이드 선택지 셀(bbox) 목록에서 펜 마킹(빨강/파랑 동그라미 등)이 있는 셀을 찾아
VITA 코드로 매핑한다. 매핑은 도메인 사전(DictMatcher, shade 카테고리)을 재사용해
표기 변형(소문자 등)을 표준 코드로 정규화한다.

쉐이드는 치명(critical) 필드 — 적용 임계값(0.95)을 flags 에 명시해 스코어링/HITL
단계가 그대로 사용한다. 함수는 순수(외부 I/O 0).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from PIL import Image

from app.services.dictionary import DictMatcher

# bbox = (x, y, width, height) — 픽셀 좌표
BBox = tuple[int, int, int, int]

PASS_FULL = 1.0
PASS_FAIL = 0.0

SHADE_CATEGORY = "shade"

# 펜 색 판정(RGB) — 빨강/파랑 펜과 검정 잉크
_CHANNEL_MIN = 110
_CHANNEL_GAP = 45
_DARK_MAX = 90


@dataclass(frozen=True)
class CellScan:
    label: str
    mark_ratio: float
    pen_color: str | None  # "red" | "blue" | "dark" | None
    marked: bool


@dataclass(frozen=True)
class ShadeResult:
    """스코어링 단계에서 합성 가능한 (value, rule_pass, debug_info) + flags."""

    value: str | None
    rule_pass: float
    debug_info: dict[str, Any]
    flags: dict[str, Any]


def _classify_pixel(r: int, g: int, b: int) -> str | None:
    if r >= _CHANNEL_MIN and r - g >= _CHANNEL_GAP and r - b >= _CHANNEL_GAP:
        return "red"
    if b >= _CHANNEL_MIN and b - r >= _CHANNEL_GAP and b - g >= _CHANNEL_GAP:
        return "blue"
    if r < _DARK_MAX and g < _DARK_MAX and b < _DARK_MAX:
        return "dark"
    return None


def scan_cell(image: Image.Image, label: str, bbox: BBox, mark_ratio_min: float) -> CellScan:
    """단일 쉐이드 셀의 펜 마킹 비율을 측정한다."""
    x, y, w, h = bbox
    crop = image.convert("RGB").crop((x, y, x + w, y + h))
    raw = crop.tobytes()  # RGB 인터리브드 바이트
    total = len(raw) // 3
    if total == 0:
        return CellScan(label, 0.0, None, marked=False)

    counts = {"red": 0, "blue": 0, "dark": 0}
    for i in range(0, total * 3, 3):
        kind = _classify_pixel(raw[i], raw[i + 1], raw[i + 2])
        if kind is not None:
            counts[kind] += 1
    best_color, best_count = max(counts.items(), key=lambda kv: kv[1])
    mark_ratio = best_count / total
    marked = mark_ratio >= mark_ratio_min
    return CellScan(label, mark_ratio, best_color if marked else None, marked=marked)


def detect_shade(
    image: Image.Image,
    cells: Mapping[str, BBox],
    matcher: DictMatcher,
    *,
    mark_ratio_min: float = 0.03,
    critical_threshold: float = 0.95,
) -> ShadeResult:
    """쉐이드 선택지 셀들에서 마킹된 코드를 찾아 VITA 표준 코드로 매핑한다."""
    scans = [scan_cell(image, label, bbox, mark_ratio_min) for label, bbox in cells.items()]
    marked = [s for s in scans if s.marked]

    flags: dict[str, Any] = {"critical": True, "threshold": critical_threshold}
    debug_info: dict[str, Any] = {
        "cells": [
            {
                "label": s.label,
                "mark_ratio": round(s.mark_ratio, 4),
                "pen_color": s.pen_color,
                "marked": s.marked,
            }
            for s in scans
        ],
        "marked_count": len(marked),
        "mark_ratio_min": mark_ratio_min,
    }

    if len(marked) != 1:
        debug_info["reason"] = "multiple_marks" if len(marked) > 1 else "no_mark"
        return ShadeResult(None, PASS_FAIL, debug_info, flags)

    # 사전 재사용: 셀 라벨 표기 변형(a2 등) → VITA 표준 코드(A2)
    match = matcher.match(SHADE_CATEGORY, marked[0].label)
    debug_info["dict_match"] = {
        "input": marked[0].label,
        "matched": match.matched_term,
        "method": match.method,
    }
    if match.matched_term is None:
        debug_info["reason"] = "label_not_in_shade_dict"
        return ShadeResult(None, PASS_FAIL, debug_info, flags)

    return ShadeResult(match.matched_term, PASS_FULL, debug_info, flags)
