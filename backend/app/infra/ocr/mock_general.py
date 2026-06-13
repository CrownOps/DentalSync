"""Mock General OCR 엔진 — 키 없이 General(자유양식) 경로를 로컬 시연.

템플릿 mock(mock.py)과 달리 레이아웃 예시가 아니라, 실제 손글씨/자유양식 의뢰서에
가까운 **자유텍스트 한 덩어리**를 단일 ocr_raw_text 필드로 반환한다. 후속 LLM 문서
구조화(document_structuring) + Mock LLM 구조화가 이 텍스트를 파싱해 필드를 채운다.

MOCK_GENERAL_TEXT 환경변수로 본문을 덮어쓸 수 있다(다른 양식 시연용).
"""

from __future__ import annotations

import os

from app.infra.ocr.base import OCRField
from app.infra.ocr.clova_general import RAW_TEXT_KEY

# 템플릿 샘플(청담세브란스…)과 다른 자유양식 — 칸이 정해지지 않은 메모형 의뢰서.
_SAMPLE_TEXT = (
    "청구치과의원\n"
    "원장 김민수\n"
    "환자: 홍길동 (M/52)\n"
    "#36, 37 지르코니아 크라운 제작 부탁드립니다.\n"
    "shade A3, 컨택 강하게 / 교합 체크\n"
    "납기 2026-06-20 까지\n"
)


class MockGeneralOCREngine:
    """OCREngine Protocol 구현 — 항상 동일한 자유양식 텍스트 1건 반환."""

    def __init__(self, text: str | None = None) -> None:
        self._text = text if text is not None else os.getenv("MOCK_GENERAL_TEXT", _SAMPLE_TEXT)

    async def extract(self, image_bytes: bytes, template_id: str) -> list[OCRField]:
        return [OCRField(field_key=RAW_TEXT_KEY, text=self._text, confidence=0.9, bbox=None)]
