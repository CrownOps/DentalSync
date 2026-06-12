"""Type B 룰 엔진 테스트 — 치식/날짜/납기."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.services.type_b_rules import (
    normalize_date,
    score_date,
    score_due_date,
    score_tooth_numbers,
)


# --------------------------------------------------------------------------- #
# 치식 — 경계값 10/11/48/49 + 복수/범위
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "rule_pass"),
    [
        ("10", 0.0),  # tooth 0 → 범위 밖
        ("11", 1.0),  # 하한
        ("48", 1.0),  # 상한
        ("49", 0.0),  # tooth 9 → 범위 밖
        ("51", 0.0),  # quadrant 5 → 범위 밖
        ("", 0.0),
        ("abc", 0.0),
    ],
)
def test_tooth_boundaries(raw: str, rule_pass: float) -> None:
    assert score_tooth_numbers(raw).rule_pass == rule_pass


def test_tooth_multiple() -> None:
    r = score_tooth_numbers("11, 12")
    assert r.rule_pass == 1.0
    assert r.teeth == ("11", "12")


def test_tooth_bridge_range() -> None:
    r = score_tooth_numbers("11-13")
    assert r.rule_pass == 1.0
    assert r.teeth == ("11", "12", "13")


def test_tooth_range_out_of_quadrant_is_partial() -> None:
    r = score_tooth_numbers("18-21")  # 사분면 경계 넘음 → 모호
    assert r.rule_pass == 0.5


def test_tooth_reversed_range_is_partial() -> None:
    assert score_tooth_numbers("13-11").rule_pass == 0.5


def test_tooth_range_out_of_fdi_fails() -> None:
    assert score_tooth_numbers("11-19").rule_pass == 0.0  # 19 범위 밖


# --------------------------------------------------------------------------- #
# 날짜 — 표기 변형 10+ 케이스
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "iso"),
    [
        ("2026-06-15", "2026-06-15"),
        ("2026.06.15", "2026-06-15"),
        ("2026/6/15", "2026-06-15"),
        ("26.6.15", "2026-06-15"),
        ("26-06-15", "2026-06-15"),
        ("2026년 6월 15일", "2026-06-15"),
        ("26년 6월 15일", "2026-06-15"),
        ("20260615", "2026-06-15"),
    ],
)
def test_date_full_valid(raw: str, iso: str) -> None:
    r = score_date(raw)
    assert r.rule_pass == 1.0
    assert r.iso == iso


@pytest.mark.parametrize("raw", ["6/15", "6월 15일", "6.15"])
def test_date_month_day_only_is_partial(raw: str) -> None:
    r = score_date(raw)
    assert r.rule_pass == 0.5
    assert r.iso is None


@pytest.mark.parametrize("raw", ["2026-13-15", "2026-06-40", "2026/02/30", "abc", "15/20"])
def test_date_invalid(raw: str) -> None:
    r = score_date(raw)
    assert r.rule_pass == 0.0
    assert r.iso is None


@pytest.mark.parametrize(
    ("raw", "iso"),
    [
        ("2026-06-04T09:00:00", "2026-06-04"),  # ISO datetime (layout due_date 예시)
        ("2026-06-04 09:00", "2026-06-04"),
        ("2026.6.4 9:30", "2026-06-04"),
        ("2026년 6월 4일 오전 9시", "2026-06-04"),
        ("2026년 6월 4일 9시 30분", "2026-06-04"),
    ],
)
def test_date_with_time_suffix_uses_date_part(raw: str, iso: str) -> None:
    """납기(datetime 타입)는 시간 접미를 무시하고 날짜부만 정규화한다."""
    r = score_date(raw)
    assert r.rule_pass == 1.0
    assert r.iso == iso


def test_normalize_date_helper() -> None:
    assert normalize_date("26.6.15") == "2026-06-15"
    assert normalize_date("6/15") is None  # 연도 없음
    assert normalize_date("nope") is None


# --------------------------------------------------------------------------- #
# 납기 — due_date >= received_at
# --------------------------------------------------------------------------- #
def test_due_after_received_passes() -> None:
    r = score_due_date("2026-06-20", date(2026, 6, 1))
    assert r.rule_pass == 1.0
    assert r.iso == "2026-06-20"


def test_due_equal_received_passes() -> None:
    assert score_due_date("2026-06-01", date(2026, 6, 1)).rule_pass == 1.0


def test_due_before_received_fails() -> None:
    assert score_due_date("2026-01-01", date(2026, 6, 1)).rule_pass == 0.0  # 역전


def test_due_accepts_datetime_received() -> None:
    assert score_due_date("2026-06-20", datetime(2026, 6, 1, 9, 0)).rule_pass == 1.0


def test_due_no_received_uses_date_validity() -> None:
    assert score_due_date("2026-06-20", None).rule_pass == 1.0


def test_due_invalid_date_fails() -> None:
    assert score_due_date("2026-13-01", date(2026, 1, 1)).rule_pass == 0.0


def test_due_partial_when_year_missing() -> None:
    r = score_due_date("6/15", date(2026, 1, 1))
    assert r.rule_pass == 0.5
    assert r.iso is None
