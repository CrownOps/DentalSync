"""필드별 자동 정확도 집계 — 파일럿 70% 목표 측정용.

자동 확정값(raw/system corrected)과 최종 확정값이 일치하는지를
training_labels.corrected_by 로 판별:
- corrected_by = 'system' → 자동 정확 (사람이 수정하지 않음)
- corrected_by = 'human'  → 자동 오류 (사람이 수정함)
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.db.models import OrderField, TrainingLabel
from app.domain.enums import CorrectedBy


@dataclass
class FieldAccuracy:
    field_key: str
    total: int
    auto_correct: int
    accuracy: float


def compute_field_accuracy(session: Session) -> list[FieldAccuracy]:
    """confirmed 의뢰서의 필드별 자동 정확도 집계.

    training_labels 기준으로 집계한다:
    - corrected_by = 'human' → 자동값과 최종값이 달랐음
    - corrected_by = 'system' → 자동값 그대로 확정됨
    """
    rows = (
        session.query(
            OrderField.field_key,
            func.count(TrainingLabel.id).label("total"),
            func.sum(
                case((TrainingLabel.corrected_by == CorrectedBy.system, 1), else_=0)
            ).label("auto_correct"),
        )
        .join(TrainingLabel, TrainingLabel.order_field_id == OrderField.id)
        .group_by(OrderField.field_key)
        .all()
    )

    result = []
    for field_key, total, auto_correct in rows:
        total = total or 0
        auto_correct = auto_correct or 0
        accuracy = auto_correct / total if total > 0 else 0.0
        result.append(FieldAccuracy(
            field_key=field_key,
            total=total,
            auto_correct=auto_correct,
            accuracy=accuracy,
        ))

    return sorted(result, key=lambda x: x.accuracy)
