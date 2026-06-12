# DentalSync — 문서 인덱스

## 폴더 구조

| 폴더 | 역할 |
|------|------|
| [`design/`](design/) | 설계 문서 — 아키텍처, 레이아웃 정의 |
| [`ops/`](ops/) | 운영 문서 — 수동 검증 시나리오 |
| [`context/`](context/) | 배경 문서 — 인터뷰, 요구사항, AI 인수인계 (구현 전 산출물) |
| [`adr/`](adr/) | Architecture Decision Records |

---

## 빠른 참조

### 현행 문서

| 문서 | 설명 |
|------|------|
| [`../README.md`](../README.md) | 프로젝트 개요, 빠른 시작, API 명세, DB/마이그레이션 |
| [`../HANDOVER.md`](../HANDOVER.md) | Phase 1 구현 인수인계 (코드 구조, API, 환경변수, Phase 2 예정) |
| [`design/OCR_시스템_아키텍처_v3.md`](design/OCR_시스템_아키텍처_v3.md) | OCR 파이프라인 설계 (v3 · 현행 기준) |
| [`design/dental_lab_request_ocr_layout_v1_1_0.json`](design/dental_lab_request_ocr_layout_v1_1_0.json) | OCR 필드 레이아웃 정의 v1.1.0 |
| [`ops/MANUAL_VERIFICATION_HITL.md`](ops/MANUAL_VERIFICATION_HITL.md) | HITL 검토 수동 검증 시나리오 (PR #15 기준) |
| [`adr/0001-llm-vendor-openai.md`](adr/0001-llm-vendor-openai.md) | LLM 벤더 OpenAI 전환 결정 |
| [`adr/0002-hitl-review-api-v1.md`](adr/0002-hitl-review-api-v1.md) | HITL API v1 설계 결정 |

### 배경 문서 (구현 전 산출물 · context/)

| 문서 | 설명 |
|------|------|
| [`context/AI_HANDOFF.md`](context/AI_HANDOFF.md) | 최상위 인수인계 — 읽는 순서 안내 |
| [`context/PROJECT_CONTEXT.md`](context/PROJECT_CONTEXT.md) | 문제정의, MVP 방향, 경쟁 포지셔닝 |
| [`context/REQUIREMENTS_CONTEXT.md`](context/REQUIREMENTS_CONTEXT.md) | 기능 목록, 역할, 요구사항 작성 기준 |
| [`context/INTERVIEW_INSIGHTS.md`](context/INTERVIEW_INSIGHTS.md) | 치과/기공소/교수/경쟁사 인터뷰 핵심 인사이트 |
| [`context/USER_PREFERENCES.md`](context/USER_PREFERENCES.md) | AI 협업 시 답변 스타일·선호 |
| [`context/DentalSync_개발_프롬프트_단계별.md`](context/DentalSync_개발_프롬프트_단계별.md) | Phase 1 단계별 개발 프롬프트 이력 (v2.0 기반) |
| [`context/[GIT] 코드_컨벤션.pdf`](<context/[GIT] 코드_컨벤션.pdf>) | Git 코드 컨벤션 원본 (PDF) |
| [`context/[OCR] 기술_스택.pdf`](<context/[OCR] 기술_스택.pdf>) | 기술 스택 원본 (PDF) |
