"""type_a_rules.py — 옵션 매칭 룰 테스트."""

from __future__ import annotations

from app.services.type_a_rules import (
    PASS_FAIL,
    PASS_FULL,
    PASS_PARTIAL,
    score_boolean,
    score_multi_select,
    score_select,
)

_SPECIAL_FLAG_OPTIONS = (
    "scrp",
    "hook",
    "embrasure",
    "inner_adjustment",
    "contact",
    "bite",
    "etc",
)


class TestScoreBoolean:
    def test_true_variants(self) -> None:
        for raw in ("true", "YES", "예", "체크", "V"):
            r = score_boolean(raw)
            assert (r.value, r.rule_pass) == ("true", PASS_FULL), raw

    def test_false_variants(self) -> None:
        for raw in ("false", "No", "아니오", "X"):
            r = score_boolean(raw)
            assert (r.value, r.rule_pass) == ("false", PASS_FULL), raw

    def test_ambiguous_fails(self) -> None:
        r = score_boolean("글쎄요")
        assert r.value is None
        assert r.rule_pass == PASS_FAIL


class TestScoreSelect:
    def test_exact_match(self) -> None:
        r = score_select("vital", ("vital", "non_vital", "unknown"))
        assert (r.value, r.rule_pass) == ("vital", PASS_FULL)

    def test_normalization_absorbs_space_and_case(self) -> None:
        r = score_select("Non Vital", ("vital", "non_vital", "unknown"))
        assert (r.value, r.rule_pass) == ("non_vital", PASS_FULL)

    def test_miss_fails(self) -> None:
        r = score_select("기타값", ("vital", "non_vital"))
        assert r.value is None
        assert r.rule_pass == PASS_FAIL

    def test_blank_fails(self) -> None:
        r = score_select("  ", ("vital",))
        assert r.rule_pass == PASS_FAIL


class TestScoreMultiSelect:
    def test_json_array_input(self) -> None:
        r = score_multi_select('["scrp"]', _SPECIAL_FLAG_OPTIONS)
        assert (r.value, r.rule_pass) == ('["scrp"]', PASS_FULL)

    def test_delimiter_separated_input(self) -> None:
        r = score_multi_select("scrp, hook", _SPECIAL_FLAG_OPTIONS)
        assert (r.value, r.rule_pass) == ('["scrp", "hook"]', PASS_FULL)

    def test_partial_match_is_partial_pass(self) -> None:
        # 미해석 토큰이 섞이면 0.5 — HITL 검토 후보로 강등
        r = score_multi_select("scrp 정체불명", _SPECIAL_FLAG_OPTIONS)
        assert r.value == '["scrp"]'
        assert r.rule_pass == PASS_PARTIAL

    def test_no_match_fails(self) -> None:
        r = score_multi_select("전부 미등록 토큰", _SPECIAL_FLAG_OPTIONS)
        assert r.value is None
        assert r.rule_pass == PASS_FAIL

    def test_empty_fails(self) -> None:
        r = score_multi_select("", _SPECIAL_FLAG_OPTIONS)
        assert r.rule_pass == PASS_FAIL
