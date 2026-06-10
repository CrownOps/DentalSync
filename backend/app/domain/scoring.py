"""스코어링 설정 도메인 모델."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ScoringWeights(BaseModel):
    ocr_conf: float = Field(ge=0.0, le=1.0)
    rule_pass: float = Field(ge=0.0, le=1.0)
    dict_match: float = Field(ge=0.0, le=1.0)

    def total(self) -> float:
        return self.ocr_conf + self.rule_pass + self.dict_match


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
