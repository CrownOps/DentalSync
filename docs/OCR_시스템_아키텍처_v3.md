# DentalSync — OCR 시스템 아키텍처 v3

작성일: 2026-06-11 · 기준: 기술 스택 v5 (템플릿 기반 비용최적화) + Step 0 스캐폴드 결정
대상: 기공의뢰서 OCR Phase 1 MVP (2~3주) + 파일럿(1기공소) → 10기공소 확장

> 본 문서는 v2(26.06.10)를 대체한다. v3의 핵심 변경은 **Type C 구조화 LLM의 벤더를 Anthropic에서 OpenAI로 전환**한 것이며, 파이프라인 구조·신뢰도 체계·HITL 플로우는 v2와 동일하다. 상세 결정 기록은 저장소 `docs/adr/0001-llm-vendor-openai.md` 참조.

---

## 0. 확정 설계 원칙

| # | 원칙 | 설명 |
|---|------|------|
| 1 | OCR 엔진은 CLOVA OCR 단일 | 의뢰서당 1회 호출 (Template Basic). 멀티모달 LLM의 이미지 직접 추출은 사용하지 않는다. |
| 2 | LLM 역할은 텍스트 구조화로 한정 | Type C 자유텍스트의 text→JSON 변환 및 불명확 케이스 처리만 담당한다. |
| 3 | 스마트 라우팅으로 LLM 호출률 ~25% 유지 | 필드 타입별 결정론적 처리 우선, LLM은 최후 수단. |
| 4 | 신뢰도 지표는 단일 복합 점수 하나만 사용 | 임계값은 2개만 둔다 (일반 0.90 / 치명 0.95). |
| 5 | 모든 필드는 4종 데이터로 저장 | raw OCR 출력 · 보정값 · 신뢰도 점수 · 플래그. |
| 6 | HITL 수정값은 학습셋으로 자동 적재 | (raw, corrected) 쌍 누적 → 자체 모델 전환의 기반. |
| 7 | 개인정보 최소수집 | 환자명 외 주민번호·전화번호 저장 금지. 학습 데이터는 익명화 후 적재. |
| 8 | OCR 엔진은 인터페이스로 추상화 | CLOVA → 자체 모델 전환 시 교체 가능한 구조 (OCREngine 인터페이스). |
| 9 | **(v3 신설) LLM 클라이언트도 인터페이스로 추상화** | LLMStructurer Protocol. 벤더(OpenAI ↔ Anthropic ↔ 기타) 교체 시 승급 체인 로직·DB 스키마 무변. 모델명은 설정으로 외부화 (`LLM_MODEL_PRIMARY` / `LLM_MODEL_ESCALATION`), 코드 하드코딩 금지. |

---

## 1. 전체 파이프라인 (Phase 1)

```
의뢰서 입력 (종이 촬영 · 스캔 · 팩스 PDF)
  → 전처리 (기울기 보정 · 노이즈 제거 · 리사이즈 / 품질 미달 시 반려·재촬영 안내)
  → R2 저장 + 이미지 해시 계산
  → 해시 캐시 조회 (Upstash Redis, TTL 7일)
       ├─ HIT  → 캐시된 OCR 결과 재사용 (CLOVA 호출 생략)
       └─ MISS → CLOVA OCR (Template) — 필드별 텍스트 · bbox · confidence
  → 필드 타입 분류 (템플릿 정의 기반)
       ├─ Type A — 체크박스/마킹 (~40%) : OpenCV 색상·마킹 감지 — LLM 0회
       ├─ Type B — 날짜/치식/납기 (~30%) : 정규식 + 도메인 사전 보정 — LLM 0회
       ├─ Shade — 시각 도형 (~5%) : PIL 색상 인식 → VITA 코드 — LLM 0회
       └─ Type C — 자유텍스트 (~20%) : 경량 LLM text→JSON (Structured Outputs) — LLM 1회
              └─ 구조화 실패/불명확 (~5%) : 상위 모델 승급 + HITL 강제 플래그 — LLM 1회
  → 복합 신뢰도 점수 산출 (필드별)
  → 분기 (§2.2 임계값)
       ├─ 전 필드 score ≥ 임계값 → 자동 확정 (status: auto_confirmed)
       └─ 하나라도 미달 또는 HITL 강제 → 검토 큐 (status: needs_review)
  → HITL 검토 UI (원본 bbox 하이라이트 · 신뢰도 색상 · 인라인 수정)
  → 사용자 확정 → DB 저장 (4종: raw · 보정값 · 신뢰도 · 플래그)
  → 수정 발생 시 training_labels 자동 적재 (raw, corrected, field_type, lab_id)
```

