# DentalSync OCR Phase 1 — 단계별 개발 프롬프트

> **문서 상태:** 이력 문서 · v2.0 기반 (현행 설계는 [v3](../design/OCR_시스템_아키텍처_v3.md)) · 수정 불필요 (ADR-0001 참조)

기준 문서: OCR 시스템 아키텍처 v2.0 (26.06.10) · 기술 스택 v5 · GIT 코드 컨벤션
사용법: 각 단계의 프롬프트를 Claude Code(또는 다른 코딩 에이전트)에 순서대로 입력한다. 단계마다 브랜치를 새로 생성하고, 완료 기준을 통과한 뒤 develop에 병합한다.

**모든 프롬프트 앞에 붙일 공통 컨텍스트 블록:**

```
[프로젝트 컨텍스트 — 모든 작업에 적용]
- 프로젝트: DentalSync — 치과 기공의뢰서 OCR 파이프라인 (Phase 1 MVP)
- 스택: FastAPI(Railway) + Next.js(Vercel) + NEON Postgres + Cloudflare R2 + Upstash Redis + CLOVA OCR + Anthropic API
- 확정 원칙:
  1. OCR 엔진은 CLOVA 단일, 의뢰서당 1회 호출. 멀티모달 LLM 이미지 추출 금지.
  2. LLM 역할은 text→JSON 구조화로 한정 (Type C만).
  3. 필드 타입별 결정론적 처리 우선, LLM 호출률 ~25% 유지.
  4. 신뢰도는 복합 점수 단일 지표 (score = 0.5·ocr_conf + 0.3·rule_pass + 0.2·dict_match), 임계값 일반 0.90 / 치명 필드(쉐이드·치식·납기) 0.95. 가중치·임계값은 설정 파일로 외부화.
  5. 모든 필드는 4종 저장: raw / corrected / confidence / flags.
  6. HITL 수정값은 training_labels에 자동 적재.
  7. 환자명 외 주민번호·전화번호 저장 금지.
  8. OCREngine은 인터페이스로 추상화 (CLOVA → 자체 모델 교체 가능 구조).
- 비동기: FastAPI BackgroundTasks + 상태 폴링 (QStash 사용 금지 — Phase 2).
- 상태 전이: uploaded → preprocessing → ocr_running → routing → needs_review | auto_confirmed → confirmed
- Git: 브랜치 feat/#이슈번호-작업명 (소문자, 하이픈), 커밋 <타입>: <메시지> (feat/fix/refactor/chore/style)
- 트랜잭션 단위는 의뢰서(order). 부분 저장 금지.
```

---

## Step 0 — 프로젝트 스캐폴딩 & 개발 환경

브랜치: `chore/#1-project-scaffold`

```
모노레포로 DentalSync 프로젝트를 스캐폴딩해줘.

구조:
- /backend — FastAPI (Python 3.12, uv 또는 poetry)
  - app/api, app/services, app/domain, app/infra(외부 서비스 어댑터), app/core(설정), app/db
  - pytest + httpx 테스트 환경, ruff + mypy 설정
- /frontend — Next.js 14+ (App Router, TypeScript), TanStack Query, Tailwind
- 루트: .gitignore, README, .env.example (CLOVA_API_KEY, CLOVA_TEMPLATE_ID, ANTHROPIC_API_KEY, DATABASE_URL, R2_*, UPSTASH_REDIS_*)

요구사항:
- 설정은 pydantic-settings로 로드. 신뢰도 가중치(w1=0.5, w2=0.3, w3=0.2)와
  임계값(일반 0.90, 치명 0.95)은 config/scoring.yaml로 외부화하고 로더 작성.
- /health 엔드포인트 + 더미 테스트 1개로 CI 통과 확인.
- docker-compose.dev.yml: Postgres + Redis 로컬 개발용.

완료 기준: backend 테스트 통과, frontend dev 서버 기동, .env.example만으로 필요한 환경변수 전부 파악 가능.
```

---

## Step 1 — DB 스키마 & 마이그레이션

브랜치: `feat/#2-db-schema`

