"""도메인 사전 매처 테스트 — 정확/유사/미매칭."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.dictionary import DictMatcher


@pytest.fixture(scope="module")
def matcher() -> DictMatcher:
    return DictMatcher.from_settings(Settings())


def test_categories_loaded(matcher: DictMatcher) -> None:
    assert {"material", "prosthesis", "shade", "abutment"} <= matcher.categories()


def test_exact_standard(matcher: DictMatcher) -> None:
    r = matcher.match("material", "지르코니아")
    assert r.method == "exact"
    assert r.score == 1.0
    assert r.matched_term == "지르코니아"


@pytest.mark.parametrize(
    ("category", "text", "expected"),
    [
        ("material", "질코니아", "지르코니아"),  # 동의어/오기
        ("material", "zirconia", "지르코니아"),  # 영문
        ("material", "P.F.M", "PFM"),
        ("prosthesis", "브리지", "브릿지"),
        ("prosthesis", "crown", "크라운"),
        ("shade", "a1", "A1"),  # 대소문자
        ("abutment", "커스텀", "커스텀 어버트먼트"),
    ],
)
def test_exact_synonyms(
    matcher: DictMatcher, category: str, text: str, expected: str
) -> None:
    r = matcher.match(category, text)
    assert r.score == 1.0
    assert r.matched_term == expected


def test_fuzzy_correction(matcher: DictMatcher) -> None:
    # 동의어 목록에 없는 오타 → rapidfuzz 유사 보정 0.7
    r = matcher.match("material", "지르코니야")
    assert r.method == "fuzzy"
    assert r.score == 0.7
    assert r.matched_term == "지르코니아"


def test_miss_returns_low_score(matcher: DictMatcher) -> None:
    r = matcher.match("material", "플라스틱")
    assert r.method == "miss"
    assert r.score == 0.3
    assert r.matched_term is None


def test_empty_text_is_miss(matcher: DictMatcher) -> None:
    assert matcher.match("material", "   ").method == "miss"


def test_applies(matcher: DictMatcher) -> None:
    assert matcher.applies("material") is True
    assert matcher.applies("patient_name") is False  # 사전 없음 → dict_match 제외 대상


def test_unknown_category_raises(matcher: DictMatcher) -> None:
    with pytest.raises(KeyError):
        matcher.match("patient_name", "홍길동")


def test_threshold_externalized() -> None:
    # 임계 유사도를 100 으로 올리면 오타는 더 이상 유사 매칭되지 않음
    strict = DictMatcher.from_settings(Settings(dict_fuzzy_threshold=100.0))
    assert strict.match("material", "지르코니야").method == "miss"
