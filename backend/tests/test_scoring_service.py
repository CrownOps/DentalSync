"""복합 신뢰도 스코어링 + 분기 테스트.

가중치 0.5/0.3/0.2 에서 세 컴포넌트가 같은 값 x 면 score == x — 경계값을
정확히 만들 수 있다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.scoring import load_scoring_config
from app.db.base import Base
from app.db.models import Lab, Order, OrderField
from app.domain.enums import CorrectedBy, FieldStatus, FieldType, OrderStatus
from app.domain.scoring import ScoringConfig
from app.services.scoring import (
    FieldScoreInput,
    ScoredFieldRecord,
    persist_scored_fields,
    score_field,
)


@pytest.fixture(scope="module")
def config() -> ScoringConfig:
    return load_scoring_config()  # config/scoring.yaml — 하드코딩 없음


def _inp(field_key: str, value: float, **kwargs: object) -> FieldScoreInput:
    return FieldScoreInput(
        field_key=field_key,
        ocr_conf=value,
        rule_pass=value,
        dict_match=value,
        **kwargs,  # type: ignore[arg-type]
    )


# --- 경계값 (일반 0.90 / 치명 0.95) ------------------------------------------
@pytest.mark.parametrize(
    ("field_key", "value", "expected"),
    [
        ("request_note", 0.89, FieldStatus.needs_review),  # 0.89 < 0.90
        ("request_note", 0.90, FieldStatus.confirmed),  # 경계 포함
        ("shade", 0.94, FieldStatus.needs_review),  # 치명: 0.94 < 0.95
        ("shade", 0.95, FieldStatus.confirmed),  # 치명 경계 포함
        ("tooth_numbers", 0.94, FieldStatus.needs_review),
        ("due_date", 0.95, FieldStatus.confirmed),
    ],
)
def test_threshold_boundaries(
    config: ScoringConfig, field_key: str, value: float, expected: FieldStatus
) -> None:
    result = score_field(_inp(field_key, value), config)
    assert result.score == pytest.approx(value)
    assert result.status is expected


# --- 가중 합성 산식 -----------------------------------------------------------
def test_weighted_sum(config: ScoringConfig) -> None:
    result = score_field(
        FieldScoreInput(field_key="request_note", ocr_conf=1.0, rule_pass=0.5, dict_match=0.0),
        config,
    )
    # 0.5*1.0 + 0.3*0.5 + 0.2*0.0 = 0.65
    assert result.score == pytest.approx(0.65)
    assert result.weights == pytest.approx({"ocr_conf": 0.5, "rule_pass": 0.3, "dict_match": 0.2})


def test_renormalization_when_dict_not_applicable(config: ScoringConfig) -> None:
    """dict_match 미적용 → 0.5/0.3 이 0.625/0.375 로 재정규화 (Step 4 재사용)."""
    result = score_field(
        FieldScoreInput(field_key="patient_name", ocr_conf=0.8, rule_pass=1.0, dict_match=None),
        config,
    )
    assert result.weights == pytest.approx({"ocr_conf": 0.625, "rule_pass": 0.375})
    assert result.score == pytest.approx(0.8 * 0.625 + 1.0 * 0.375)  # 0.875
    assert "dict_match" not in result.components  # 보존 데이터에도 미포함


# --- 치명 필드 분기 ------------------------------------------------------------
def test_critical_field_uses_higher_threshold(config: ScoringConfig) -> None:
    """동일 점수(0.92)라도 일반은 confirmed, 치명(쉐이드)은 needs_review."""
    general = score_field(_inp("request_note", 0.92), config)
    critical = score_field(_inp("shade", 0.92), config)
    assert general.status is FieldStatus.confirmed
    assert critical.status is FieldStatus.needs_review
    assert general.flags["critical"] is False
    assert critical.flags["critical"] is True
    assert critical.threshold == 0.95


# --- forced_hitl 우선 ----------------------------------------------------------
def test_forced_hitl_overrides_perfect_score(config: ScoringConfig) -> None:
    result = score_field(_inp("request_note", 1.0, forced_hitl=True), config)
    assert result.score == pytest.approx(1.0)
    assert result.status is FieldStatus.needs_review  # 점수 무관
    assert result.flags["forced_hitl"] is True


def test_extra_flags_passthrough(config: ScoringConfig) -> None:
    result = score_field(
        _inp("request_note", 1.0, forced_hitl=True, extra_flags={"model_escalated": True}),
        config,
    )
    assert result.flags["model_escalated"] is True


# --- 설정 파일 변경만으로 조정 가능 증명 ---------------------------------------
def test_threshold_tunable_via_yaml_only(tmp_path: Path) -> None:
    """코드 변경 없이 scoring.yaml 만 바꿔 분기가 달라짐을 증명."""
    custom = tmp_path / "scoring.yaml"
    custom.write_text(
        yaml.safe_dump(
            {
                "weights": {"ocr_conf": 0.5, "rule_pass": 0.3, "dict_match": 0.2},
                "thresholds": {"general": 0.80, "critical": 0.95},  # general 완화
                "critical_fields": ["shade", "tooth_numbers", "due_date"],
            }
        ),
        encoding="utf-8",
    )
    relaxed = load_scoring_config(custom)
    default = load_scoring_config()

    inp = _inp("request_note", 0.85)
    assert score_field(inp, default).status is FieldStatus.needs_review  # 0.85 < 0.90
    assert score_field(inp, relaxed).status is FieldStatus.confirmed  # 0.85 >= 0.80


def test_weights_tunable_via_yaml_only(tmp_path: Path) -> None:
    custom = tmp_path / "scoring.yaml"
    custom.write_text(
        yaml.safe_dump(
            {
                "weights": {"ocr_conf": 0.2, "rule_pass": 0.2, "dict_match": 0.6},
                "thresholds": {"general": 0.90, "critical": 0.95},
                "critical_fields": ["shade"],
            }
        ),
        encoding="utf-8",
    )
    cfg = load_scoring_config(custom)
    result = score_field(
        FieldScoreInput(field_key="material", ocr_conf=1.0, rule_pass=1.0, dict_match=0.0),
        cfg,
    )
    assert result.score == pytest.approx(0.4)  # 0.2+0.2+0 — 가중치도 yaml 로만 조정


# --- 순수 함수 / 입력 검증 -----------------------------------------------------
def test_pure_function_deterministic(config: ScoringConfig) -> None:
    inp = _inp("shade", 0.93)
    assert score_field(inp, config) == score_field(inp, config)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_out_of_range_component_raises(config: ScoringConfig, bad: float) -> None:
    with pytest.raises(ValueError, match="0~1"):
        score_field(FieldScoreInput(field_key="x", ocr_conf=bad, rule_pass=0.5), config)


# --- 저장: order_fields 4종 일괄 + 의뢰서 상태 전이 ----------------------------
@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _order(session: Session) -> Order:
    lab = Lab(name="lab")
    session.add(lab)
    session.flush()
    order = Order(lab_id=lab.id, image_url="orders/x.jpg", image_hash="h")
    session.add(order)
    session.flush()
    return order


def _record(
    config: ScoringConfig, field_key: str, value: float, **kwargs: object
) -> ScoredFieldRecord:
    return ScoredFieldRecord(
        field_type=FieldType.B,
        score=score_field(_inp(field_key, value, **kwargs), config),
        raw_text=f"raw-{field_key}",
        raw_bbox={"vertices": [{"x": 1, "y": 2}]},
        corrected_value=f"corr-{field_key}",
        corrected_by=CorrectedBy.system,
    )


def test_persist_four_kinds_and_components(session: Session, config: ScoringConfig) -> None:
    order = _order(session)
    status = persist_scored_fields(
        session, order, [_record(config, "due_date", 0.96), _record(config, "shade", 0.92)]
    )

    assert status is OrderStatus.needs_review  # shade 0.92 < 0.95
    rows = list(session.scalars(select(OrderField).order_by(OrderField.field_key)))
    assert [r.field_key for r in rows] == ["due_date", "shade"]

    shade = rows[1]
    # 4종: raw / corrected / score+components / flags·status
    assert shade.raw_text == "raw-shade"
    assert shade.raw_bbox == {"vertices": [{"x": 1, "y": 2}]}
    assert shade.raw_ocr_conf == pytest.approx(0.92)
    assert shade.corrected_value == "corr-shade"
    assert shade.corrected_by is CorrectedBy.system
    assert shade.score == pytest.approx(0.92)
    assert shade.score_components == pytest.approx(
        {"ocr_conf": 0.92, "rule_pass": 0.92, "dict_match": 0.92}  # 튜닝 근거 보존
    )
    assert shade.flags is not None
    assert shade.flags["critical"] is True
    assert shade.status is FieldStatus.needs_review


def test_persist_all_confirmed_auto_confirms_order(
    session: Session, config: ScoringConfig
) -> None:
    order = _order(session)
    status = persist_scored_fields(
        session,
        order,
        [_record(config, "due_date", 0.97), _record(config, "patient_name", 0.95)],
    )
    assert status is OrderStatus.auto_confirmed
    assert order.status is OrderStatus.auto_confirmed


def test_persist_forced_hitl_blocks_auto_confirm(
    session: Session, config: ScoringConfig
) -> None:
    order = _order(session)
    status = persist_scored_fields(
        session,
        order,
        [_record(config, "due_date", 0.97), _record(config, "request_note", 1.0, forced_hitl=True)],
    )
    assert status is OrderStatus.needs_review  # forced_hitl 이 검토 큐로 보냄
