# DentalSync OCR Backend — Phase 1 인수인계 문서

> 작성일: 2026-06-11  
> 작성자: Claude (DentalSync Dev 작업 요약)

---

## 1. 프로젝트 개요

치과기공소 의뢰서 이미지를 업로드하면 OCR → 스마트 라우팅 → 신뢰도 스코어링 → HITL 분기 순서로 자동 처리하는 백엔드 파이프라인.

```
이미지 업로드 → 검증/전처리 → SHA-256 해시 → 캐시 조회
    → R2 저장 + orders 생성 → CLOVA OCR → 스마트 라우팅(A/B/C/Shade)
    → 신뢰도 스코어링 → FieldStatus 결정 → OrderStatus 집계 → DB 저장
```

---

## 2. 기술 스택

| 분류 | 기술 |
|------|------|
| 런타임 | Python 3.11+, FastAPI (async) |
| ORM / 마이그레이션 | SQLAlchemy 2.0, Alembic |
| DB | NEON Postgres (serverless) |
| 스토리지 | Cloudflare R2 (boto3, S3 호환) |
| 캐시 | upstash-redis (이미지 해시 TTL 7일) |
| 큐 | QStash (미사용 예정, Phase 2) |
| OCR | Naver CLOVA OCR Template Basic |
| LLM | OpenAI (Type C 텍스트 구조화 전용, 이미지 입력 금지) |
| 이미지 처리 | Pillow (Shade 색상), OpenCV (체크박스/마킹) |
| 배포 | Railway (Dockerfile 없이 자동 감지) |
| 설정 관리 | pydantic-settings |

---

## 3. 완료된 작업 (PR 목록)

| PR | 브랜치 / 커밋 | 내용 |
|----|--------------|------|
| #2 | develop → main | 초기 프로젝트 세팅 |
| #3 | feat/db-schema | DB 스키마 구현 (SQLAlchemy 2.0 + Alembic) |
| #4 | feat/upload-pipeline | 의뢰서 이미지 업로드 파이프라인 앞단 (POST /api/orders) |
| #5 | develop | 브랜치 동기화 |
| #6 | feat/ocr-engine | OCR 엔진 추상화 + CLOVA 구현체 + Mock |
| #7 | feat/scoring-rules (1차) | 도메인 사전 + Type B 결정론적 보정 룰 (LLM 0회) |
| #8 | feat/ocr-engine | OCR 엔진 통합 완료 |
| #9 | feat/marking-detection | Type A 마킹 감지(OpenCV) + Shade 색상 인식(PIL) (LLM 0회) |
| #10 | feat/llm-structurer | Type C 자유텍스트 LLM 구조화 — OpenAI 전환 + 승급 체인 (ADR-0001) |
| #11 | feat/scoring-rules | 필드별 복합 신뢰도 스코어링 + confirmed/needs_review 분기 |
| #12 | feat/marking-detection | OrderPipeline — Step 2~7 연결 오케스트레이터 + 폴링 API |

---

## 4. 코드 구조

