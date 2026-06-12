"""CLOVA OCR Template(Basic) 엔진 구현.

- 의뢰서당 CLOVA 호출 1회(성공 시). 일시적 실패는 지수 백오프 3회 재시도(tenacity).
- 최종 실패/파싱 실패는 OCRExtractionError 로 올려, 서비스가 ocr_failed 처리.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

from app.core.config import Settings
from app.infra.ocr.base import (
    OCREngine,
    OCRField,
    OCRParseError,
    OCRTransientError,
)


# CLOVA images[].format 은 실제 파일 포맷과 일치해야 함(불일치 시 HTTP 400).
# 클라이언트 content-type 을 믿지 않고 매직 바이트로 판별한다.
_FORMAT_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"%PDF", "pdf"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
)


def detect_clova_format(image_bytes: bytes) -> str:
    """매직 바이트 → CLOVA format 문자열. 미상이면 jpg 로 폴백."""
    for magic, fmt in _FORMAT_MAGIC:
        if image_bytes.startswith(magic):
            return fmt
    return "jpg"


def parse_clova_response(payload: dict[str, Any]) -> list[OCRField]:
    """CLOVA Template 응답 → OCRField 목록. 스키마 위반 시 OCRParseError."""
    try:
        images = payload["images"]
        image = images[0]
    except (KeyError, IndexError, TypeError) as exc:
        raise OCRParseError(f"CLOVA 응답에 images 없음: {exc}") from exc

    infer_result = image.get("inferResult")
    if infer_result not in (None, "SUCCESS"):
        raise OCRParseError(f"CLOVA inferResult={infer_result}")

    fields: list[OCRField] = []
    try:
        for raw in image.get("fields", []):
            name = raw["name"]
            fields.append(
                OCRField(
                    field_key=name,
                    text=raw.get("inferText", ""),
                    confidence=float(raw.get("inferConfidence", 0.0)),
                    bbox=raw.get("boundingPoly"),
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise OCRParseError(f"CLOVA 필드 파싱 실패: {exc}") from exc
    return fields


class CLOVAOCREngine(OCREngine):
    def __init__(
        self,
        *,
        invoke_url: str,
        secret: str,
        timeout: float = 15.0,
        max_attempts: int = 3,
        wait: wait_base | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._invoke_url = invoke_url
        self._secret = secret
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._wait: wait_base = wait or wait_exponential(multiplier=0.5, max=8)
        self._transport = transport

    @classmethod
    def from_settings(cls, settings: Settings) -> CLOVAOCREngine:
        return cls(
            invoke_url=settings.clova_ocr_invoke_url,
            secret=settings.clova_ocr_secret,
        )

    async def extract(self, image_bytes: bytes, template_id: str) -> list[OCRField]:
        payload = await self._call_with_retry(image_bytes, template_id)
        return parse_clova_response(payload)

    async def _call_with_retry(self, image_bytes: bytes, template_id: str) -> dict[str, Any]:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=self._wait,
            retry=retry_if_exception_type(OCRTransientError),
            reraise=True,
        ):
            with attempt:
                return await self._single_call(image_bytes, template_id)
        raise OCRTransientError("재시도 소진")  # pragma: no cover - 도달 불가(reraise)

    async def _single_call(self, image_bytes: bytes, template_id: str) -> dict[str, Any]:
        image_format = detect_clova_format(image_bytes)
        message = {
            "version": "V2",
            "requestId": str(uuid.uuid4()),
            "timestamp": 0,
            "images": [{"format": image_format, "name": "requisition"}],
            "templateIds": [template_id],
        }
        headers = {"X-OCR-SECRET": self._secret}
        files = {
            "file": (f"requisition.{image_format}", image_bytes, "application/octet-stream")
        }
        data = {"message": json.dumps(message)}

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                resp = await client.post(
                    self._invoke_url, headers=headers, data=data, files=files
                )
        except httpx.HTTPError as exc:
            raise OCRTransientError(f"CLOVA 통신 오류: {exc}") from exc

        if resp.status_code >= 500 or resp.status_code == 429:
            raise OCRTransientError(f"CLOVA 일시 오류: HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise OCRParseError(f"CLOVA 비정상 응답: HTTP {resp.status_code}")

        try:
            body: dict[str, Any] = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise OCRParseError(f"CLOVA 응답 JSON 파싱 실패: {exc}") from exc
        return body
