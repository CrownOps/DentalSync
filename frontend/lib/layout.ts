// 레이아웃 섹션·필드 메타데이터 — dental_lab_request_ocr_layout_v1_1_0.json 단일 소스 기준

export interface SectionDef {
  key: string;
  label: string;
  fieldKeys: readonly string[];
}

// 치명 필드 — 임계값 0.95, UI 강조 대상 (레이아웃 critical: true)
export const CRITICAL_FIELD_KEYS = new Set<string>([
  "tooth_numbers",
  "shade",
  "due_date",
  "internal_due_date",
]);

// 확정 저장 시 필수 필드 — 누락 시 저장 거부 (REQ-002)
export const REQUIRED_FIELD_KEYS = new Set<string>([
  "patient_name",
  "tooth_numbers",
  "prosthesis_category",
]);

// PII 필드 — 기본 마스킹 표시
export const PII_FIELD_KEYS = new Set<string>([
  "patient_name",
  "chart_no",
  "sex",
  "age",
  "birth_date",
  "patient_id",
  "ssn",
  "phone",
]);

// 섹션 순서는 레이아웃 v1.1.0 sections 배열 순서와 동일
export const LAYOUT_SECTIONS: SectionDef[] = [
  {
    key: "case_basic",
    label: "케이스 기본정보",
    fieldKeys: [
      "clinic_name", "clinic_contact", "lab_name", "doctor_name",
      "doctor_license_no", "signature_present",
      "patient_name", "chart_no", "sex", "age", "birth_date",
      "received_date", "due_date", "completed_date",
    ],
  },
  {
    key: "tooth",
    label: "치식·부위 정보",
    fieldKeys: [
      "tooth_numbers", "tooth_notation", "tooth_numbers_fdi",
      "tooth_region", "tooth_side", "tooth_validation_status",
    ],
  },
  {
    key: "prosthesis",
    label: "보철 작업 정보",
    fieldKeys: [
      "prosthesis_category", "prosthesis_type", "material", "work_item_raw",
      "connection_type", "is_remake", "remake_reason_code", "remake_reason_text",
    ],
  },
  {
    key: "implant",
    label: "임플란트 정보",
    fieldKeys: [
      "is_implant_case", "implant_manufacturer", "implant_system",
      "implant_product_name", "platform_size", "connection_hex_type",
      "is_custom_abutment", "implant_raw_text",
    ],
  },
  {
    key: "abutment_scanbody",
    label: "어버트먼트/스캔바디 정보",
    fieldKeys: [
      "abutment_material", "margin_position", "margin_offset_mm",
      "scanbody_manufacturer", "scanbody_size", "scanbody_raw_text",
      "scanbody_validation_status",
    ],
  },
  {
    key: "manufacturing_conditions",
    label: "제작 조건",
    fieldKeys: [
      "shade", "opposing_tooth", "bite_record", "tray_included",
      "articulator", "contact_instruction", "bite_preference",
      "margin_instruction", "tooth_vitality", "special_flags",
    ],
  },
  {
    key: "internal_routing",
    label: "내부 라우팅",
    fieldKeys: [
      "clinic_initial", "internal_due_date", "priority", "assignee", "internal_memo",
    ],
  },
  {
    key: "note",
    label: "Note",
    fieldKeys: [
      "ocr_raw_text", "llm_summary", "structured_extraction", "unparsed_tokens",
    ],
  },
];

// 필드 키 → 한국어 라벨 (레이아웃 label 필드 기준)
export const FIELD_LABELS: Readonly<Record<string, string>> = {
  // case_basic
  clinic_name: "치과명",
  clinic_contact: "치과 주소/연락처",
  lab_name: "기공소명",
  doctor_name: "담당 원장",
  doctor_license_no: "치과의사 면허번호",
  signature_present: "서명/날인",
  patient_name: "환자명",
  chart_no: "차트번호",
  sex: "성별",
  age: "나이",
  birth_date: "생년월일",
  received_date: "접수일",
  due_date: "납기일(본문)",
  completed_date: "완성일",
  // tooth
  tooth_numbers: "치식(원본)",
  tooth_notation: "치식 표기 체계",
  tooth_numbers_fdi: "치식(FDI 정규화)",
  tooth_region: "상악/하악",
  tooth_side: "좌/우",
  tooth_validation_status: "치식 검증 상태",
  // prosthesis
  prosthesis_category: "보철 형태",
  prosthesis_type: "작업 종류",
  material: "재료",
  work_item_raw: "작업 원문",
  connection_type: "연결 여부",
  is_remake: "Remake 여부",
  remake_reason_code: "Remake 원인 코드",
  remake_reason_text: "Remake 사유(원문)",
  // implant
  is_implant_case: "임플란트 케이스 여부",
  implant_manufacturer: "임플란트 제조사",
  implant_system: "시스템",
  implant_product_name: "제품명",
  platform_size: "Platform Size",
  connection_hex_type: "Hex/Non-Hex",
  is_custom_abutment: "Custom Abutment 여부",
  implant_raw_text: "임플란트 원문",
  // abutment_scanbody
  abutment_material: "Abutment 재료",
  margin_position: "Margin Position",
  margin_offset_mm: "Margin 값(mm)",
  scanbody_manufacturer: "Scanbody 제조사",
  scanbody_size: "Scanbody 사이즈",
  scanbody_raw_text: "Scanbody 원문",
  scanbody_validation_status: "스캔바디 검증 상태",
  // manufacturing_conditions
  shade: "Shade",
  opposing_tooth: "대합치",
  bite_record: "Bite",
  tray_included: "Tray",
  articulator: "교합기",
  contact_instruction: "Contact 요청",
  bite_preference: "Bite 요청",
  margin_instruction: "Margin 요청",
  tooth_vitality: "변색 정도",
  special_flags: "SCRP/Hook/기타",
  // internal_routing
  clinic_initial: "치과 앞글자",
  internal_due_date: "납품 요구일(내부)",
  priority: "긴급 여부",
  assignee: "담당자",
  internal_memo: "내부 메모",
  // note
  ocr_raw_text: "OCR 원문",
  llm_summary: "LLM 요약",
  structured_extraction: "구조화 추출 결과",
  unparsed_tokens: "해석 실패 단어",
};

export function getFieldLabel(fieldKey: string): string {
  return FIELD_LABELS[fieldKey] ?? fieldKey.replace(/_/g, " ");
}

// 라우팅 타입 → 한국어 설명
export const ROUTING_TYPE_LABELS: Readonly<Record<string, string>> = {
  A: "Type A — 체크박스/마킹 (OpenCV 룰)",
  B: "Type B — 날짜/치아번호 (정규식)",
  C: "Type C — 자유텍스트 (LLM)",
  SHADE: "쉐이드 감지 (PIL 색상)",
};

// 주문 상태 → 한국어
export const ORDER_STATUS_LABELS: Readonly<Record<string, string>> = {
  uploaded: "업로드됨",
  preprocessing: "전처리 중",
  ocr_running: "OCR 처리 중",
  routing: "라우팅 중",
  needs_review: "검토 필요",
  auto_confirmed: "자동 확정",
  confirmed: "확정됨",
  ocr_failed: "OCR 실패",
};