```
backend/
├── app/
│   ├── main.py               # FastAPI 진입점, CORS, 예외 핸들러
│   ├── api/
│   │   ├── deps.py           # DI: DB 세션, 스토리지, 캐시, OCR 엔진, 설정
│   │   ├── health.py         # GET /health
│   │   └── orders.py         # POST /api/orders, POST /api/orders/{id}/retry-ocr
│   ├── core/
│   │   ├── config.py         # Settings (pydantic-settings, .env 로드)
│   │   └── scoring.py        # get_scoring_config() — YAML 로드/캐시
│   ├── db/
│   │   ├── base.py           # Base, CreatedAtMixin, TimestampMixin
│   │   ├── models.py         # Lab, User, Order, OrderField, TrainingLabel, FieldAuditLog
│   │   └── session.py        # DB 세션 팩토리
│   ├── domain/
│   │   ├── enums.py          # OrderStatus, FieldType, CorrectedBy, FieldStatus 등
│   │   ├── errors.py         # 도메인 예외 클래스
│   │   └── scoring.py        # ScoringConfig, ScoringWeights, ScoringThresholds (도메인 모델)
│   ├── infra/
│   │   ├── cache.py          # CacheClient (upstash-redis 래퍼)
│   │   ├── storage.py        # StorageClient (R2/S3 래퍼)
│   │   ├── ocr/
│   │   │   ├── base.py       # OCREngine 추상 인터페이스, OCRField, OCRExtractionError
│   │   │   ├── clova.py      # ClovaOCREngine (실제 CLOVA 호출)
│   │   │   └── mock.py       # MockOCREngine (테스트용)
│   │   └── llm/
│   │       ├── base.py       # LLMStructurer 추상 인터페이스, LLMCallError
│   │       └── openai_structurer.py  # OpenAI Structured Outputs 구현체
│   └── services/
│       ├── order_intake.py       # 업로드 앞단: 검증→해시→캐시→R2→orders 생성
│       ├── ocr_runner.py         # OCR 실행 오케스트레이션
│       ├── image_validation.py   # 이미지 검증 (크기, 블러, MIME)
│       ├── preprocessing.py      # 이미지 전처리 (회전, 리사이즈, PDF→PNG)
│       ├── hashing.py            # SHA-256 해시
│       ├── marking_detection.py  # Type A: 체크박스/마킹 감지 (OpenCV)
│       ├── shade_detection.py    # Shade: 색상 인식 (PIL/HSV)
│       ├── type_b_rules.py       # Type B: 날짜/치아번호 정규식 보정
│       ├── type_c_structuring.py # Type C: LLM 승급 체인 + 비용 모니터
│       ├── dictionary.py         # 도메인 사전 fuzzy 매칭
│       ├── order_status.py       # 의뢰서 상태 집계 (필드 상태 → 의뢰서 상태)
│       └── scoring.py            # 필드별 복합 신뢰도 스코어링
├── alembic/
│   └── versions/
│       └── 5287b87ac5bb_initial_schema.py  # 초기 마이그레이션
├── config/
│   └── scoring.yaml          # 스코어링 가중치/임계값 외부 설정
├── data/
│   └── domain_dict/          # 도메인 사전 파일들 (.txt, 치과 용어)
├── tests/                    # pytest 테스트
└── scripts/
    └── test_marking.py       # 마킹 감지 수동 테스트 스크립트
```

---

## 5. DB 스키마 요약

### 테이블 목록

| 테이블 | 역할 |
|--------|------|
| `labs` | 기공소 |
| `users` | 사용자 (owner/staff, RBAC 세분화는 Phase 2) |
| `orders` | 의뢰서 1건 단위 (이미지 URL, 해시, 상태, 날짜) |
| `order_fields` | 필드별 4종 저장: raw / corrected / score / flags |
| `training_labels` | HITL 확정 (raw, corrected) 쌍 학습셋 자동 적재 |
| `field_audit_log` | 필드 변경 이력 |

### OrderField 4종 저장 구조

```
raw_text, raw_bbox, raw_ocr_conf   ← CLOVA OCR 원본
corrected_value, corrected_by      ← 보정값 (system/llm/human)
score, score_components            ← 신뢰도 점수 (가중합 + 분해 JSONB)
flags, status                      ← HITL 여부, confirmed/needs_review
```

### OrderStatus 전이 흐름

```
uploaded → preprocessing → ocr_running → routing
    → needs_review (하나라도 needs_review 필드 존재)
    → auto_confirmed (전 필드 confirmed)
    → confirmed (HITL 완료)
    → ocr_failed (OCR 실패, 수동 재시도 대상)
```

---

## 6. 스마트 라우팅 규칙 (v5)

| 타입 | 비중 | 처리 방식 | LLM 호출 |
|------|------|-----------|---------|
| Type A (체크박스/마킹) | ~40% | OpenCV 색상·밀도 감지 | 0회 |
| Type B (날짜/치아번호) | ~30% | CLOVA + 정규식 보정 | 0회 |
| Shade (색상) | ~5% | PIL HSV 색상 인식 | 0회 |
| Type C (자유텍스트, 명확) | ~20% | CLOVA + LLM_MODEL_PRIMARY | 1회 |
| Type C (자유텍스트, 불명확) | ~5% | LLM_MODEL_PRIMARY → 승급 LLM_MODEL_ESCALATION | 최대 3회 |

설계 목표 LLM 호출률: **~25%**  
비용 가드: `TypeCRatioMonitor` — 20건 이상 누적 시 설계치+15% 초과하면 warning 로그

---

## 7. 신뢰도 스코어링

```yaml
# backend/config/scoring.yaml
weights:
  ocr_conf: 0.5    # CLOVA 자체 신뢰도
  rule_pass: 0.3   # 보정 룰 통과 여부 (1.0 or 0.0)
  dict_match: 0.2  # 도메인 사전 fuzzy 매칭 (rapidfuzz ≥85점)

thresholds:
  general: 0.90
  critical: 0.95   # shade, tooth_numbers, due_date 는 0.95 이상 필요
```

