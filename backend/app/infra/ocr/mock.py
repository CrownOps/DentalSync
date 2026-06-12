"""Mock OCR 엔진 — 테스트/로컬용.

dental_lab_request_ocr_layout_v1_1_0.json 의 필드 정의(source 에 'ocr' 포함 +
example 보유)를 기반으로 고정 응답을 반환한다. 개인정보(pii)는 환자명만 허용한다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.infra.ocr.base import OCRField

_LAYOUT_PATH = Path(__file__).with_name("layout_v1_1_0.json")
_DUMMY_BBOX: dict[str, Any] = {
    "vertices": [
        {"x": 10, "y": 10},
        {"x": 200, "y": 10},
        {"x": 200, "y": 48},
        {"x": 10, "y": 48},
    ]
}


def _example_text(example: Any) -> str:
    if isinstance(example, str):
        return example
    # 실제 OCR raw 텍스트에 가깝게: 배열 예시는 쉼표 구분 평문으로 평탄화
    if isinstance(example, list):
        return ", ".join(str(item) for item in example)
    return json.dumps(example, ensure_ascii=False)


@lru_cache
def load_layout_fields() -> tuple[OCRField, ...]:
    """layout JSON → 고정 OCRField 목록(불변 캐시)."""
    data = json.loads(_LAYOUT_PATH.read_text(encoding="utf-8"))
    fields: list[OCRField] = []
    for section in data.get("sections", []):
        for spec in section.get("fields", []):
            source = str(spec.get("source", "")).lower()
            example = spec.get("example")
            key = spec.get("key")
            if "ocr" not in source or example in (None, "") or key is None:
                continue
            # 개인정보 최소수집: 환자명 외 PII 필드는 mock 응답에서 제외
            if spec.get("pii") and key != "patient_name":
                continue
            fields.append(
                OCRField(
                    field_key=key,
                    text=_example_text(example),
                    confidence=0.95,
                    bbox=dict(_DUMMY_BBOX),
                )
            )
    return tuple(fields)


class MockOCREngine:
    """OCREngine Protocol 구현 — 항상 동일한 고정 필드 셋 반환."""

    def __init__(self, fields: list[OCRField] | None = None) -> None:
        self._fields: tuple[OCRField, ...] = tuple(fields) if fields is not None else (
            load_layout_fields()
        )

    async def extract(self, image_bytes: bytes, template_id: str) -> list[OCRField]:
        return [f.model_copy() for f in self._fields]