### 처리 방식 요약 (v5 스마트 라우팅)

| 라우트 | 비중 | 처리 방식 | LLM 호출 |
|--------|------|-----------|----------|
| Type A — 체크박스/마킹 | ~40% | OpenCV 색상·마킹 감지 룰로 확정 | 0회 |
| Type B — 날짜/치아번호 | ~30% | CLOVA + 정규식 + 도메인 사전 | 0회 |
| Shade — 시각 도형 | ~5% | PIL 색상 인식 → VITA 코드 매핑 | 0회 |
| Type C — 자유텍스트 | ~20% | CLOVA + 경량 모델 text→JSON (기본 `gpt-5-mini`, Structured Outputs strict) | 1회 |
| Type C — 불명확 | ~5% | 상위 모델 승급 (기본 `gpt-5`) + HITL 강제 | 1회 |
| **합계 LLM 호출률** | | | **~25%** |

---

## 2. 신뢰도 스코어링 (단일 지표)

모든 분기는 아래 복합 신뢰도 점수 하나로만 판단한다.

### 2.1 복합 신뢰도 점수 (필드별, 0.0~1.0)

```
score = w1 · ocr_conf + w2 · rule_pass + w3 · dict_match

  ocr_conf  : CLOVA inferConfidence (0~1)
  rule_pass : 타입별 룰 검증 통과 여부 (통과 1.0 / 부분 0.5 / 실패 0.0)
              - Type A: 마킹 감지 명확도 (단일 마킹=1.0, 복수/모호=0.0)
              - Type B: 정규식 매칭 (FDI 11~48 범위, 날짜 유효성, 납기≥접수일)
              - Type C: Structured Outputs 스키마 검증 + pydantic 2차 검증
                        + LLM 자기보고 confidence
  dict_match: 도메인 사전 매칭 (정확 1.0 / 유사 보정 0.7 / 미매칭 0.3)
              - 해당 없는 필드(환자명 등)는 이 항 제외 후 가중치 재정규화

초기 가중치: w1=0.5, w2=0.3, w3=0.2 (파일럿 데이터로 보정)
```

### 2.2 임계값 — 2개만

| 조건 | 분기 | 상태 |
|------|------|------|
| 필드 score ≥ 0.90 | 해당 필드 자동 확정 | `confirmed` |
| 필드 score < 0.90 | 해당 필드 검토 대상 | `needs_review` |
| 상위 모델 승급 필드 | 점수 무관 HITL 강제 | `needs_review` (forced) |

- 의뢰서 단위 상태: 전 필드 confirmed → `auto_confirmed` / 하나라도 needs_review → 검토 큐 진입.
- 치명 필드 가중 규칙: 쉐이드 · 치식 · 납기는 오인식 비용이 크므로 임계값을 **0.95**로 상향 적용한다.
- **(v3 구체화)** 가중치 · 임계값 · 치명 필드 목록은 `config/scoring.yaml`로 외부화한다. 치명 필드 키는 레이아웃 정의(`dental_lab_request_ocr_layout` v1.1.0)의 field_key를 따른다. 파일럿 정확도 데이터 누적 후 재조정한다.

```yaml
# config/scoring.yaml
weights: { ocr_conf: 0.5, rule_pass: 0.3, dict_match: 0.2 }
thresholds: { general: 0.90, critical: 0.95 }
critical_fields: [shade, tooth_number, due_date]  # field_key는 레이아웃 정의 기준
```

### 2.3 분기 다이어그램

```
필드별 복합 점수 → score ≥ 임계값? (일반 0.90 / 치명 0.95)
    ├─ 예  → 자동 확정 ──────────────┐
    └─ 아니오 → HITL 검토 ← 상위 모델  │
               승급 필드(점수 무관)     │
               → 사람 수정·확정 ───────┤
                  └─ 수정 시 학습 라벨 적재
                                      ↓
                                  DB 저장
```

---

## 3. HITL 검토 플로우

```
검토 큐 (신뢰도 낮은 순 정렬)
→ 검토 상세: 좌측 원본 이미지(bbox 하이라이트) ‖ 우측 필드 폼
  - 신뢰도 색상 코딩: 녹(≥0.90) · 황(0.60~0.90) · 적(<0.60)
→ 인라인 수정 (필수값 검증: 누락 시 저장 거부 — REQ-002)
→ 확정 → DB 저장 + 변경 이력 기록
→ 수정 발생 필드: training_labels 자동 INSERT
```

