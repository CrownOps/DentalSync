"""OCR 엔진 추상 인터페이스 + 결과 모델 + 예외.

서비스 레이어는 이 모듈(인터페이스)에만 의존한다. 구체 엔진(CLOVA/Mock/자체모델)은
이 Protocol 을 구현하면 DI 로 교체 가능하다(Phase 3 자체모델 전환 대비).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class OCRField(BaseModel):
    """정규화된 단일 OCR 필드."""

    field_key: str
    text: str
    bbox: dict[str, Any] | None = None  # CLOVA boundingPoly (JSONB 저장 호환)
    confidence: float  # CLOVA inferConfidence 매핑


@runtime_checkable
class OCREngine(Protocol):
    """OCR 엔진 인터페이스 — 의뢰서당 extract 1회 호출."""

    async def extract(self, image_bytes: bytes, template_id: str) -> list[OCRField]: ...


class OCRExtractionError(Exception):
    """OCR 추출 실패(최종). 서비스 레이어가 orders.status=ocr_failed 로 매핑."""


class OCRTransientError(OCRExtractionError):
    """일시적 실패(타임아웃/5xx/429) — 재시도 대상."""


class OCRParseError(OCRExtractionError):
    """응답 파싱 실패 — 재시도하지 않고 즉시 실패."""
