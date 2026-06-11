# ADR-0002: HITL 검토 API v1 설계 결정

- 상태: 승인됨
- 날짜: 2026-06-11
- 관련 PR: #15

## 맥락

HITL 검토 플로우(검토 큐 → 상세 → 인라인 수정 → 확정)와 라우팅 결과 저장을
구현하면서 아키텍처 v3 문서가 정하지 않은 세부 사항에 대해 내린 결정을 기록한다.

## 결정 사항

### 1. 기존 `/api/orders` 유지 + 신규 `/api/v1/review/` 분리

기존 PR #14 의 HITL 엔드포인트(`GET /api/orders`, `PATCH /confirm`)는 그대로 두고,
스펙의 v1 명세를 충족하는 새 라우터를 `/api/v1/review/` 에 추가했다.
업로드·재시도 등 비검토 엔드포인트는 `/api/orders` 에 유지된다.
프론트 검토 화면은 v1 으로 전환 완료 — 기존 `confirm` 경로는 Phase 2 에서 제거 예정.

### 2. confidence 구성요소 이중 기록 (JSONB + 개별 컬럼)

`order_fields.score_components` JSONB 외에 `ocr_conf` / `rule_pass` / `dict_match`
Float 개별 컬럼을 추가(마이그레이션 `a1c3e9f02d41`). 임계값 튜닝 분석 시
JSONB 연산 없이 직접 집계 가능하도록 하기 위함. 쓰기는 `RoutingResultStore` 가
양쪽에 동시에 기록한다.

### 3. Phase 1 라우팅은 텍스트 기반 — `routing.py`

`run_ocr` 마지막 단계에서 `route_ocr_fields()` → `store_routing_result()` 를 호출해
`routing → needs_review | auto_confirmed` 전이를 완결한다. Phase 1 매핑 규칙:

- field_key 에 치아/날짜 패턴 → Type B (`type_b_rules` 적용, rule_pass 산출)
- shade 패턴 → SHADE (이미지 기반 PIL 감지는 후속 단계에서 corrected 갱신)
- 그 외 → Type C (ocr_conf 단독 점수, 가중치 재정규화)

Type A(OpenCV 체크박스)·Shade(PIL)·Type C(LLM) 의 이미지/LLM 기반 처리는
서비스가 이미 존재하나(`marking_detection` 등) 파이프라인 연결은 후속 작업.
연결 시 `route_ocr_fields` 의 corrected_value/score 산출부만 교체하면 된다.

### 4. OCR 재시도 시 order_fields 전체 재생성

`store_routing_result` 는 INSERT 전에 해당 order 의 기존 필드를 삭제한다.
(order_id, field_key) 유니크 제약 충돌 방지 + 재시도 시 이전 결과 잔존 방지.
사람이 수정한 후 재시도하면 수정값도 함께 초기화된다 — 재시도는 needs_review
이전 단계(ocr_failed)에서만 노출되므로 Phase 1 에서는 허용.

### 5. training_labels 적재 시점: 확정 시 일괄

`PATCH /fields/{key}` 는 corrected 만 갱신하고 training_labels 를 적재하지 않는다.
확정 전 재수정이 가능하므로, `POST /confirm` 트랜잭션 안에서
`corrected_by_human=true` 또는 `raw ≠ 최종값` 필드만 일괄 INSERT 한다.

### 6. PII 익명화 규칙

PII 필드 키 목록(Phase 1 하드코딩: patient_name 등 — 레이아웃 정의 v1.1.0 의
`pii: true` 와 동기화)에 해당하면 training_labels 적재 전 첫 글자 + `*` 마스킹.
레이아웃 JSON 에서 동적 로드하는 것은 후속 작업.

### 7. 인증: 단일 베어러 토큰 dependency

`require_auth` dependency 를 `/api/v1/review/` 라우터 전체에 적용.
`API_AUTH_TOKEN` 미설정(로컬)이면 통과, 설정 시 Bearer 일치 필수
(`secrets.compare_digest` 사용). Phase 2 RBAC 은 이 dependency 만 교체하면 된다.

### 8. 페이지네이션: offset 방식

검토 큐는 기공소당 일 수십 건 규모이므로 cursor 의 복잡성이 불필요.
`limit`(기본 20, 최대 100) / `offset` + `total` 반환.

## 결과

- 상태 전이 완결: `uploaded → … → routing → needs_review | auto_confirmed → confirmed`
- 테스트: 백엔드 178개 + 프론트 vitest 8개 통과
