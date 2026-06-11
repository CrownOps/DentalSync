"""Type A 마킹 감지 테스트 — 단일/복수/무마킹 + 색상 펜 변형 + 모호."""

from __future__ import annotations

import cv2
import numpy as np

from app.services.marking_detection import (
    BBox,
    MarkingParams,
    detect_checkbox_group,
    scan_box,
)

# 4지선다 체크박스 시트 (60x60 박스 4개)
OPTIONS: dict[str, BBox] = {
    "크라운": (50, 100, 60, 60),
    "브릿지": (150, 100, 60, 60),
    "임플란트": (250, 100, 60, 60),
    "틀니": (350, 100, 60, 60),
}

BLACK = (0, 0, 0)
RED_BGR = (0, 0, 255)
BLUE_BGR = (255, 0, 0)


def _sheet() -> np.ndarray:
    """흰 캔버스 + 체크박스 테두리만 그린 빈 시트."""
    img = np.full((300, 500, 3), 255, dtype=np.uint8)
    for x, y, w, h in OPTIONS.values():
        cv2.rectangle(img, (x, y), (x + w, y + h), BLACK, 2)
    return img


def _mark_x(img: np.ndarray, bbox: BBox, color: tuple[int, int, int] = BLACK) -> None:
    x, y, w, h = bbox
    pad = 12
    cv2.line(img, (x + pad, y + pad), (x + w - pad, y + h - pad), color, 5)
    cv2.line(img, (x + w - pad, y + pad), (x + pad, y + h - pad), color, 5)


def _params() -> MarkingParams:
    return MarkingParams()


# --- 단일/복수/무마킹 --------------------------------------------------------
def test_single_black_mark() -> None:
    img = _sheet()
    _mark_x(img, OPTIONS["브릿지"])
    result = detect_checkbox_group(img, OPTIONS, _params())
    assert result.value == "브릿지"
    assert result.rule_pass == 1.0
    assert result.debug_info["marked_count"] == 1


def test_no_mark_fails() -> None:
    result = detect_checkbox_group(_sheet(), OPTIONS, _params())
    assert result.value is None
    assert result.rule_pass == 0.0
    assert result.debug_info["reason"] == "no_mark"


def test_multiple_marks_fail() -> None:
    img = _sheet()
    _mark_x(img, OPTIONS["크라운"])
    _mark_x(img, OPTIONS["틀니"])
    result = detect_checkbox_group(img, OPTIONS, _params())
    assert result.value is None
    assert result.rule_pass == 0.0
    assert result.debug_info["reason"] == "multiple_marks"
    assert result.debug_info["marked_count"] == 2


# --- 색상 펜 변형 ------------------------------------------------------------
def test_red_pen_mark() -> None:
    img = _sheet()
    _mark_x(img, OPTIONS["임플란트"], RED_BGR)
    result = detect_checkbox_group(img, OPTIONS, _params())
    assert result.value == "임플란트"
    assert result.rule_pass == 1.0
    box = next(b for b in result.debug_info["boxes"] if b["label"] == "임플란트")
    assert box["pen_color"] == "red"


def test_blue_pen_mark() -> None:
    img = _sheet()
    _mark_x(img, OPTIONS["크라운"], BLUE_BGR)
    result = detect_checkbox_group(img, OPTIONS, _params())
    assert result.value == "크라운"
    box = next(b for b in result.debug_info["boxes"] if b["label"] == "크라운")
    assert box["pen_color"] == "blue"


def test_red_circle_mark() -> None:
    """X 가 아닌 동그라미 마킹도 색상 신호로 감지."""
    img = _sheet()
    x, y, w, h = OPTIONS["틀니"]
    cv2.circle(img, (x + w // 2, y + h // 2), 20, RED_BGR, 4)
    result = detect_checkbox_group(img, OPTIONS, _params())
    assert result.value == "틀니"
    assert result.rule_pass == 1.0


# --- 모호 판정 / 파라미터 외부화 --------------------------------------------
def test_ambiguous_mark_fails() -> None:
    """동일 마킹이라도 임계값을 올리면 모호(gray zone) → 0.0."""
    img = _sheet()
    _mark_x(img, OPTIONS["브릿지"])
    strict = MarkingParams(
        density_marked=0.90,  # 사실상 도달 불가
        density_ambiguous=0.01,
        color_ratio_marked=0.90,
    )
    result = detect_checkbox_group(img, OPTIONS, strict)
    assert result.value is None
    assert result.rule_pass == 0.0
    assert result.debug_info["reason"] == "ambiguous_marks"


def test_params_from_settings() -> None:
    from app.core.config import Settings

    params = MarkingParams.from_settings(Settings(marking_density_marked=0.11))
    assert params.density_marked == 0.11  # 외부화 확인


# --- 개별 스캔 / 경계 --------------------------------------------------------
def test_scan_box_empty_region() -> None:
    img = _sheet()
    scan = scan_box(img, "x", (490, 290, 60, 60), _params())  # 캔버스 밖으로 걸침
    assert scan.marked is False


def test_border_excluded_from_density() -> None:
    """빈 박스는 테두리만 있으므로 마킹으로 오인하지 않아야 한다."""
    img = _sheet()
    scan = scan_box(img, "크라운", OPTIONS["크라운"], _params())
    assert scan.marked is False
    assert scan.ink_density < 0.02


def test_debug_info_contains_all_boxes() -> None:
    img = _sheet()
    _mark_x(img, OPTIONS["크라운"])
    result = detect_checkbox_group(img, OPTIONS, _params())
    assert {b["label"] for b in result.debug_info["boxes"]} == set(OPTIONS)
    assert "params" in result.debug_info