```
SQLAlchemy 2.0 + Alembic으로 DB 스키마를 구현해줘.

테이블:
1. labs — 기공소 (id, name, template_id, created_at)
2. users — 사용자 (id, lab_id FK, name, role, created_at) ※ RBAC 세분화는 Phase 2, role은 enum(owner, staff)만
3. orders — 의뢰서 (id, lab_id FK, image_url(R2 키), image_hash, status enum:
   uploaded/preprocessing/ocr_running/routing/needs_review/auto_confirmed/confirmed/ocr_failed,
   received_at, due_date, created_at, updated_at)
4. order_fields — 필드별 4종 저장 (id, order_id FK, field_key, field_type enum: A/B/C/SHADE,
   raw_text, raw_bbox JSONB, raw_ocr_conf float,
   corrected_value, corrected_by(nullable, system/llm/human 구분),
   score float, score_components JSONB(ocr_conf, rule_pass, dict_match),
   flags JSONB(needs_review, forced_hitl, sonnet_escalated 등),
   status enum: confirmed/needs_review, updated_at)
5. training_labels — (id, order_field_id FK, raw_text, corrected_value, field_type, lab_id, corrected_by, created_at)
6. field_audit_log — 변경 이력 (order_field_id, before, after, actor, created_at)

제약:
- 환자명 외 개인정보 컬럼 생성 금지 (주민번호·전화번호 컬럼 자체를 만들지 않는다).
- order_fields에 (order_id, field_key) unique 제약.
- 의뢰서 단위 상태 규칙: 전 필드 confirmed → orders.status = auto_confirmed,
  하나라도 needs_review → orders.status = needs_review. 이 규칙은 서비스 레이어 함수로 구현하고 단위 테스트 작성.

완료 기준: alembic upgrade head 성공, 상태 전이 규칙 테스트 통과.
```

---

## Step 2 — 업로드 · 전처리 · R2 저장 · 해시 캐시

브랜치: `feat/#3-upload-preprocess`

```
의뢰서 이미지 업로드 파이프라인의 앞단을 구현해줘.

엔드포인트: POST /api/orders (multipart: image, lab_id)

흐름:
1. 이미지 검증: jpg/png/pdf 허용, 최대 크기 제한, 해상도/블러 임계 미달 시
   422 반려 + "재촬영 안내" 에러 코드 반환 (블러는 OpenCV Laplacian variance로 측정, 임계값 설정 외부화).
2. 전처리: 기울기 보정(deskew), 노이즈 제거, 리사이즈 — OpenCV 기반 preprocessing 모듈로 분리.
3. SHA-256 이미지 해시 계산.
4. Upstash Redis 해시 캐시 조회 (TTL 7일):
   - HIT → 캐시된 OCR 결과 재사용, CLOVA 호출 생략 플래그 설정.
   - MISS → 다음 단계 진행.
5. 원본을 Cloudflare R2에 업로드 (boto3 S3 호환 API), orders 레코드 생성(status: uploaded).
6. R2 또는 DB 실패 시 업로드 자체를 실패 응답으로 처리 — 부분 저장 금지, 트랜잭션 단위는 의뢰서.

테스트: 정상 업로드, 블러 반려, 캐시 HIT/MISS, R2 실패 시 롤백.
완료 기준: 모든 테스트 통과, 전처리 모듈이 독립 함수로 분리되어 있을 것.
```

---

## Step 3 — OCREngine 인터페이스 & CLOVA 어댑터

브랜치: `feat/#4-clova-adapter`

```
OCR 엔진 추상화 레이어와 CLOVA 구현체를 만들어줘.

1. OCREngine 추상 인터페이스 (Protocol 또는 ABC):
   - async def extract(image_bytes, template_id) -> list[OCRField]
   - OCRField: field_key, text, bbox, confidence (CLOVA inferConfidence 매핑)
   - 자체 모델 전환(Phase 3) 시 이 인터페이스만 구현하면 교체 가능해야 함.

2. CLOVAOCREngine 구현:
   - CLOVA OCR Template API (Template Basic) 호출, 의뢰서당 정확히 1회.
   - 실패 처리: 지수 백오프 3회 재시도(tenacity) → 최종 실패 시 orders.status = ocr_failed로 갱신하고
     수동 재시도 가능하도록 POST /api/orders/{id}/retry-ocr 엔드포인트 추가.
   - 응답 파싱은 CLOVA Template 응답 스키마 기준, 파싱 실패도 ocr_failed 처리.

3. MockOCREngine: 테스트/로컬 개발용 — dental_lab_request_ocr_layout_v1_1_0.json의
   필드 정의를 기반으로 고정 응답 반환.

테스트: 재시도 동작(3회 후 실패), 인터페이스 교체 가능성(DI로 Mock 주입), 응답 파싱.
완료 기준: 서비스 레이어가 CLOVAOCREngine을 직접 import하지 않고 인터페이스에만 의존할 것.
```

