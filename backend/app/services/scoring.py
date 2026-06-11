"""필드별 복합 신뢰도 스코어링 + confirmed/needs_review 분기.

score = w_ocr·ocr_conf + w_rule·rule_pass + w_dict·dict_match
- 가중치/임계값은 config/scoring.yaml 에서 로드(ScoringConfig 주입) — 하드코딩 금지.
- dict_match 미적용 필드(사전 없음)는 해당 항 제외 후 가중치 재정규화(Step 4 재사용).
- 분기: 일반 ≥ general(0.90) / 치명(쉐이드·치식·납기) ≥ critical(0.95) → confirmed,
  forced_hitl 플래그는 점수 무관 needs_review.

스코어링(score_field)은 순수 함수 — 설정은 인자로 주입되며 외부 I/O 가 없다.
저장(persist_scored_fields)은 분리된 함수로 order_fields 4종 일괄 저장을 담당한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Order, OrderField
from app.domain.enums import CorrectedBy, FieldStatus, FieldType, OrderStatus
from app.domain.scoring import ScoringConfig
from app.services.order_status import recompute_order_status

_COMPONENT_RANGE_ERR = "{name} 는 0~1 범위여야 합니다 (현재: {value})"


@dataclass(frozen=True)
class FieldScoreInput:
    """스코어링 입력 — 앞 단계(OCR/룰/사전/LLM) 산출물의 합류 지점."""

    field_key: str
    ocr_conf: float
    rule_pass: float
    dict_match: float | None = None  # None = 사전 미적용 필드(환자명 등)
    forced_hitl: bool = False  # LLM 승급 등으로 HITL 강제된 필드
    extra_flags: dict[str, Any] = field(default_factory=dict)  # model_escalated 등 전달


@dataclass(frozen=True)
class FieldScore:
    """스코어링 결과 — 저장/튜닝 근거 데이터 포함."""

    field_key: str
    score: float
    status: FieldStatus
    threshold: float
    components: dict[str, float]  # ocr_conf/rule_pass(/dict_match) 개별값 보존
    weights: dict[str, float]  # 적용된(재정규화된) 가중치
    flags: dict[str, Any]  # critical/forced_hitl/extra


def _check_range(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(_COMPONENT_RANGE_ERR.format(name=name, value=value))


def score_field(inp: FieldScoreInput, config: ScoringConfig) -> FieldScore:
    """순수 함수: 컴포넌트 + 설정 → 복합 점수와 분기."""
    _check_range("ocr_conf", inp.ocr_conf)
    _check_range("rule_pass", inp.rule_pass)

    components: dict[str, float] = {
        "ocr_conf": inp.ocr_conf,
        "rule_pass": inp.rule_pass,
    }
    if inp.dict_match is not None:
        _check_range("dict_match", inp.dict_match)
        components["dict_match"] = inp.dict_match

    # dict_match 미적용 시 남은 가중치를 합 1.0 으로 재정규화 (Step 4 로직 재사용)
    weights = config.weights.normalized_for(components.keys())
    score = sum(weights[name] * components[name] for name in components)

    critical = inp.field_key in config.critical_fields
    threshold = config.threshold_for(inp.field_key)

    if inp.forced_hitl:
        status = FieldStatus.needs_review  # 점수 무관 HITL 우선
    else:
        status = FieldStatus.confirmed if score >= threshold else FieldStatus.needs_review

    flags: dict[str, Any] = {
        "critical": critical,
        "threshold": threshold,
        "forced_hitl": inp.forced_hitl,
        "needs_review": status is FieldStatus.needs_review,
        **inp.extra_flags,
    }
    return FieldScore(
        field_key=inp.field_key,
        score=round(score, 6),
        status=status,
        threshold=threshold,
        components=components,
        weights={k: round(v, 6) for k, v in weights.items()},
        flags=flags,
    )


# --------------------------------------------------------------------------- #
# 저장 — order_fields 4종(raw / corrected / score+components / flags·status) 일괄
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ScoredFieldRecord:
    """저장 입력 = raw·corrected 원천 + 스코어링 결과."""

    field_type: FieldType
    score: FieldScore
    raw_text: str | None = None
    raw_bbox: dict[str, Any] | None = None
    corrected_value: str | None = None
    corrected_by: CorrectedBy | None = None


def persist_scored_fields(
    session: Session,
    order: Order,
    records: list[ScoredFieldRecord],
) -> OrderStatus:
    """필드 결과 일괄 저장 + 의뢰서 단위 상태 전이.

    score_components 에 ocr_conf/rule_pass/dict_match 개별값을 보존한다 —
    파일럿 임계값 튜닝의 근거 데이터.
    """
    for rec in records:
        s = rec.score
        session.add(
            OrderField(
                order_id=order.id,
                field_key=s.field_key,
                field_type=rec.field_type,
                # 1) raw
                raw_text=rec.raw_text,
                raw_bbox=rec.raw_bbox,
                raw_ocr_conf=s.components.get("ocr_conf"),
                # 2) corrected
                corrected_value=rec.corrected_value,
                corrected_by=rec.corrected_by,
                # 3) score + components(튜닝 근거)
                score=s.score,
                score_components=dict(s.components),
                # 4) flags + status
                flags=dict(s.flags),
                status=s.status,
            )
        )
    session.flush()
    session.refresh(order, attribute_names=["fields"])

    new_status = recompute_order_status(order)  # 전 필드 confirmed → auto_confirmed
    session.commit()
    return new_status
