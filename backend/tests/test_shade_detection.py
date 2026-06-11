"""Shade 색상 인식 테스트 — 단일/복수/무마킹, 펜 색 변형, 사전 매핑, critical flags."""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from app.core.config import Settings
from app.services.dictionary import DictMatcher
from app.services.shade_detection import BBox, detect_shade, scan_cell

# 쉐이드 선택지 셀 (80x50 셀 4개)
CELLS: dict[str, BBox] = {
    "A1": (20, 20, 80, 50),
    "A2": (120, 20, 80, 50),
    "A3": (220, 20, 80, 50),
    "B1": (320, 20, 80, 50),
}

RED = (220, 30, 30)
BLUE = (30, 40, 220)
DARK = (40, 40, 40)


@pytest.fixture(scope="module")
def matcher() -> DictMatcher:
    return DictMatcher.from_settings(Settings())


def _sheet() -> Image.Image:
    return Image.new("RGB", (430, 90), (255, 255, 255))


def _circle(img: Image.Image, cell: BBox, color: tuple[int, int, int] = RED) -> None:
    x, y, w, h = cell
    draw = ImageDraw.Draw(img)
    draw.ellipse((x + 8, y + 6, x + w - 8, y + h - 6), outline=color, width=5)


# --- 단일/복수/무마킹 --------------------------------------------------------
def test_single_red_circle(matcher: DictMatcher) -> None:
    img = _sheet()
    _circle(img, CELLS["A2"])
    result = detect_shade(img, CELLS, matcher)
    assert result.value == "A2"
    assert result.rule_pass == 1.0
    assert result.debug_info["marked_count"] == 1


def test_no_mark(matcher: DictMatcher) -> None:
    result = detect_shade(_sheet(), CELLS, matcher)
    assert result.value is None
    assert result.rule_pass == 0.0
    assert result.debug_info["reason"] == "no_mark"


def test_multiple_marks(matcher: DictMatcher) -> None:
    img = _sheet()
    _circle(img, CELLS["A1"])
    _circle(img, CELLS["B1"])
    result = detect_shade(img, CELLS, matcher)
    assert result.value is None
    assert result.rule_pass == 0.0
    assert result.debug_info["reason"] == "multiple_marks"


# --- 펜 색 변형 --------------------------------------------------------------
def test_blue_pen(matcher: DictMatcher) -> None:
    img = _sheet()
    _circle(img, CELLS["A3"], BLUE)
    result = detect_shade(img, CELLS, matcher)
    assert result.value == "A3"
    cell = next(c for c in result.debug_info["cells"] if c["label"] == "A3")
    assert cell["pen_color"] == "blue"


def test_dark_pencil(matcher: DictMatcher) -> None:
    img = _sheet()
    _circle(img, CELLS["B1"], DARK)
    result = detect_shade(img, CELLS, matcher)
    assert result.value == "B1"
    cell = next(c for c in result.debug_info["cells"] if c["label"] == "B1")
    assert cell["pen_color"] == "dark"


# --- 사전 매핑 재사용 --------------------------------------------------------
def test_lowercase_label_mapped_to_vita(matcher: DictMatcher) -> None:
    """셀 라벨 표기 변형(a2)도 사전을 통해 표준 코드(A2)로 정규화."""
    cells: dict[str, BBox] = {"a2": (20, 20, 80, 50), "b1": (120, 20, 80, 50)}
    img = Image.new("RGB", (230, 90), (255, 255, 255))
    _circle(img, cells["a2"])
    result = detect_shade(img, cells, matcher)
    assert result.value == "A2"  # 소문자 → VITA 표준
    assert result.debug_info["dict_match"]["method"] == "exact"


def test_label_not_in_dict_fails(matcher: DictMatcher) -> None:
    cells: dict[str, BBox] = {"Z9": (20, 20, 80, 50)}
    img = Image.new("RGB", (130, 90), (255, 255, 255))
    _circle(img, cells["Z9"])
    result = detect_shade(img, cells, matcher)
    assert result.value is None
    assert result.rule_pass == 0.0
    assert result.debug_info["reason"] == "label_not_in_shade_dict"


# --- critical flags ----------------------------------------------------------
def test_critical_flags_present(matcher: DictMatcher) -> None:
    img = _sheet()
    _circle(img, CELLS["A1"])
    result = detect_shade(img, CELLS, matcher, critical_threshold=0.95)
    assert result.flags == {"critical": True, "threshold": 0.95}


def test_flags_present_even_on_failure(matcher: DictMatcher) -> None:
    result = detect_shade(_sheet(), CELLS, matcher)
    assert result.flags["critical"] is True


def test_scoring_config_threshold_wires_in(matcher: DictMatcher) -> None:
    """scoring.yaml 의 critical 임계값(0.95)을 그대로 flags 로 전달 가능."""
    from app.core.scoring import load_scoring_config

    threshold = load_scoring_config().threshold_for("shade")
    img = _sheet()
    _circle(img, CELLS["A1"])
    result = detect_shade(img, CELLS, matcher, critical_threshold=threshold)
    assert result.flags["threshold"] == 0.95


# --- 개별 셀 스캔 ------------------------------------------------------------
def test_scan_cell_ratio_threshold(matcher: DictMatcher) -> None:
    img = _sheet()
    _circle(img, CELLS["A1"])
    marked = scan_cell(img, "A1", CELLS["A1"], mark_ratio_min=0.01)
    assert marked.marked is True
    strict = scan_cell(img, "A1", CELLS["A1"], mark_ratio_min=0.9)
    assert strict.marked is False  # 임계 상향 → 미마킹 처리(외부화 확인)
