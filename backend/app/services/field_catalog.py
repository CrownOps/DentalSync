"""레이아웃 필드 카탈로그 — layout_v1_1_0.json 단일 소스 기반 필드 스펙 조회.

라우팅이 키워드 휴리스틱 대신 레이아웃 메타데이터(type/source/options)로
필드 타입을 결정할 수 있도록 field_key → FieldSpec 맵을 제공한다.
로딩은 모듈 수명 동안 1회(lru_cache), 조회는 순수 함수.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_LAYOUT_PATH = Path(__file__).resolve().parents[1] / "infra" / "ocr" / "layout_v1_1_0.json"


@dataclass(frozen=True)
class FieldSpec:
    """레이아웃 필드 정의 중 라우팅에 필요한 부분."""

    key: str
    section_key: str
    layout_type: str  # text | textarea | select | array | boolean | date | datetime | ...
    source: str  # ocr | ocr_or_llm | llm | system | ...
    options: tuple[str, ...] = ()
    item_options: tuple[str, ...] = ()

    @property
    def has_options(self) -> bool:
        """select 단일 선택 또는 array 다중 선택 옵션 보유 여부 — Type A 후보."""
        return bool(self.options or self.item_options)

    @property
    def llm_allowed(self) -> bool:
        """레이아웃이 LLM 구조화를 허용한 필드인지 (source 에 'llm' 포함)."""
        return "llm" in self.source


@lru_cache
def get_field_catalog() -> dict[str, FieldSpec]:
    """layout JSON → field_key 기준 FieldSpec 맵 (불변 캐시)."""
    data = json.loads(_LAYOUT_PATH.read_text(encoding="utf-8"))
    catalog: dict[str, FieldSpec] = {}
    for section in data.get("sections", []):
        section_key = str(section.get("section_key", ""))
        for spec in section.get("fields", []):
            key = spec.get("key")
            if not key:
                continue
            catalog[key] = FieldSpec(
                key=key,
                section_key=section_key,
                layout_type=str(spec.get("type", "")).lower(),
                source=str(spec.get("source", "")).lower(),
                options=tuple(str(o) for o in spec.get("options") or ()),
                item_options=tuple(str(o) for o in spec.get("item_options") or ()),
            )
    return catalog


def get_field_spec(field_key: str) -> FieldSpec | None:
    """field_key 의 레이아웃 스펙. 레이아웃에 없는 키는 None (호출측 폴백 대상)."""
    return get_field_catalog().get(field_key)
