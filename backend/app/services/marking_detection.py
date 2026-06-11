"""Type A — 체크박스/마킹 감지 (OpenCV). LLM 0회.

템플릿 정의의 체크박스 bbox 목록을 받아 각 영역의 마킹 여부를 판정한다.
판정 신호 2종: 잉크 밀도(흑연/검정 펜) + 색상 마킹(빨강/파랑 펜, HSV).

규칙: 단일 마킹 명확 → rule_pass=1.0 / 복수 마킹·모호·무마킹 → rule_pass=0.0.
판정 파라미터는 Settings 로 외부화(파일럿 튜닝 대상). 함수는 순수(외부 I/O 0).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from app.core.config import Settings

Image = NDArray[np.uint8]
# bbox = (x, y, width, height) — 픽셀 좌표
BBox = tuple[int, int, int, int]

PASS_FULL = 1.0
PASS_FAIL = 0.0

_INK_GRAY_MAX = 160  # 이 값 미만 그레이스케일 픽셀을 잉크로 간주
_PEN_SAT_MIN = 70
_PEN_VAL_MIN = 60


@dataclass(frozen=True)
class MarkingParams:
    """판정 임계값 — 파일럿에서 튜닝한다."""

    density_marked: float = 0.06
    density_ambiguous: float = 0.025
    color_ratio_marked: float = 0.04
    border_margin: float = 0.18

    @classmethod
    def from_settings(cls, settings: Settings) -> MarkingParams:
        return cls(
            density_marked=settings.marking_density_marked,
            density_ambiguous=settings.marking_density_ambiguous,
            color_ratio_marked=settings.marking_color_ratio_marked,
            border_margin=settings.marking_border_margin,
        )


@dataclass(frozen=True)
class BoxScan:
    """단일 체크박스 스캔 결과."""

    label: str
    ink_density: float
    color_ratio: float
    pen_color: str | None  # "red" | "blue" | None
    marked: bool
    ambiguous: bool


@dataclass(frozen=True)
class MarkingResult:
    """스코어링 단계에서 합성 가능한 (value, rule_pass, debug_info)."""

    value: str | None
    rule_pass: float
    debug_info: dict[str, Any]


def _crop_interior(image: Image, bbox: BBox, margin: float) -> Image:
    """bbox 내부에서 테두리(margin 비율)를 제외한 영역을 잘라낸다."""
    x, y, w, h = bbox
    mx, my = int(w * margin), int(h * margin)
    x0, y0 = max(x + mx, 0), max(y + my, 0)
    x1, y1 = min(x + w - mx, image.shape[1]), min(y + h - my, image.shape[0])
    if x1 <= x0 or y1 <= y0:
        return image[0:0, 0:0]
    return image[y0:y1, x0:x1]


def _pen_masks(bgr: Image) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    """HSV 기반 빨강/파랑 펜 마스크."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    vivid = (s >= _PEN_SAT_MIN) & (v >= _PEN_VAL_MIN)
    red = vivid & ((h <= 10) | (h >= 170))
    blue = vivid & (h >= 90) & (h <= 140)
    return red, blue


def scan_box(image: Image, label: str, bbox: BBox, params: MarkingParams) -> BoxScan:
    """단일 체크박스 영역의 마킹 신호를 측정한다."""
    interior = _crop_interior(image, bbox, params.border_margin)
    if interior.size == 0:
        return BoxScan(label, 0.0, 0.0, None, marked=False, ambiguous=False)

    gray = cv2.cvtColor(interior, cv2.COLOR_BGR2GRAY)
    ink_density = float((gray < _INK_GRAY_MAX).mean())

    red, blue = _pen_masks(interior)
    red_ratio, blue_ratio = float(red.mean()), float(blue.mean())
    color_ratio = max(red_ratio, blue_ratio)
    pen_color: str | None = None
    if color_ratio >= params.color_ratio_marked:
        pen_color = "red" if red_ratio >= blue_ratio else "blue"

    marked = ink_density >= params.density_marked or color_ratio >= params.color_ratio_marked
    ambiguous = not marked and ink_density >= params.density_ambiguous
    return BoxScan(label, ink_density, color_ratio, pen_color, marked=marked, ambiguous=ambiguous)


def detect_checkbox_group(
    image: Image,
    options: Mapping[str, BBox],
    params: MarkingParams,
) -> MarkingResult:
    """체크박스 그룹(예: 보철 종류 4지선다)에서 선택값을 판정한다."""
    scans = [scan_box(image, label, bbox, params) for label, bbox in options.items()]
    marked = [s for s in scans if s.marked]
    ambiguous = [s for s in scans if s.ambiguous]

    debug_info: dict[str, Any] = {
        "boxes": [
            {
                "label": s.label,
                "ink_density": round(s.ink_density, 4),
                "color_ratio": round(s.color_ratio, 4),
                "pen_color": s.pen_color,
                "marked": s.marked,
                "ambiguous": s.ambiguous,
            }
            for s in scans
        ],
        "marked_count": len(marked),
        "ambiguous_count": len(ambiguous),
        "params": {
            "density_marked": params.density_marked,
            "density_ambiguous": params.density_ambiguous,
            "color_ratio_marked": params.color_ratio_marked,
        },
    }

    if len(marked) == 1 and not ambiguous:
        return MarkingResult(marked[0].label, PASS_FULL, debug_info)

    if len(marked) > 1:
        debug_info["reason"] = "multiple_marks"
    elif ambiguous:
        debug_info["reason"] = "ambiguous_marks"
    else:
        debug_info["reason"] = "no_mark"
    return MarkingResult(None, PASS_FAIL, debug_info)
