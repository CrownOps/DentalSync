"""스코어링 설정 도메인 모델."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field, model_validator

COMPONENTS = ("ocr_conf", "rule_pass", "dict_match")


class ScoringWeights(BaseModel):
    ocr_conf: float = Field(ge=0.0, le=1.0)
    rule_pass: float = Field(ge=0.0, le=1.0)
    dict_match: float = Field(ge=0.0, le=1.0)

    def total(self) -> float:
        return self.ocr_conf + self.rule_pass + self.dict_match

    def normalized_for(self, components: Iterable[str]) -> dict[str, float]:
        """주어진 컴포넌트만 남기고 합이 1.0 이 되도록 가중치 재정규화.

        사전에 해당 없는 필드는 dict_match 를 제외하고 호출하면, 남은 가중치가
        비율을 유지한 채 1.0 으로 재정규화된다.
        """
        selected = list(dict.fromkeys(components))  # 중복 제거, 순서 유지
        if not selected:
            raise ValueError("컴포넌트가 비어 있습니다")
        unknown = [c for c in selected if c not in COMPONENTS]
        if unknown:
            raise ValueError(f"알 수 없는 컴포넌트: {unknown}")

        weights = {c: getattr(self, c) for c in selected}
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("선택한 컴포넌트의 가중치 합이 0 입니다")
        return {c: w / total for c, w in weights.items()}


class ScoringThresholds(BaseModel):
    general: float = Field(ge=0.0, le=1.0)
    critical: float = Field(ge=0.0, le=1.0)


class ScoringConfig(BaseModel):
    weights: ScoringWeights
    thresholds: ScoringThresholds
    critical_fields: list[str]

    @model_validator(mode="after")
    def _check_weights_sum(self) -> ScoringConfig:
        total = self.weights.total()
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"가중치 합은 1.0 이어야 합니다 (현재: {total})")
        return self

    def threshold_for(self, field_key: str) -> float:
        """필드별 적용 임계값 — critical 필드는 critical, 그 외는 general."""
        return (
            self.thresholds.critical
            if field_key in self.critical_fields
            else self.thresholds.general
        )
