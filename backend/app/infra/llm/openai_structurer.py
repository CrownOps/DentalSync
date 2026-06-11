"""OpenAI 구현체 — Structured Outputs(json_schema + strict)로 스키마 준수를 API 레벨 강제.

입력은 CLOVA 가 추출한 **텍스트만** 전달한다. 메시지 content 는 항상 문자열이며
이미지 파트(image_url 등)는 어떤 경로로도 만들 수 없다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.config import Settings
from app.infra.llm.base import LLMCallError, LLMRefusalError, RawStructuredOutput

SYSTEM_PROMPT = """\
당신은 치과기공소 의뢰서의 자유텍스트를 구조화하는 전문가입니다.

도메인 컨텍스트:
- 입력은 치과 의뢰서에서 CLOVA OCR 로 추출된 한국어 텍스트입니다 (이미지가 아님).
- 보철 종류(크라운/브릿지/임플란트/틀니), 재료(지르코니아/PFM/골드), VITA 쉐이드,
  FDI 치식(11~48), 임플란트 시스템/어버트먼트 용어가 자주 등장합니다.
- OCR 오인식(예: 질코니아→지르코니아)을 감안해 의미를 해석하되,
  원문에 없는 정보를 지어내지 마십시오.

출력 규칙:
- 주어진 JSON Schema 를 정확히 따르는 JSON 만 출력합니다.
- confidence 필드에 추출 확신도를 0~1 로 자기보고합니다.
  불확실하거나 원문이 모호하면 낮은 값을 보고하십시오.
"""


class OpenAIStructurer:
    """LLMStructurer Protocol 구현 — chat.completions + response_format json_schema."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport  # 테스트용 MockTransport 주입 지점

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAIStructurer:
        return cls(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

    async def structure(
        self,
        *,
        text: str,
        schema: Mapping[str, Any],
        model: str,
    ) -> RawStructuredOutput:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                # content 는 문자열만 — 이미지 파트(image_url)는 구조적으로 불가
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "type_c_extraction",
                    "strict": True,
                    "schema": dict(schema),
                },
            },
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
        except httpx.HTTPError as exc:
            raise LLMCallError(f"OpenAI 통신 오류: {exc}") from exc

        if resp.status_code != 200:
            raise LLMCallError(f"OpenAI 비정상 응답: HTTP {resp.status_code}")

        try:
            body = resp.json()
            message = body["choices"][0]["message"]
        except (json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMCallError(f"OpenAI 응답 형식 오류: {exc}") from exc

        if message.get("refusal"):
            raise LLMRefusalError(f"모델 거부: {message['refusal']}")

        content = message.get("content")
        if not content:
            raise LLMCallError("OpenAI 응답 content 가 비어 있음")

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMCallError(f"구조화 JSON 파싱 실패: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMCallError("구조화 출력이 JSON 객체가 아님")

        return RawStructuredOutput(data=data, model=str(body.get("model", model)))
