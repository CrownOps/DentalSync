"""주문 업로드 API 스키마."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.services.order_intake import IntakeResult


class OrderIntakeResponse(BaseModel):
    order_id: int
    image_hash: str
    status: str
    cache_hit: bool
    ocr_cached: bool

    @classmethod
    def from_result(cls, result: IntakeResult) -> OrderIntakeResponse:
        return cls(
            order_id=result.order_id,
            image_hash=result.image_hash,
            status=result.status.value,
            cache_hit=result.cache_hit,
            ocr_cached=result.ocr_cached,
        )


class ImageRejectResponse(BaseModel):
    """422 반려 응답 — 재촬영 안내 포함."""

    error_code: str
    message: str
    guidance: str


class OCRRunResponse(BaseModel):
    """OCR 실행/재시도 결과."""

    order_id: int
    status: str
    field_count: int


# ── HITL 검토 큐 ──────────────────────────────────────────────────────────────


class ReviewQueueItem(BaseModel):
    order_id: int
    lab_id: int
    status: str
    received_at: str | None
    due_date: str | None
    min_score: float | None
    field_count: int


class OrderFieldDetail(BaseModel):
    id: int
    field_key: str
    field_type: str
    raw_text: str | None
    raw_bbox: dict[str, Any] | None
    raw_ocr_conf: float | None
    corrected_value: str | None
    corrected_by: str | None
    score: float | None
    score_components: dict[str, Any] | None
    flags: dict[str, Any] | None
    status: str


class OrderDetailResponse(BaseModel):
    order_id: int
    lab_id: int
    status: str
    image_url: str
    received_at: str | None
    due_date: str | None
    fields: list[OrderFieldDetail]


# ── HITL 확정 ─────────────────────────────────────────────────────────────────


class FieldUpdate(BaseModel):
    field_key: str
    corrected_value: str


class ConfirmOrderRequest(BaseModel):
    fields: list[FieldUpdate]
    actor: str = "human"


class ConfirmOrderResponse(BaseModel):
    order_id: int
    status: str
    updated_fields: int
    training_labels_inserted: int
