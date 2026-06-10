# DentalSync OCR Backend — Phase 1 MVP

## 프로젝트 개요
치과기공소 의뢰서 OCR 파이프라인. 이미지 업로드 → CLOVA OCR → 
3단계 스마트 라우팅(Type A/B/C) → 신뢰도 스코어링 → HITL 분기 → DB 저장.

## 기술 스택 (변경 금지)
- Python 3.11+, FastAPI, SQLAlchemy 2.0 + Alembic
- DB: NEON Postgres (serverless) / Storage: Cloudflare R2 (boto3, S3 호환)
- 이미지: Pillow(Shade 색상), OpenCV(체크박스/마킹 감지)
- 캐시: upstash-redis (이미지 해시 캐시 TTL 7일) / 큐: QStash
- OCR: Naver CLOVA OCR (Template Basic) — 의뢰서당 1회 호출
- LLM: Claude Haiku 4.5 (Type C 자유텍스트), Sonnet (불명확+HITL)
- 배포: Railway (Dockerfile 없이 자동 감지)

## 스마트 라우팅 규칙 (v5, LLM 호출률 ~25%)
- Type A (체크박스/마킹 ~40%): OpenCV 색상 감지 룰로 확정, LLM 0회
- Type B (날짜/치아번호 ~30%): CLOVA + 정규식으로 확정, LLM 0회
- Shade (~5%): PIL 색상 인식으로 확정, LLM 0회
- Type C 자유텍스트 (~20%): CLOVA + Haiku 1회
- Type C 불명확 (~5%): Sonnet 1회 + HITL 강제

## DB 저장 4종 (모든 필드에 대해)
raw OCR 출력 / 보정값 / 신뢰도 점수 / 플래그(HITL 여부)
사용자가 HITL에서 수정한 값은 (raw, corrected) 쌍으로 학습셋 테이블에 자동 적재.

## 코드 컨벤션
- 브랜치: Git Flow. develop에서 feat/#이슈번호-작업명 분기 (소문자, 하이픈)
- 커밋: <타입>: <메시지> (feat/fix/refactor/chore/style)
- 환경변수는 pydantic-settings로 관리, .env.example 항상 동기화
- 모든 API는 비동기(async def), 타입힌트 필수
- 환자 개인정보 최소수집: 환자명 외 주민번호/전화번호 저장 금지

## 작업 규칙
- 작업 시작 전 계획을 먼저 제시하고 승인받을 것
- 마이그레이션은 Alembic으로만 생성
- 외부 API(CLOVA, LLM)는 인터페이스 추상화 + mock 가능하게 작성