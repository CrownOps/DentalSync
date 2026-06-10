# DentalSync

치과기공소 의뢰서 OCR 파이프라인 — 모노레포 (Step 0 스캐폴드).

> Step 0 의 목표는 기능 구현이 아니라 **구조 · 설정 · `/health` · CI 통과 가능성**이다.
> OCR 라우팅/스코어링/파이프라인 등 실제 기능은 이후 단계에서 이 골격 위에 구현한다.

## 구조

```
.
├── backend/                FastAPI (Python 3.12, uv)
│   ├── app/
│   │   ├── api/            라우터 (현재: /health)
│   │   ├── services/       유스케이스 (이후 단계)
│   │   ├── domain/         도메인 모델 (예: ScoringConfig)
│   │   ├── infra/          외부 서비스 어댑터 (이후 단계)
│   │   ├── core/           설정(pydantic-settings), 스코어링 로더
│   │   └── db/             DB 세션 인프라
│   ├── config/scoring.yaml 신뢰도 가중치/임계값 (외부화)
│   └── tests/              pytest + httpx
├── frontend/               Next.js 15 (App Router, TS, Tailwind, TanStack Query)
│   └── app/                / 화면에서 backend /health 연동 스모크
├── docker-compose.dev.yml  Postgres + Redis (로컬 개발)
└── .env.example            필요한 환경변수 전체 목록
```

## 사전 준비

- [uv](https://docs.astral.sh/uv/) (백엔드 Python/의존성 관리)
- Node.js 20+ / npm
- Docker (로컬 Postgres/Redis)

## 빠른 시작

```bash
# 0) 환경변수
cp .env.example backend/.env
# (선택) 프론트 전용 값
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > frontend/.env.local

# 1) 로컬 인프라
docker compose -f docker-compose.dev.yml up -d

# 2) backend
cd backend
uv sync --dev
uv run uvicorn app.main:app --reload --port 8000
#  → http://localhost:8000/health  ⇒ {"status":"ok"}

# 3) frontend (다른 터미널)
cd frontend
npm install
npm run dev
#  → http://localhost:3000  (브라우저가 backend /health 호출, CORS 허용됨)
```

## 검증

```bash
# backend
cd backend
uv run ruff check .
uv run mypy app tests
uv run pytest

# frontend
cd frontend
npm run build
```

## 설정 (config/scoring.yaml)

신뢰도 스코어는 `score = 0.5·ocr_conf + 0.3·rule_pass + 0.2·dict_match` 로 계산하며,
가중치/임계값은 코드가 아닌 `backend/config/scoring.yaml` 에서 관리한다.

| 항목 | 값 |
| --- | --- |
| weights | ocr_conf 0.5 / rule_pass 0.3 / dict_match 0.2 (합 1.0) |
| thresholds | general 0.90 / critical 0.95 |
| critical_fields | shade, tooth_numbers, due_date |

로더(`app/core/scoring.py`)는 가중치 합이 1.0 인지, threshold 필수 키가 있는지 검증한다.
