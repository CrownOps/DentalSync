"""General OCR 경로 — CLOVA General 엔진 / Mock General / Mock 구조화기 테스트."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity.wait import wait_none

from app.infra.llm.mock_structurer import MockLLMStructurer
from app.infra.ocr.clova_general import (
    RAW_TEXT_KEY,
    CLOVAGeneralOCREngine,
    assemble_full_text,
)
from app.infra.ocr.mock_general import MockGeneralOCREngine

_GENERAL_RESPONSE: dict[str, Any] = {
    "version": "V2",
    "images": [
        {
            "inferResult": "SUCCESS",
            "fields": [
                {"inferText": "청구치과", "inferConfidence": 0.90, "lineBreak": True},
                {"inferText": "#36,", "inferConfidence": 0.80, "lineBreak": False},
                {"inferText": "37", "inferConfidence": 0.86, "lineBreak": True},
            ],
        }
    ],
}


# --- 전체 텍스트 조립 -------------------------------------------------------
def test_assemble_full_text_joins_with_linebreak() -> None:
    text, avg = assemble_full_text(_GENERAL_RESPONSE)
    assert text == "청구치과\n#36, 37"
    assert 0.8 <= avg <= 0.9


# --- CLOVA General 엔진 -----------------------------------------------------
def _engine(handler: Any) -> CLOVAGeneralOCREngine:
    return CLOVAGeneralOCREngine(
        invoke_url="http://clova.test/general",
        secret="secret",
        max_attempts=3,
        wait=wait_none(),
        transport=httpx.MockTransport(handler),
    )


async def test_general_engine_returns_single_raw_text_field() -> None:
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = req.content.decode("latin-1")
        return httpx.Response(200, json=_GENERAL_RESPONSE)

    fields = await _engine(handler).extract(b"\x89PNG\r\n\x1a\nimg", "ignored")
    assert len(fields) == 1
    assert fields[0].field_key == RAW_TEXT_KEY
    assert fields[0].text == "청구치과\n#36, 37"
    # General OCR 은 templateIds 를 보내지 않는다
    assert "templateIds" not in seen["body"]
    assert '"format": "png"' in seen["body"]


# --- Mock General 엔진 ------------------------------------------------------
async def test_mock_general_engine_returns_freeform_text() -> None:
    fields = await MockGeneralOCREngine().extract(b"img", "t")
    assert len(fields) == 1
    assert fields[0].field_key == RAW_TEXT_KEY
    assert "지르코니아" in fields[0].text


async def test_mock_general_engine_custom_text() -> None:
    fields = await MockGeneralOCREngine("환자 김철수 / 25 지르 A2").extract(b"x", "t")
    assert fields[0].text == "환자 김철수 / 25 지르 A2"


# --- Mock LLM 구조화기 (입력 반영) -----------------------------------------
async def test_mock_structurer_parses_input_text() -> None:
    text = (
        "청구치과의원\n원장 김민수\n환자: 홍길동\n"
        "#36, 37 지르코니아 크라운\nshade A3\n납기 2026-06-20"
    )
    out = await MockLLMStructurer().structure(text=text, schema={}, model="mock")
    d = out.data
    assert d["clinic_name"] == "청구치과의원"
    assert d["doctor_name"] == "김민수"
    assert d["patient_name"] == "홍길동"
    assert d["prosthesis_category"] == "crown"
    assert d["material"] == ["zirconia"]
    assert d["shade"] == "A3"
    assert d["tooth_numbers"] == ["36", "37"]
    assert d["due_date"] == "2026-06-20"
    assert 0.0 <= d["confidence"] <= 1.0