`score < threshold` → `FieldStatus.needs_review` → HITL 분기  
승급(Escalation) 성공 시에도 `forced_hitl=true` 플래그로 강제 HITL

---

## 8. 주요 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/health` | 헬스체크 |
| `POST` | `/api/orders` | 의뢰서 이미지 업로드 (multipart: image, lab_id) |
| `POST` | `/api/orders/{order_id}/retry-ocr` | OCR 실패 건 수동 재시도 |

---

## 9. 환경 변수 (.env)

| 변수 | 설명 |
|------|------|
| `DATABASE_URL` | NEON Postgres 연결 문자열 |
| `REDIS_URL` | upstash-redis URL |
| `CLOVA_API_KEY`, `CLOVA_TEMPLATE_ID`, `CLOVA_OCR_INVOKE_URL`, `CLOVA_OCR_SECRET` | CLOVA OCR 인증 |
| `OPENAI_API_KEY` | OpenAI API 키 |
| `LLM_MODEL_PRIMARY` | Type C 경량 모델명 (예: gpt-5-mini) |
| `LLM_MODEL_ESCALATION` | Type C 승급 모델명 (예: gpt-5) |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_ENDPOINT` | Cloudflare R2 |
| `CORS_ORIGINS` | 허용 프론트 origin (콤마 구분) |
| `SCORING_CONFIG_PATH` | scoring.yaml 경로 (기본: backend/config/scoring.yaml) |

> **주의**: `LLM_MODEL_PRIMARY` / `LLM_MODEL_ESCALATION` 기본값(gpt-5-mini/gpt-5)은 잠정값. 실제 배포 전 OpenAI 라인업·가격 확인 후 `.env`에서 확정 필요 (ADR-0001).

---

## 10. Type C LLM 승급 체인 (ADR-0001)

`backend/app/services/type_c_structuring.py`

```
PRIMARY(경량) ──실패──▶ PRIMARY_RETRY(경량) ──실패──▶ ESCALATION(승급) ──실패──▶ FAILED
    │성공                    │성공                       │성공
    ▼                       ▼                          ▼
   OK                      OK                OK + model_escalated + forced_hitl
```

- Structured Outputs strict 모드 사용 (`additionalProperties: false`, 전 프로퍼티 required)
- 출력 스키마: `{value: string|null, confidence: 0~1}`
- Pydantic 2차 방어: 빈 문자열 자동 거부 (null 강제)
- 결정 기준: `rule_pass = schema_valid(1.0 or 0.0) × llm_confidence`

---

## 11. 아직 미구현 / Phase 2 예정

- **HITL UI** — 검토자가 `needs_review` 필드를 수정하는 화면 (백엔드 API도 미구현)
- **HITL 수정값 학습셋 적재** — `TrainingLabel` 테이블은 있으나 적재 로직 미연결
- **QStash 큐** — 비동기 파이프라인 연결 (현재 동기 처리)
- **인증/RBAC** — `UserRole` enum은 정의되었으나 인증 미들웨어 없음
- **LLM 모델명 확정** — 배포 전 OpenAI 라인업 확인 필요
- **파일럿 튜닝** — `marking_density_marked`, `shade_mark_ratio` 등 이미지 처리 파라미터 실데이터로 조정 필요

---

## 12. 개발 환경 세팅

```bash
cd backend
pip install -r requirements.txt

# .env 파일 작성 (.env.example 참고)
cp .env.example .env

# DB 마이그레이션
alembic upgrade head

# 서버 실행
uvicorn app.main:app --reload

# 테스트
pytest
```

---

## 13. 주요 설계 결정 사항

1. **LLM 벤더 추상화** — `LLMStructurer` 인터페이스로 분리, OpenAI가 기본 구현체. 교체 시 `openai_structurer.py`만 수정.
2. **OCR 추상화** — `OCREngine` 인터페이스. 테스트는 `MockOCREngine` 사용. CLOVA 교체 가능.
3. **스코어링 외부화** — `config/scoring.yaml`. 가중치/임계값을 코드 수정 없이 조정 가능.
4. **이미지 처리 파라미터 외부화** — `Settings`에서 마킹 감지 임계값 관리. 파일럿 데이터로 튜닝 예정.
5. **트랜잭션 원자성** — R2 업로드 실패 시 DB 롤백, DB 커밋 실패 시 R2 객체 보상 삭제.
6. **개인정보 최소수집** — 환자명 외 주민번호/전화번호 컬럼 없음.
