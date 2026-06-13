"""HITL 검토 API 스키마 — /api/v1/review/."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# ── 공통 에러 ──────────────────────────────────────────────────────────────────


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[str] = []


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ── 검토 큐 ───────────────────────────────────────────────────────────────────


class ReviewQueueItem(BaseModel):
    order_id: int
    lab_id: int
    status: str
    received_at: str | None
    needs_review_count: int
    min_score: float | None
    has_forced_hitl: bool


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItem]
    total: int
    limit: int
    offset: int


# ── 검토 상세 ─────────────────────────────────────────────────────────────────


class FieldEnvelope(BaseModel):
    """레이아웃 정의 v1.1.0 value envelope."""

    field_key: str
    field_type: str
    value: str | None
    raw: str | None
    bbox: dict[str, Any] | None
    confidence: float | None
    score_components: dict[str, Any] | None
    status: str
    flags: dict[str, Any] | None
    corrected_by: str | None
    corrected_at: str | None
    pii: bool


class ReviewDetailResponse(BaseModel):
    order_id: int
    lab_id: int
    status: str
    image_url: str
    received_at: str | None
    due_date: str | None
    fields: list[FieldEnvelope]


# ── 필드 인라인 수정 ──────────────────────────────────────────────────────────


class FieldUpdateRequest(BaseModel):
    value: str


class FieldUpdateResponse(BaseModel):
    order_id: int
    field_key: str
    corrected_value: str
    field_status: str


# ── 확정 ─────────────────────────────────────────────────────────────────────


class ConfirmResponse(BaseModel):
    order_id: int
    status: str
    training_labels_inserted: int


# ── 상태 폴링 ─────────────────────────────────────────────────────────────────


class OrderStatusResponse(BaseModel):
    order_id: int
    status: str
    updated_at: str | None
    # status=ocr_failed 일 때 실패 사유 — 프론트 재시도 UI 가 원인을 표시한다.
    error_detail: str | None = None


# ── 정확도 집계 ───────────────────────────────────────────────────────────────


class FieldAccuracyItem(BaseModel):
    field_key: str
    total: int
    auto_correct: int
    accuracy: float


class AccuracyResponse(BaseModel):
    items: list[FieldAccuracyItem]