| 항목 | 내용 |
|------|------|
| 검토 대상 | needs_review 의뢰서의 플래그 필드 (확정 필드는 읽기 전용 표시) |
| 수정 기록 | (raw, corrected, field_type, lab_id, corrected_by, created_at) |
| 확정 권한 | 기공소 소장/직원 (RBAC은 Phase 2에서 세분화) |
| 정확도 계측 | 자동값 == 최종 확정값 비율을 필드별로 집계 → 파일럿 70% 목표 측정 |

---

## 4. 데이터 저장 구조

### 4.1 저장 4종 (order_fields)

| 컬럼 그룹 | 내용 | 용도 |
|-----------|------|------|
| raw | CLOVA 원시 텍스트 + bbox + inferConfidence | 감사 추적, 학습 입력 |
| corrected | 룰/사전/LLM 보정값 또는 사람 수정값 | 업무 사용값 |
| confidence | 복합 신뢰도 점수 + 구성 요소별 점수 | 분기 근거, 임계값 튜닝 |
| flags | field_type(A/B/C/Shade), needs_review, forced_hitl, **model_escalated**, corrected_by_human | 라우팅·검토 상태 |

> **(v3 변경)** 플래그 `sonnet_escalated` → `model_escalated`로 개명. 특정 벤더 모델명을 DB 스키마에 박지 않는다 — 원칙 9(LLM 추상화)와 동일 논리.

### 4.2 학습 라벨 (training_labels)

```
order_field_id · raw_value · corrected_value · field_type
lab_id · corrected_by · created_at
※ 적재 시 환자 식별정보 제거(익명화) 후 저장
```

---

## 5. 학습 루프 — 중앙 수집 + 기공소별 Personal Layer

> 실제 구조는 **"동의 기반 중앙 수집 + 익명화 + 기공소별 personal layer 파인튜닝"**이다.
> (진성 federated learning — 데이터 로컬 유지, 가중치만 전송 — 은 기공소 측 학습 클라이언트가 필요하므로 자체 모델 전환 이후 장기 과제로 분리한다.)

```
DB 저장 (raw · 보정값 · 신뢰도 · 플래그)
  → 학습 데이터 누적 (수정 이력 · 오인식 패턴 · 익명화 처리)
  → 글로벌 모델 재학습 (전체 기공소 익명화 데이터)
     + Personal Layer 파인튜닝 (기공소별 글씨체 · 약어 적응)
  → 정확도 향상 → 검토 빈도 감소 → 사용자 부담 감소
  → (재학습 사이클 반복)
```

### 데이터 프라이버시 원칙

| 항목 | 처리 |
|------|------|
| 수집 동의 | 기공소 단위 동의 기반. 글로벌 모델 기여 여부 opt-in/out 제공 |
| 익명화 | 학습 적재 전 환자 식별정보 제거 |
| 치명 필드 | 쉐이드 · 치식 · 납기 — 오인식 주의 필드로 임계값 상향(0.95) |
| 기공소 간 격리 | personal layer는 해당 기공소에만 적용, 교차 공유 금지 |

### Phase별 전환 로드맵

| Phase | OCR 엔진 | 학습 |
|-------|----------|------|
| 1 (현재) | CLOVA API | 라벨 누적만 (학습 미수행) |
| 2 | CLOVA API | 도메인 사전 자동 확장, 임계값 튜닝, 템플릿 분류기 (YOLO+CLIP) |
| 3 | 자체 모델 (OCREngine 교체) | 글로벌 모델 + personal layer 파인튜닝 |

---

## 6. 인프라 배치 (기술 스택 v5 정합)

```
[Next.js 15 / Vercel] ── 업로드 · 검토 UI (PWA는 Phase 2)
        │ HTTPS
[FastAPI / Railway]  (Python 3.12 · uv)
        ├─ Cloudflare R2 ──── 원본 이미지 (Egress $0)
        ├─ NEON Postgres ──── orders · order_fields · training_labels · labs · users
        ├─ Upstash Redis ──── 이미지 해시 캐시 (TTL 7일)
        ├─ CLOVA OCR API ──── 의뢰서당 1회
        └─ OpenAI API ─────── Type C 구조화: LLM_MODEL_PRIMARY (기본 gpt-5-mini)
                              불명확 승급: LLM_MODEL_ESCALATION (기본 gpt-5)
                              Structured Outputs (json_schema, strict: true)
```

**(v3 추가) 환경 설정 정합** — Redis 접속은 `REDIS_URL` 단일 변수로 통일한다 (로컬 `redis://localhost:6379`, 프로덕션은 Upstash의 `rediss://` 프로토콜 URL). Upstash REST API는 사용하지 않는다 — 로컬/프로덕션 패리티 유지. LLM 모델명 기본값(gpt-5-mini / gpt-5)은 잠정값으로, 구현 시점 OpenAI 라인업·가격 확인 후 설정 변경만으로 확정한다.

