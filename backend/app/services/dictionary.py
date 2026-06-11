"""도메인 사전 매처.

YAML 사전(표준어 + 동의어/오기 변형)을 로드(init 시 1회 I/O)하고, 매칭은 순수하게
수행한다. 정확 매칭 1.0 / 유사 보정 0.7(rapidfuzz, 임계 외부화) / 미매칭 0.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from rapidfuzz import fuzz, process

from app.core.config import Settings

EXACT_SCORE = 1.0
FUZZY_SCORE = 0.7
MISS_SCORE = 0.3


def _normalize(text: str) -> str:
    return text.strip().lower()


@dataclass(frozen=True)
class DictMatchResult:
    matched_term: str | None
    score: float
    method: str  # "exact" | "fuzzy" | "miss"


@dataclass(frozen=True)
class _Category:
    standards: tuple[str, ...]
    exact: dict[str, str]  # normalized(변형) -> 표준어
    candidates: tuple[str, ...]  # 유사 매칭 후보(normalized 변형)
    candidate_to_standard: dict[str, str]


class DictMatcher:
    def __init__(self, catalog: dict[str, _Category], *, fuzzy_threshold: float = 85.0) -> None:
        self._catalog = catalog
        self._threshold = fuzzy_threshold

    # --- 로딩 ---------------------------------------------------------------
    @classmethod
    def from_dir(cls, directory: Path, *, fuzzy_threshold: float = 85.0) -> DictMatcher:
        catalog: dict[str, _Category] = {}
        for path in sorted(Path(directory).glob("*.yaml")):
            data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            category = data.get("category") or path.stem
            catalog[category] = cls._build_category(data.get("terms", []))
        return cls(catalog, fuzzy_threshold=fuzzy_threshold)

    @classmethod
    def from_settings(cls, settings: Settings) -> DictMatcher:
        return cls.from_dir(
            settings.domain_dict_dir, fuzzy_threshold=settings.dict_fuzzy_threshold
        )

    @staticmethod
    def _build_category(terms: list[dict[str, Any]]) -> _Category:
        standards: list[str] = []
        exact: dict[str, str] = {}
        candidate_to_standard: dict[str, str] = {}
        for term in terms:
            standard = term["standard"]
            standards.append(standard)
            variants = {standard, *term.get("synonyms", [])}
            for variant in variants:
                norm = _normalize(str(variant))
                if not norm:
                    continue
                exact.setdefault(norm, standard)
                candidate_to_standard.setdefault(norm, standard)
        return _Category(
            standards=tuple(standards),
            exact=exact,
            candidates=tuple(candidate_to_standard.keys()),
            candidate_to_standard=candidate_to_standard,
        )

    # --- 조회 ---------------------------------------------------------------
    def applies(self, category: str) -> bool:
        """해당 카테고리 사전이 존재하는지(없으면 dict_match 항 제외 대상)."""
        return category in self._catalog

    def categories(self) -> set[str]:
        return set(self._catalog)

    def match(self, category: str, text: str) -> DictMatchResult:
        cat = self._catalog.get(category)
        if cat is None:
            raise KeyError(f"사전에 없는 카테고리: {category}")

        norm = _normalize(text)
        if not norm:
            return DictMatchResult(None, MISS_SCORE, "miss")

        standard = cat.exact.get(norm)
        if standard is not None:
            return DictMatchResult(standard, EXACT_SCORE, "exact")

        best = process.extractOne(norm, cat.candidates, scorer=fuzz.WRatio)
        if best is not None and best[1] >= self._threshold:
            return DictMatchResult(cat.candidate_to_standard[best[0]], FUZZY_SCORE, "fuzzy")

        return DictMatchResult(None, MISS_SCORE, "miss")
