"""note(자유텍스트) 결정론 추출 룰 — 쉐이드/치식/보철재료. 순수 함수(외부 I/O 0), LLM 0회.

치과 의뢰서는 쉐이드·치식·보철재료를 전용 칸이 아니라 note 본문에 몰아 적는 일이 잦다.
("#36, 37 custom abutment ... zirconia cr. ... A3" 처럼) 이 모듈은 그 본문에서
세 항목을 정규식/키워드로 역추출해 라우팅 백필의 입력으로 쓴다.

- 쉐이드: VITA Classical(A1~D4) + 3D-Master 코드 (data/domain_dict/shade.yaml 과 정합)
- 치식: 산문 속 독립 2자리 FDI(11~48)
- 보철재료: 키워드 → layout `material` enum (Zir → zirconia 등)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# 쉐이드 (VITA)
# --------------------------------------------------------------------------- #
# data/domain_dict/shade.yaml 의 standard 집합과 정합. 오탐 방지를 위해 정규식으로
# 후보를 찾고 이 집합으로 최종 검증한다(D1·1L1 등 비표준 토큰 배제).
_VITA_CLASSIC: frozenset[str] = frozenset(
    {"A1", "A2", "A3", "A3.5", "A4", "B1", "B2", "B3", "B4",
     "C1", "C2", "C3", "C4", "D2", "D3", "D4"}
)
_VITA_3D: frozenset[str] = frozenset(
    {"0M1", "0M2", "0M3", "1M1", "1M2", "2L1.5", "2L2.5", "2M1", "2M2", "2M3",
     "2R1.5", "2R2.5", "3L1.5", "3L2.5", "3M1", "3M2", "3M3", "3R1.5", "3R2.5",
     "4L1.5", "4L2.5", "4M1", "4M2", "4M3", "4R1.5", "4R2.5", "5M1", "5M2", "5M3"}
)
VITA_CODES: frozenset[str] = _VITA_CLASSIC | _VITA_3D

# 후보 토큰: Classical([ABCD]+숫자(.5?)) 또는 3D-Master([0-5]+MLR+숫자(.5?))
_SHADE_RE = re.compile(
    r"(?<![A-Za-z0-9])([ABCD][1-4](?:\.5)?|[0-5][MLR][1-3](?:\.5)?)(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def extract_shades(text: str) -> tuple[str, ...]:
    """본문에서 유효한 VITA 코드만 등장 순서대로(중복 제거) 추출."""
    found: list[str] = []
    for m in _SHADE_RE.finditer(text):
        code = m.group(1).upper()
        if code in VITA_CODES and code not in found:
            found.append(code)
    return tuple(found)


# --------------------------------------------------------------------------- #
# 치식 (FDI 11~48)
# --------------------------------------------------------------------------- #
# 산문 속 독립 2자리 FDI. 앞뒤가 숫자면 제외 → 연도(2026)/차트번호/Platform(5.0x6.0) 오탐 차단.
_FDI_IN_TEXT_RE = re.compile(r"(?<!\d)([1-4][1-8])(?!\d)")


def extract_tooth_numbers(text: str) -> tuple[str, ...]:
    """본문에서 FDI 치식 토큰을 등장 순서대로(중복 제거) 추출."""
    found: list[str] = []
    for m in _FDI_IN_TEXT_RE.finditer(text):
        tok = m.group(1)
        if tok not in found:
            found.append(tok)
    return tuple(found)


# --------------------------------------------------------------------------- #
# 보철재료 (layout `material` enum)
# --------------------------------------------------------------------------- #
# (synonym, enum) 순서 리스트 — data/domain_dict/material.yaml 과 정합.
# ascii 키워드는 단어경계로, 한글 키워드는 부분일치로 매칭한다.
_MATERIAL_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("zirconia", "zirconia"), ("zir", "zirconia"), ("zr", "zirconia"),
    ("지르코니아", "zirconia"), ("질코니아", "zirconia"), ("지르콘", "zirconia"),
    ("지르", "zirconia"),
    ("pfm", "pfm"), ("피에프엠", "pfm"), ("도재금속", "pfm"),
    ("lithium disilicate", "lithium_disilicate"), ("e.max", "lithium_disilicate"),
    ("emax", "lithium_disilicate"), ("이맥스", "lithium_disilicate"),
    ("empress", "lithium_disilicate"), ("엠프레스", "lithium_disilicate"),
    ("gold", "gold"), ("골드", "gold"), ("금관", "gold"),
    ("titanium", "titanium"), ("티타늄", "titanium"),
    ("ceramic", "ceramic"), ("세라믹", "ceramic"),
    ("pmma", "pmma"),
    ("resin", "resin"), ("레진", "resin"),
)


def _matches(keyword: str, text_lower: str) -> bool:
    if keyword.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text_lower) is not None
    return keyword in text_lower


def extract_materials(text: str) -> tuple[str, ...]:
    """본문에서 보철재료 키워드를 enum 으로 변환(첫 등장 순서, 중복 제거)."""
    lower = text.lower()
    found: list[str] = []
    for keyword, enum_value in _MATERIAL_KEYWORDS:
        if enum_value in found:
            continue
        if _matches(keyword, lower):
            found.append(enum_value)
    return tuple(found)


# --------------------------------------------------------------------------- #
# 통합
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NoteExtraction:
    shade: str | None  # 첫 VITA 코드
    tooth_numbers: tuple[str, ...]  # FDI 토큰
    materials: tuple[str, ...]  # layout material enum


def extract_from_note(text: str | None) -> NoteExtraction:
    """note 본문 → (쉐이드 1개, 치식 목록, 재료 목록). 빈 입력은 빈 결과."""
    if not text or not text.strip():
        return NoteExtraction(shade=None, tooth_numbers=(), materials=())
    shades = extract_shades(text)
    return NoteExtraction(
        shade=shades[0] if shades else None,
        tooth_numbers=extract_tooth_numbers(text),
        materials=extract_materials(text),
    )
