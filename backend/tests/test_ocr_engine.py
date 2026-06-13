"""OCR 엔진 단위 테스트 — Mock / CLOVA 파싱 / 재시도."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from tenacity.wait import wait_none

from app.infra.ocr.base import OCRExtractionError, OCRParseError
from app.infra.ocr.clova import CLOVAOCREngine, detect_clova_format, parse_clova_response
from app.infra.ocr.mock import MockOCREngine

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_PDF_MAGIC = b"%PDF-1.4"

SAMPLE_CLOVA: dict[str, Any] = {
    "version": "V2",
    "requestId": "req-1",
    "images": [
        {
            "name": "requisition",
            "inferResult": "SUCCESS",
            "fields": [
                {
                    "name": "shade",
                    "inferText": "A2",
                    "inferConfidence": 0.987,
                    "boundingPoly": {"vertices": [{"x": 1, "y": 2}]},
                },
                {
                    "name": "tooth_numbers",
                    "inferText": "11, 12",
                    "inferConfidence": 0.91,
                    "boundingPoly": {"vertices": [{"x": 3, "y": 4}]},
                },
            ],
        }
    ],
}


# --- Mock 엔진 --------------------------------------------------------------
async def test_mock_engine_returns_layout_fields() -> None:
    fields = await MockOCREngine().extract(b"image", "tmpl")
    keys = {f.field_key for f in fields}
    assert {"shade", "tooth_numbers", "patient_name"} <= keys
    assert "chart_no" not in keys  # PII 제외(환자명만 허용)
    assert all(0.0 <= f.confidence <= 1.0 for f in fields)


async def test_mock_engine_custom_fields() -> None:
    from app.infra.ocr.base import OCRField

    custom = [OCRField(field_key="shade", text="B1", confidence=0.5)]
    fields = await MockOCREngine(custom).extract(b"x", "t")
    assert len(fields) == 1
    assert fields[0].text == "B1"


async def test_mock_engine_note_only_omits_dedicated_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MOCK_OCR_NOTE_ONLY: 쉐이드/치식/재료 칸을 제외해 note 백필 경로를 재현한다."""
    monkeypatch.setenv("MOCK_OCR_NOTE_ONLY", "1")
    keys = {f.field_key for f in await MockOCREngine().extract(b"image", "tmpl")}
    assert keys.isdisjoint({"shade", "tooth_numbers", "material"})
    assert "ocr_raw_text" in keys  # note 원문은 유지 → 라우팅이 여기서 역추출


# --- CLOVA 응답 파싱 --------------------------------------------------------
def test_parse_clova_response_maps_fields() -> None:
    fields = parse_clova_response(SAMPLE_CLOVA)
    assert len(fields) == 2
    shade = fields[0]
    assert shade.field_key == "shade"
    assert shade.text == "A2"
    assert shade.confidence == pytest.approx(0.987)  # inferConfidence 매핑
    assert shade.bbox == {"vertices": [{"x": 1, "y": 2}]}


@pytest.mark.parametrize(
    "payload",
    [
        {},  # images 없음
        {"images": []},  # 빈 images
        {"images": [{"inferResult": "FAILURE", "fields": []}]},  # 실패 결과
        {"images": [{"inferResult": "SUCCESS", "fields": [{"inferText": "x"}]}]},  # name 누락
    ],
)
def test_parse_clova_response_failures(payload: dict[str, Any]) -> None:
    with pytest.raises(OCRParseError):
        parse_clova_response(payload)


# --- CLOVA 재시도 / 호출 횟수 ----------------------------------------------
def _engine(handler: Any) -> CLOVAOCREngine:
    return CLOVAOCREngine(
        invoke_url="http://clova.test/ocr",
        secret="secret",
        max_attempts=3,
        wait=wait_none(),
        transport=httpx.MockTransport(handler),
    )


async def test_clova_retries_3_times_then_fails() -> None:
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"error": "boom"})

    # 5xx 는 일시적 오류 → 3회 재시도 후 OCRExtractionError 재전파
    with pytest.raises(OCRExtractionError):
        await _engine(handler).extract(b"img", "42209")
    assert calls["n"] == 3


async def test_clova_success_calls_once() -> None:
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=SAMPLE_CLOVA)

    fields = await _engine(handler).extract(b"img", "42209")
    assert calls["n"] == 1  # 의뢰서당 정확히 1회
    assert {f.field_key for f in fields} == {"shade", "tooth_numbers"}


# --- CLOVA format 판별(매직 바이트) ---------------------------------------
@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (_JPEG_MAGIC + b"rest", "jpg"),
        (_PNG_MAGIC + b"rest", "png"),
        (_PDF_MAGIC + b"rest", "pdf"),
        (b"II*\x00rest", "tiff"),
        (b"unknown-bytes", "jpg"),  # 미상은 jpg 폴백
    ],
)
def test_detect_clova_format(data: bytes, expected: str) -> None:
    assert detect_clova_format(data) == expected


async def test_clova_request_declares_actual_format() -> None:
    """PNG 업로드는 message.format 을 png 로 선언해야 함(format 불일치 400 방지)."""
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        # 멀티파트 본문에 JSON message 가 텍스트로 포함됨
        seen["body"] = req.content.decode("latin-1")
        return httpx.Response(200, json=SAMPLE_CLOVA)

    await _engine(handler).extract(_PNG_MAGIC + b"img", "42209")
    assert '"format": "png"' in seen["body"]
    assert "requisition.png" in seen["body"]


async def test_clova_request_serializes_template_id_as_int() -> None:
    """templateIds 는 정수 배열, timestamp 는 0 이 아닌 호출 시각(ms)이어야 함."""
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = req.content.decode("latin-1")
        return httpx.Response(200, json=SAMPLE_CLOVA)

    await _engine(handler).extract(b"img", "42209")
    assert '"templateIds": [42209]' in seen["body"]  # 문자열 "42209" 아님
    assert '"timestamp": 0' not in seen["body"]


async def test_clova_non_numeric_template_id_fails_fast() -> None:
    """비정수 templateId 는 CLOVA 호출 없이 설정 오류로 즉시 실패."""
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=SAMPLE_CLOVA)

    with pytest.raises(OCRParseError) as exc_info:
        await _engine(handler).extract(b"img", "tmpl")
    assert calls["n"] == 0
    assert "정수" in str(exc_info.value)


async def test_clova_4xx_not_retried() -> None:
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={})

    with pytest.raises(OCRParseError):
        await _engine(handler).extract(b"img", "42209")
    assert calls["n"] == 1  # 4xx 는 재시도하지 않음


async def test_clova_4xx_surfaces_response_body() -> None:
    """400 사유(응답 본문)를 에러 메시지에 실어 진단 가능해야 함."""

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"code": "0011", "message": "Invalid templateIds"}
        )

    with pytest.raises(OCRParseError) as exc_info:
        await _engine(handler).extract(b"img", "42209")
    msg = str(exc_info.value)
    assert "HTTP 400" in msg
    assert "Invalid templateIds" in msg  # 실제 사유가 메시지에 노출


async def test_clova_empty_template_id_fails_fast() -> None:
    """빈 templateId 는 CLOVA 호출 없이 설정 누락으로 즉시 실패."""
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=SAMPLE_CLOVA)

    with pytest.raises(OCRParseError) as exc_info:
        await _engine(handler).extract(b"img", "   ")
    assert calls["n"] == 0  # 네트워크 호출 자체가 발생하지 않음
    assert "templateId" in str(exc_info.value)