### 비동기 처리 — Phase 1 결정

| Phase | 방식 | 근거 |
|-------|------|------|
| 1 (1기공소, ~20건/일) | FastAPI BackgroundTasks + 상태 폴링 | QStash 무료 한도(500 msg/월)는 월 ~500건 + 재시도로 초과 확실. 1기공소 트래픽은 인프로세스로 충분 |
| 2 (10기공소 확장) | QStash 도입 (유료) | 재시도 · DLQ · 콜백 필요 시점 |

> 작업 상태 전이: `uploaded → preprocessing → ocr_running → routing → needs_review | auto_confirmed → confirmed`
> 프론트는 상태 폴링(TanStack Query)으로 추적. Phase 1에서 WebSocket 불필요.

---

## 7. 실패 처리 정책

| 실패 지점 | 정책 |
|-----------|------|
| CLOVA 호출 실패 | 지수 백오프 3회 재시도 → 최종 실패 시 status `ocr_failed`, 수동 재시도 버튼 노출 |
| LLM 구조화 실패 (스키마/pydantic 검증 실패 또는 refusal) | 경량 모델 1회 재시도 → 실패 시 **상위 모델 승급** (`model_escalated`) + HITL 강제 → 그래도 실패 시 해당 필드 raw만 저장하고 HITL 강제 |
| 치식 범위 밖 값 (FDI 11~48 외) | rule_pass=0 → 사실상 HITL 직행 |
| 이미지 품질 불량 (해상도/블러 임계 미달) | 전처리 단계에서 반려, 재촬영 안내 |
| R2/DB 장애 | 업로드 자체 실패 응답, 부분 저장 금지 (트랜잭션 단위: 의뢰서) |

> **(v3 참고)** v2의 "LLM JSON 파싱 실패"는 OpenAI Structured Outputs(strict) 도입으로 발생 빈도가 구조적으로 낮아진다. 다만 strict 모드도 refusal 응답·빈 값·도메인 제약 위반은 막지 못하므로 pydantic 2차 검증과 승급 체인은 유지한다.

---

## 8. v2 → v3 변경 요약

| # | 변경 | 사유 |
|---|------|------|
| 1 | Type C LLM 벤더: Anthropic (Haiku/Sonnet) → OpenAI (경량/상위 모델, 설정 외부화) | 손글씨 후처리 벤치마크 우위 + Structured Outputs strict 모드의 스키마 강제. ADR-0001 |
| 2 | LLM 클라이언트 인터페이스 추상화를 설계 원칙 9로 신설 | 벤더 재교체 가능성 대비. OCREngine 추상화(원칙 8)와 동일 논리 |
| 3 | 플래그 `sonnet_escalated` → `model_escalated` 개명 | 벤더 종속 명칭의 DB 스키마 유입 차단 |
| 4 | 출력 검증 2단 방어 명문화: Structured Outputs(1차) + pydantic(2차) | refusal·빈 값·도메인 제약 위반은 strict 모드로 차단 불가 |
| 5 | scoring.yaml 외부화 범위에 치명 필드 목록 포함, field_key는 레이아웃 정의 기준 명시 | 치명 임계값 0.95의 무음 미적용 버그 방지 |
| 6 | Redis 접속 `REDIS_URL` 단일 변수 (rediss:// 프로토콜), Upstash REST 미사용 | 로컬/프로덕션 패리티 |
| 7 | LLM 모델 기본값을 잠정값으로 명시, 확정은 설정 변경으로만 | 모델 라인업 변동 대응, 코드 무변 보장 |

### 검증 필요 항목 (파일럿에서 확인)

- JSON 포맷 일관성은 기존 벤치마크에서 Claude 우위였음. Structured Outputs strict 모드가 그 격차를 상쇄하는지 Type C 필드 정확도로 측정한다 — 미달 시 LLMStructurer 인터페이스를 통해 벤더 재전환 가능 (원칙 9).

---

## 변경 이력

| 버전 | 일자 | 편집자 | 내용 |
|------|------|--------|------|
| v1 | 26.06.07 | 신은지 | OCR 및 전체 MVP 구성 아키텍처 작성 |
| v2 | 26.06.10 | 신은지 | 문서 검토 반영 — 구버전 파이프라인 폐기, 신뢰도 단일화, 라우팅 명시, 학습 루프 용어 정정, 비동기 처리 결정 |
| v3 | 26.06.11 | 신은지 | LLM 벤더 OpenAI 전환 (ADR-0001), LLM 추상화 원칙 신설, 플래그 중립화, 검증 2단 방어, scoring.yaml 범위 확정, Redis 설정 통일 |
