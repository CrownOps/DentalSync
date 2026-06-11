"""필드 타입 분류 — 템플릿 정의(layout v1.1.0) 기반 선언적 매핑.

분류 자체에 추론 로직을 넣지 않는다: 아래 ROUTE_TYPE_MAP 은 layout JSON 의
필드 key 에 대한 명시적 데이터 매핑이며, 로드 시 layout 과의 정합(존재하는 key 인지)을
검증한다. layout 에 없는 key 가 매핑에 있으면 즉시 실패한다.

(참고) layout v1.1.0 자체에는 A/B/C/SHADE 라우팅 속성이 없어 본 모듈이 그 매핑을
데이터로 보유한다. 차기 layout 버전에서 필드 속성으로 흡수하는 것이 바람직하다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.domain.enums import FieldType

_LAYOUT_PATH = Path(__file__).parents[1] / "infra" / "ocr" / "layout_v1_1_0.json"

# field_key → (FieldType, 도메인 사전 카테고리)
ROUTE_TYPE_MAP: dict[str, tuple[FieldType, str | None]] = {
    # --- Type A: 체크박스/선택지 (OpenCV 마킹 또는 선택지 검증) ---
    "signature_present": (FieldType.A, None),
    "prosthesis_category": (FieldType.A, None),
    "prosthesis_type": (FieldType.A, "prosthesis"),
    "material": (FieldType.A, "material"),
    "connection_type": (FieldType.A, None),
    "is_remake": (FieldType.A, None),
    "remake_reason_code": (FieldType.A, None),
    "tooth_notation": (FieldType.A, None),
    "tooth_region": (FieldType.A, None),
    "tooth_side": (FieldType.A, None),
    "is_implant_case": (FieldType.A, None),
    "connection_hex_type": (FieldType.A, None),
    "is_custom_abutment": (FieldType.A, "abutment"),
    "abutment_material": (FieldType.A, "material"),
    "opposing_tooth": (FieldType.A, None),
    "bite_record": (FieldType.A, None),
    "tray_included": (FieldType.A, None),
    "articulator": (FieldType.A, None),
    "tooth_vitality": (FieldType.A, None),
    # --- Type B: 날짜/치식 (정규식 룰 엔진) ---
    "tooth_numbers": (FieldType.B, None),
    "received_date": (FieldType.B, None),
    "due_date": (FieldType.B, None),
    "completed_date": (FieldType.B, None),
    # --- SHADE: 색상 인식 + 사전 ---
    "shade": (FieldType.SHADE, "shade"),
    # --- Type C: 자유텍스트 (LLM 구조화) ---
    "clinic_name": (FieldType.C, None),
    "clinic_contact": (FieldType.C, None),
    "lab_name": (FieldType.C, None),
    "doctor_name": (FieldType.C, None),
    "doctor_license_no": (FieldType.C, None),
    "patient_name": (FieldType.C, None),
    "work_item_raw": (FieldType.C, None),
    "remake_reason_text": (FieldType.C, None),
    "implant_manufacturer": (FieldType.C, None),
    "implant_system": (FieldType.C, None),
    "implant_product_name": (FieldType.C, None),
    "platform_size": (FieldType.C, None),
    "implant_raw_text": (FieldType.C, None),
    "scanbody_manufacturer": (FieldType.C, None),
    "scanbody_size": (FieldType.C, None),
    "scanbody_raw_text": (FieldType.C, None),
    "contact_instruction": (FieldType.C, None),
    "bite_preference": (FieldType.C, None),
    "margin_instruction": (FieldType.C, None),
    "ocr_raw_text": (FieldType.C, None),
}


@dataclass(frozen=True)
class FieldRoute:
    field_key: str
    field_type: FieldType
    dict_category: str | None = None


@lru_cache
def load_field_routes(layout_path: Path = _LAYOUT_PATH) -> dict[str, FieldRoute]:
    """매핑 로드 + layout 정합 검증."""
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    layout_keys = {
        f["key"] for section in layout.get("sections", []) for f in section.get("fields", [])
    }
    unknown = sorted(set(ROUTE_TYPE_MAP) - layout_keys)
    if unknown:
        raise ValueError(f"layout v1.1.0 에 존재하지 않는 매핑 키: {unknown}")

    return {
        key: FieldRoute(field_key=key, field_type=ftype, dict_category=cat)
        for key, (ftype, cat) in ROUTE_TYPE_MAP.items()
    }