---

## Step 4 — 도메인 사전 & Type B 룰 엔진

브랜치: `feat/#5-domain-dict-rules`

```
도메인 사전과 Type B(날짜/치식/납기) 결정론적 보정 룰을 구현해줘. LLM 호출 0회.

1. 도메인 사전 (data/domain_dict/*.yaml):
   - 보철물 종류, 재료, 쉐이드 코드(VITA Classical A1~D4 + 3D Master), 어버트먼트 용어 등
     카테고리별 YAML. 표준어 + 동의어/오기 변형(예: "지르코니아" ← "질코니아", "zirconia") 매핑.
   - DictMatcher: 정확 매칭 1.0 / 유사 보정 0.7 (rapidfuzz, 임계 유사도 설정 외부화) / 미매칭 0.3 반환.
   - 사전에 해당 없는 필드(환자명 등)는 dict_match 항 제외 후 가중치 재정규화 — 재정규화 로직 단위 테스트 필수.

2. Type B 룰 엔진:
   - 치식: FDI 표기 11~48 범위 검증. 범위 밖 값은 rule_pass=0.0 (사실상 HITL 직행).
     복수 치아 표기("11,12", "11-13" 브릿지)는 파싱 후 개별 검증.
   - 날짜: 다양한 한국 표기("26.6.15", "6/15", "2026-06-15") 정규화 → ISO 8601.
     유효하지 않은 날짜 rule_pass=0.0.
   - 납기: due_date ≥ received_at 검증. 위반 시 rule_pass=0.0.
   - 부분 통과(파싱은 됐으나 일부 모호) rule_pass=0.5.

테스트: 치식 경계값(10, 11, 48, 49), 날짜 표기 변형 최소 10케이스, 납기 역전, 유사 보정 매칭.
완료 기준: 룰 엔진은 순수 함수로 작성(외부 I/O 없음), 테스트 커버리지 90% 이상.
```

---

## Step 5 — Type A 마킹 감지 & Shade 색상 인식

브랜치: `feat/#6-marking-shade`

```
Type A(체크박스/마킹)와 Shade(시각 도형) 처리를 구현해줘. LLM 호출 0회.

1. Type A — OpenCV 마킹 감지:
   - 입력: 원본 이미지 + 템플릿 정의의 체크박스 bbox 목록.
   - 각 bbox 영역의 마킹 여부 판정: 픽셀 밀도 + 색상 마킹(빨강/파랑 펜) 감지.
   - 단일 마킹 명확 → rule_pass=1.0, 복수 마킹 또는 모호 → rule_pass=0.0.
   - 판정 파라미터(밀도 임계 등)는 설정 외부화 — 파일럿에서 튜닝 대상.

2. Shade — PIL 색상 인식:
   - 쉐이드 표기 영역의 색상/도형 마킹을 감지해 VITA 코드로 매핑.
   - 매핑 테이블은 Step 4의 도메인 사전 재사용.
   - 쉐이드는 치명 필드 — 임계값 0.95 적용 대상임을 flags에 명시.

3. 두 모듈 모두 (value, rule_pass, debug_info) 형태로 반환해 스코어링 단계에서 합성 가능하게.

테스트: 샘플 이미지 fixture로 단일/복수/무마킹 케이스, 색상 펜 변형.
완료 기준: 실제 의뢰서 샘플 1장으로 e2e 수동 검증 스크립트(scripts/test_marking.py) 제공.
```

---

## Step 6 — Type C LLM 구조화 (Haiku → Sonnet 승급)

브랜치: `feat/#7-llm-structuring`

