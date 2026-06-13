"""CLOVA General OCR 엔진 — 템플릿 없이 임의 양식 의뢰서의 전체 텍스트를 추출.

Template OCR(clova.py)과 달리 templateIds 를 보내지 않고, 응답의 텍스트 조각을
lineBreak 기준으로 이어붙여 **단일 ocr_raw_text 필드**(전체 텍스트)로 반환한다.
의미 구조화는 후속 LLM 문서 구조화 단계(document_structuring.py)가 담당한다.

- 의뢰서당 CLOVA 호출 1회(성공 시). 일시 실패는 지수 백오프 3회 재시도.
- 재시도/포맷 감지/에러 본문 파싱은 clova.py 공용 함수를 재사용한다.
"""

from __future__ import annotations

import json
import time
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
from app.infra.ocr.base import OCREngine, OCRField, OCRParseError, OCRTransientError
from app.infra.ocr.clova import _error_detail, detect_clova_format

# 전체 텍스트를 담는 단일 필드 키 — 라우팅/구조화/note 백필의 입력.
RAW_TEXT_KEY = "ocr_raw_text"


def assemble_full_text(payload: dict[str, Any]) -> tuple[str, float]:
    """CLOVA General 응답 → (전체 텍스트, infer 신뢰도 평균).

    fields[].lineBreak 가 True 면 줄바꿈, 아니면 공백으로 inferText 를 잇는다.
    """
    try:
        image = payload["images"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise OCRParseError(f"CLOVA 응답에 images 없음: {exc}") from exc

    infer_result = image.get("inferResult")
    if infer_result not in (None, "SUCCESS"):
        raise OCRParseError(f"CLOVA inferResult={infer_result}")

    parts: list[str] = []
    confidences: list[float] = []
    try:
        for fld in image.get("fields", []):
            text = fld.get("inferText", "")
            parts.append(text)
            parts.append("\n" if fld.get("lineBreak") else " ")
            if "inferConfidence" in fld:
                confidences.append(float(fld["inferConfidence"]))
    except (TypeError, ValueError) as exc:
        raise OCRParseError(f"CLOVA General 필드 파싱 실패: {exc}") from exc

    full_text = "".join(parts).strip()
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return full_text, avg_conf


class CLOVAGeneralOCREngine(OCREngine):
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
    def from_settings(cls, settings: Settings) -> CLOVAGeneralOCREngine:
        return cls(
            invoke_url=settings.clova_general_invoke_url,
            secret=settings.clova_ocr_secret,
        )

    async def extract(self, image_bytes: bytes, template_id: str) -> list[OCRField]:
        # template_id 는 General 모드에서 무시(인터페이스 호환용 인자).
        if not self._invoke_url.strip():
            raise OCRParseError(
                "CLOVA General Invoke URL 미설정 — CLOVA_GENERAL_INVOKE_URL 을 설정하세요"
            )
        payload = await self._call_with_retry(image_bytes)
        full_text, avg_conf = assemble_full_text(payload)
        return [OCRField(field_key=RAW_TEXT_KEY, text=full_text, confidence=avg_conf, bbox=None)]

    async def _call_with_retry(self, image_bytes: bytes) -> dict[str, Any]:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=self._wait,
            retry=retry_if_exception_type(OCRTransientError),
            reraise=True,
        ):
            with attempt:
                return await self._single_call(image_bytes)
        raise OCRTransientError("재시도 소진")  # pragma: no cover - 도달 불가(reraise)

    async def _single_call(self, image_bytes: bytes) -> dict[str, Any]:
        image_format = detect_clova_format(image_bytes)
        # General OCR: templateIds 없이 images 만. timestamp 는 호출 시각(ms).
        message = {
            "version": "V2",
            "requestId": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "images": [{"format": image_format, "name": "requisition"}],
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
            raise OCRTransientError(
                f"CLOVA 일시 오류: HTTP {resp.status_code} — {_error_detail(resp)}"
            )
        if resp.status_code != 200:
            raise OCRParseError(
                f"CLOVA 비정상 응답: HTTP {resp.status_code} — {_error_detail(resp)}"
            )

        try:
            body: dict[str, Any] = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise OCRParseError(f"CLOVA 응답 JSON 파싱 실패: {exc}") from exc
        return body
