# HITL 검토 수동 검증 시나리오

> **문서 상태:** 현행 · 2026-06-11 · PR #15 기준

> 대상: PR #15 (HITL 검토 API v1 + 프론트 연동)
> 사전 조건: `docker compose -f docker-compose.dev.yml up -d` → 백엔드(`:8000`)·프론트(`:3000`) 기동, `uv run alembic upgrade head` 적용

## 1. 수정 → 확정 플로우 (해피패스)

1. 의뢰서 이미지 업로드 (`POST /api/orders`, lab_id=1)
2. `/review` 진입 → 업로드한 의뢰서가 큐에 표시되는지 확인 (신뢰도 낮은 순 정렬)
3. 행 클릭 → 상세 진입. 좌측 원본 이미지 + bbox 오버레이, 우측 필드 폼 확인
4. needs_review 필드(황/적 테두리) 값 수정 → 필드 이탈(blur) 시:
   - 즉시 "확정됨" 뱃지로 전환 (optimistic)
   - 확정 버튼의 미확정 카운터 감소
5. 전 필드 확정 후 [확정 저장] 활성화 → 클릭 → `/review` 로 복귀, 큐에서 사라짐
6. DB 확인: `orders.status = confirmed`, 수정 필드마다 `training_labels` 1행
   (PII 필드는 마스킹된 값으로 적재), `field_audit_log` 기록

## 2. 필수값 누락 확정 거부

1. needs_review 필드가 남은 상태에서 확정 버튼 → 비활성 + "미확정 N개" 표시 확인
2. API 직접 호출: `POST /api/v1/review/{id}/confirm` → 422 + 위반 필드 목록 응답 확인
3. 프론트에서 422 수신 시 위반 필드로 스크롤 + 에러 메시지 표시 확인

## 3. 필드 값 검증 (422)

| 입력 | 필드 | 기대 결과 |
|------|------|----------|
| `99` | tooth_number | 422, code=`fdi_range` |
| `2026-13-99` | due_date | 422, code=`date_format` |
| 접수일 이전 날짜 | due_date | 422, code=`due_date_after_received` |
| `Z9` | shade | 422, code=`vita_shade` |
| `A2` | shade | 200, confirmed 전환 |

에러 메시지가 필드 옆에 표시되고 값이 롤백되는지 확인.

## 4. 폴링 종료 조건

1. 업로드 직후 상세 진입 → 상단 "처리 중…" 배너 + 2초 간격 폴링 (네트워크 탭)
2. status 가 `needs_review | auto_confirmed | confirmed | ocr_failed` 도달 시
   폴링 중지 + 배너 사라짐 확인
3. `ocr_failed` 의뢰서 → [OCR 재시도] 버튼 노출 → 클릭 시 재처리 확인

## 5. 멱등성 / 동시성

1. 확정 완료된 의뢰서에 `POST /confirm` 재호출 → 409 `ALREADY_CONFIRMED`
2. confirmed 필드에 `PATCH /fields/{key}` → 409 `FIELD_NOT_REVIEWABLE`

## 6. PII 마스킹

1. 상세 화면에서 patient_name 필드 → 기본 마스킹(`홍***`) + PII 뱃지 표시
2. [표시] 토글 → 원본 노출, [숨기기] → 재마스킹

## 7. 인증 (운영 환경)

1. `API_AUTH_TOKEN` 설정 후 토큰 없이 `/api/v1/review/queue` → 401
2. `Authorization: Bearer <토큰>` 포함 → 200