```
Type C 자유텍스트의 text→JSON 구조화를 구현해줘. LLM은 텍스트 구조화 전용 — 이미지 입력 절대 금지.

1. LLMStructurer (Anthropic API):
   - 1차: Claude Haiku. 입력은 CLOVA가 추출한 텍스트 + 필드 스키마(JSON Schema).
   - 시스템 프롬프트: 치과 기공 도메인 컨텍스트 + 출력은 JSON만(프리앰블·마크다운 금지) +
     자기보고 confidence(0~1) 필드 포함.
   - 출력 검증: JSON 파싱 → 스키마 검증(pydantic).

2. 승급 체인 (실패 처리 정책 그대로):
   - JSON 파싱/스키마 검증 실패 → Haiku 1회 재시도
   - → 실패 시 Sonnet 승급 + flags.sonnet_escalated=true + HITL 강제(forced_hitl=true, 점수 무관)
   - → Sonnet도 실패 시 해당 필드 raw만 저장하고 HITL 강제.

3. rule_pass 산정: JSON 스키마 검증 통과 여부 + LLM 자기보고 confidence 결합.

4. 비용 가드: 의뢰서당 LLM 호출 수를 로깅하고, Type C 비중이 설계치(~25%)를 크게 벗어나면 경고 로그.

테스트: Anthropic API는 mock으로 — 정상 구조화, 파싱 실패 → 재시도 → Sonnet 승급 → 최종 실패 체인 전체.
완료 기준: 승급 체인이 상태 머신으로 명확히 분리되어 있고, 모든 분기에 테스트 존재.
```

---

## Step 7 — 복합 신뢰도 스코어링 & 분기

브랜치: `feat/#8-confidence-scoring`

```
필드별 복합 신뢰도 스코어링과 분기 로직을 구현해줘.

1. ScoringService:
   - score = w1·ocr_conf + w2·rule_pass + w3·dict_match (초기 w1=0.5, w2=0.3, w3=0.2)
   - dict_match 미적용 필드는 해당 항 제외 후 가중치 재정규화 (Step 4 로직 재사용).
   - 가중치·임계값은 config/scoring.yaml에서 로드 — 코드 하드코딩 금지.

2. 분기:
   - 일반 필드: score ≥ 0.90 → confirmed / 미만 → needs_review
   - 치명 필드(쉐이드, 치식, 납기): 임계값 0.95
   - forced_hitl 플래그 필드: 점수 무관 needs_review
   - 의뢰서 단위: 전 필드 confirmed → auto_confirmed / 하나라도 needs_review → 검토 큐

3. 저장: order_fields에 4종(raw/corrected/score+components/flags) 일괄 저장.
   score_components에 ocr_conf, rule_pass, dict_match 개별값 보존 — 임계값 튜닝 근거 데이터.

테스트: 경계값(0.89/0.90/0.94/0.95), 재정규화 산식, 치명 필드 분기, forced_hitl 우선.
완료 기준: 스코어링이 순수 함수, 설정 파일 변경만으로 임계값 조정 가능함을 테스트로 증명.
```

---

## Step 8 — 파이프라인 오케스트레이션 & 비동기 처리

브랜치: `feat/#9-pipeline-orchestration`

```
Step 2~7 모듈을 연결하는 파이프라인 오케스트레이터를 구현해줘.

1. OrderPipeline 서비스:
   업로드 완료 → FastAPI BackgroundTasks로 비동기 실행 (QStash 금지 — Phase 1 결정):
   preprocessing → ocr_running(CLOVA 1회 또는 캐시) → routing(필드 타입별 분기:
   A→마킹감지, B→룰엔진, SHADE→색상인식, C→LLM) → 스코어링 → 분기 → DB 저장.
   각 단계 진입 시 orders.status 갱신.

2. 필드 타입 분류는 템플릿 정의(dental_lab_request_ocr_layout_v1_1_0.json)의
   field_type 매핑 기반 — 분류 자체에 추론 로직 넣지 않는다.

3. 상태 폴링 API:
   - GET /api/orders/{id} — 상태 + 필드별 결과
   - GET /api/orders?status=needs_review&lab_id= — 검토 큐 (신뢰도 낮은 순 정렬)

4. 실패 격리: 한 필드의 처리 실패가 의뢰서 전체를 중단시키지 않도록 필드 단위 try/except,
   실패 필드는 forced_hitl 처리. 단, CLOVA 호출 실패는 의뢰서 전체 ocr_failed.

5. 구조화 로깅(structlog): order_id, 단계, 소요시간, LLM 호출 수.

테스트: 전체 파이프라인 e2e (Mock OCR + Mock LLM), 상태 전이 순서, 필드 실패 격리.
완료 기준: 단일 의뢰서가 업로드부터 auto_confirmed/needs_review까지 자동 진행.
```

---

## Step 9 — HITL 검토 UI (Next.js)

브랜치: `feat/#10-hitl-review-ui`

