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

## API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/health` | 헬스 체크 |
| POST | `/api/orders` | 의뢰서 이미지 업로드 (multipart: `image`, `lab_id`) |
| POST | `/api/orders/{id}/retry-ocr` | OCR 수동 재시도 (실패 시 `ocr_failed`) |

`POST /api/orders` 앞단 파이프라인: 검증(jpg/png/pdf·크기·해상도·블러) → 전처리(deskew/denoise/resize)
→ SHA-256 해시 → Redis 캐시 조회(TTL 7일) → R2 업로드 + `orders` 생성(status `uploaded`).
- 품질 미달 시 **422** + `{error_code, message, guidance}`(재촬영 안내). 블러는 OpenCV Laplacian
  variance 로 측정하며 임계값은 `Settings`(env) 로 외부화(`BLUR_LAPLACIAN_MIN` 등).
- 트랜잭션 단위는 의뢰서 — R2/DB 실패 시 부분 저장 없이 전체 롤백.

### OCR 엔진 (추상화)

`OCREngine` 인터페이스(`app/infra/ocr/base.py`)에 서비스가 의존하고, 구체 엔진은 DI 로 주입한다.
- `CLOVAOCREngine`: CLOVA Template Basic 호출(의뢰서당 1회), 일시적 실패는 tenacity 지수 백오프 3회 재시도,
  최종/파싱 실패는 `orders.status=ocr_failed` 처리 → `POST /api/orders/{id}/retry-ocr` 로 수동 재시도.
- `MockOCREngine`: 테스트/로컬용. `app/infra/ocr/layout_v1_1_0.json` 의 OCR 필드 정의 기반 고정 응답.
- Phase 3 자체 모델 전환 시 이 인터페이스만 구현하면 교체 가능(서비스는 CLOVA 를 직접 import 하지 않음).

## DB / 마이그레이션 (Alembic)

DB 스키마는 SQLAlchemy 2.0 모델(`backend/app/db/models.py`) + Alembic 으로 관리한다.
DB URL 은 `.env` 의 `DATABASE_URL` 을 `alembic/env.py` 가 주입한다.

```bash
docker compose -f docker-compose.dev.yml up -d postgres   # 로컬 Postgres
cd backend
uv run alembic upgrade head        # 최신 스키마 적용
uv run alembic revision --autogenerate -m "변경 설명"   # 모델 변경 후 마이그레이션 생성
uv run alembic check               # 모델↔마이그레이션 드리프트 점검
```

테이블: `labs · users · orders · order_fields · training_labels · field_audit_log`.
- `order_fields` 는 필드별 **4종 저장**(raw / corrected / score / flags·status) + `(order_id, field_key)` unique.
- 개인정보 최소수집: 환자명 외 주민번호/전화번호 등 PII 컬럼은 만들지 않는다.
- 의뢰서 상태 규칙은 `app/services/order_status.py` (전 필드 confirmed → `auto_confirmed`,
  하나라도 needs_review → `needs_review`).

## 설정 (config/scoring.yaml)

신뢰도 스코어는 `score = 0.5·ocr_conf + 0.3·rule_pass + 0.2·dict_match` 로 계산하며,
가중치/임계값은 코드가 아닌 `backend/config/scoring.yaml` 에서 관리한다.

| 항목 | 값 |
| --- | --- |
| weights | ocr_conf 0.5 / rule_pass 0.3 / dict_match 0.2 (합 1.0) |
| thresholds | general 0.90 / critical 0.95 |
| critical_fields | shade, tooth_numbers, due_date |

로더(`app/core/scoring.py`)는 가중치 합이 1.0 인지, threshold 필수 키가 있는지 검증한다.
