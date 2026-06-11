"""OpenAIStructurer 테스트 — 실제 API 호출 없음(httpx.MockTransport).

요청 형식(Structured Outputs strict / 텍스트 전용)과 응답 처리(정상/refusal/오류)를 검증.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.infra.llm.base import LLMCallError, LLMRefusalError
from app.infra.llm.openai_structurer import SYSTEM_PROMPT, OpenAIStructurer
from app.services.type_c_structuring import TYPE_C_SCHEMA


def _ok_body(content: dict[str, Any], model: str = "gpt-test") -> dict[str, Any]:
    return {
        "model": model,
        "choices": [{"message": {"content": json.dumps(content), "refusal": None}}],
    }


def _engine(handler: Any) -> OpenAIStructurer:
    return OpenAIStructurer(
        api_key="test-key",
        base_url="http://openai.test/v1",
        transport=httpx.MockTransport(handler),
    )


async def test_request_shape_strict_and_text_only() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured.update(json.loads(req.content))
        captured["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json=_ok_body({"value": "교합 낮게", "confidence": 0.9}))

    await _engine(handler).structure(text="교합 낮게 부탁", schema=TYPE_C_SCHEMA, model="m-1")

    assert captured["model"] == "m-1"
    # Structured Outputs: json_schema + strict 강제
    rf = captured["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"]["required"] == ["value", "confidence"]
    # 텍스트 전용 — 모든 메시지 content 가 문자열(이미지 파트 불가)
    assert all(isinstance(m["content"], str) for m in captured["messages"])
    assert captured["messages"][0]["content"] == SYSTEM_PROMPT
    assert "치과기공소" in captured["messages"][0]["content"]  # 도메인 컨텍스트
    assert captured["auth"] == "Bearer test-key"


async def test_success_returns_parsed_data() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body({"value": "지르코니아", "confidence": 0.85}))

    out = await _engine(handler).structure(text="질코니아", schema=TYPE_C_SCHEMA, model="m")
    assert out.data == {"value": "지르코니아", "confidence": 0.85}
    assert out.model == "gpt-test"


async def test_refusal_raises() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "m", "choices": [{"message": {"content": None, "refusal": "거부"}}]},
        )

    with pytest.raises(LLMRefusalError):
        await _engine(handler).structure(text="t", schema=TYPE_C_SCHEMA, model="m")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"error": "boom"}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(
            200, json={"choices": [{"message": {"content": "not-json", "refusal": None}}]}
        ),
        httpx.Response(
            200, json={"choices": [{"message": {"content": "[1,2]", "refusal": None}}]}
        ),
        httpx.Response(
            200, json={"choices": [{"message": {"content": "", "refusal": None}}]}
        ),
    ],
)
async def test_error_responses_raise(response: httpx.Response) -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(LLMCallError):
        await _engine(handler).structure(text="t", schema=TYPE_C_SCHEMA, model="m")