```
HITL 검토 화면을 Next.js로 구현해줘.

1. 검토 큐 페이지 (/review):
   - needs_review 의뢰서 목록, 신뢰도 낮은 순 정렬, TanStack Query 폴링(WebSocket 금지 — Phase 1).

2. 검토 상세 (/review/[orderId]):
   - 좌측: 원본 이미지 + 필드 bbox 하이라이트 오버레이 (R2 presigned URL).
   - 우측: 필드 폼. 신뢰도 색상 코딩 — 녹(≥0.90) / 황(0.60~0.90) / 적(<0.60).
   - needs_review 필드만 편집 가능, confirmed 필드는 읽기 전용 표시.
   - 필드 클릭 ↔ bbox 하이라이트 상호 연동.
   - 인라인 수정 + 필수값 검증: 필수 필드 누락 시 저장 거부 (REQ-002).

3. 확정 API: PATCH /api/orders/{id}/confirm
   - 수정된 필드 → corrected_value 갱신, corrected_by=human, field_audit_log 기록.
   - 수정 발생 필드는 training_labels 자동 INSERT (raw, corrected, field_type, lab_id, corrected_by).
   - 전 필드 검증 통과 시 orders.status = confirmed.

4. ocr_failed 의뢰서: 수동 재시도 버튼 노출.

완료 기준: Mock 데이터로 검토→수정→확정 전체 플로우 동작, REQ-002 검증 동작,
training_labels 적재가 e2e 테스트로 확인될 것.
```

---

## Step 10 — 정확도 계측 & 파일럿 대시보드

브랜치: `feat/#11-accuracy-metrics`

```
파일럿 정확도 70% 목표 측정을 위한 계측을 구현해줘.

1. 정확도 정의: 자동값(스코어링 직후 corrected_value) == 최종 확정값 비율, 필드별 집계.
2. GET /api/metrics/accuracy?lab_id=&from=&to= —
   필드별/필드타입별(A·B·C·SHADE) 정확도, 자동확정률, HITL 수정률, LLM 호출률, 평균 처리 시간.
3. 간단한 대시보드 페이지 (/metrics): 필드별 정확도 테이블 + 추이.
4. score_components 기반 분석 쿼리: 어떤 구성요소(ocr_conf/rule_pass/dict_match)가
   오답에 기여했는지 — 임계값·가중치 튜닝 근거 자료.

완료 기준: 시드 데이터로 정확도 집계 검증, 70% 목표 대비 현황이 한 화면에서 확인 가능.
```

---

## Step 11 — 배포 & 통합 점검

브랜치: `release/v0.1.0`

```
Phase 1 파일럿 배포를 준비해줘.

1. Backend → Railway: Dockerfile, 환경변수 문서화, /health 기반 헬스체크.
2. Frontend → Vercel: 환경 분리(preview/production), API URL 환경변수.
3. NEON Postgres 마이그레이션 실행 절차 문서화, R2 버킷 CORS 설정.
4. 통합 점검 체크리스트 작성·실행:
   - 실제 CLOVA 템플릿으로 실의뢰서 5장 e2e
   - 캐시 HIT 동작, CLOVA 장애 시 재시도→ocr_failed→수동 재시도
   - 개인정보 점검: DB 전체에서 환자명 외 개인정보 부재 확인
   - LLM 호출률 25% 내외 확인
5. 운영 런북: 장애 유형별 대응(CLOVA 실패, R2/DB 장애, LLM 파싱 실패).

완료 기준: 파일럿 기공소 1곳 온보딩 가능한 상태. develop → release → main 병합.
```

---

## 부록 — 프롬프트 사용 팁

1. **한 단계 = 한 세션.** 컨텍스트가 길어지면 품질이 떨어지므로, 단계마다 새 세션에서 공통 컨텍스트 블록 + 해당 단계 프롬프트로 시작한다.
2. **완료 기준을 먼저 테스트로 작성하게 시키기.** "테스트부터 작성하고 구현해줘"를 붙이면 분기 누락이 줄어든다.
3. **설계 변경이 필요해 보이면 멈추게 하기.** 각 프롬프트 끝에 "아키텍처 v2.0 원칙과 충돌하는 결정이 필요하면 구현하지 말고 먼저 보고해줘"를 추가하면 임의 변경을 막을 수 있다.
4. **Step 4의 도메인 사전은 코드보다 데이터가 핵심.** 초기 YAML은 파일럿 기공소의 실제 의뢰서 용어로 채워야 하므로, 구현 후 별도 세션에서 사전 구축 작업을 진행한다.
5. 의존성 순서: 0 → 1 → (2, 3 병렬 가능) → (4, 5, 6 병렬 가능) → 7 → 8 → 9 → 10 → 11.
