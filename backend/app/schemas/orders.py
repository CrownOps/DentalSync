"""주문 업로드 API 스키마."""

from __future__ import annotations

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


class OrderFieldOut(BaseModel):
    """필드별 결과(4종 저장 그대로 노출)."""

    field_key: str
    field_type: str
    raw_text: str | None
    corrected_value: str | None
    corrected_by: str | None
    score: float | None
    score_components: dict[str, float] | None
    status: str
    flags: dict[str, object] | None


class OrderDetailResponse(BaseModel):
    """GET /api/orders/{id} — 상태 + 필드별 결과."""

    order_id: int
    lab_id: int
    status: str
    image_hash: str
    fields: list[OrderFieldOut]


class OrderSummaryOut(BaseModel):
    """검토 큐 목록 항목."""

    order_id: int
    lab_id: int
    status: str
    min_score: float | None  # 가장 낮은 필드 점수(검토 우선순위 근거)
