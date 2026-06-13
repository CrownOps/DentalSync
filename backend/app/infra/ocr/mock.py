"""Mock OCR 엔진 — 테스트/로컬용.

dental_lab_request_ocr_layout_v1_1_0.json 의 필드 정의(source 에 'ocr' 포함 +
example 보유)를 기반으로 고정 응답을 반환한다. 개인정보(pii)는 환자명만 허용한다.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.infra.ocr.base import OCRField

_LAYOUT_PATH = Path(__file__).with_name("layout_v1_1_0.json")

# 로컬 QA 전용: note 백필 시연을 위해 mock 응답에서 제외할 전용 칸.
# 의사가 이 값들을 note(ocr_raw_text)에만 적은 상황을 재현 → 라우팅이 note 에서 역추출한다.
_NOTE_ONLY_OMIT_KEYS = frozenset({"shade", "tooth_numbers", "material"})
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
        fields = self._fields

        # 로컬 QA 전용: MOCK_OCR_NOTE_ONLY 로 쉐이드/치식/재료 전용 칸을 제외해
        # note 백필 경로를 재현한다(자동추출 시연용). note(ocr_raw_text)는 유지.
        if os.getenv("MOCK_OCR_NOTE_ONLY"):
            fields = tuple(f for f in fields if f.field_key not in _NOTE_ONLY_OMIT_KEYS)

        # 로컬 QA 전용: MOCK_OCR_CONFIDENCE 로 OCR 신뢰도를 낮춰 저품질 스캔을
        # 재현한다(needs_review 분기 시연용). 미설정 시 layout 기본값(0.95) 유지.
        override = os.getenv("MOCK_OCR_CONFIDENCE")
        if override:
            conf = float(override)
            return [f.model_copy(update={"confidence": conf}) for f in fields]
        return [f.model_copy() for f in fields]
