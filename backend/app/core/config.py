"""애플리케이션 설정 — pydantic-settings 로 .env 로드."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 디렉터리 기준 (이 파일: backend/app/core/config.py)
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- 일반 ---
    environment: str = "local"

    # --- CORS (프론트 origin 허용) ---
    cors_origins: str = "http://localhost:3000"

    # --- 데이터 스토어 ---
    database_url: str = "postgresql+psycopg://dentalsync:dentalsync@localhost:5432/dentalsync"
    redis_url: str = "redis://localhost:6379"
    image_cache_ttl_seconds: int = 60 * 60 * 24 * 7  # 이미지 해시 캐시 TTL 7일

    # --- 이미지 업로드 검증 임계값 (외부화) ---
    max_image_bytes: int = 15 * 1024 * 1024  # 15MB
    min_image_width: int = 1000
    min_image_height: int = 1000
    blur_laplacian_min: float = 100.0  # Laplacian variance 가 이 값 미만이면 블러로 반려
    pdf_render_dpi: int = 200  # PDF 1페이지 래스터화 DPI

    # --- 외부 API: Naver CLOVA OCR (Template Basic) ---
    clova_api_key: str = ""
    clova_template_id: str = ""
    clova_ocr_invoke_url: str = ""  # APIGW invoke URL
    clova_ocr_secret: str = ""  # X-OCR-SECRET

    # --- 외부 API: OpenAI — Type C 텍스트 구조화 전용(이미지 입력 금지) ---
    # 모델명 하드코딩 금지: 코드가 아닌 이 설정으로만 모델을 지정한다.
    # 기본값(gpt-5-mini/gpt-5)은 잠정값 — 현 시점 라인업·가격 확인 후 확정 필요.
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model_primary: str = "gpt-5-mini"
    llm_model_escalation: str = "gpt-5"

    # --- Type C 비용 가드 ---
    type_c_design_ratio: float = 0.25  # 설계상 LLM 호출 비중(~25%)
    type_c_ratio_warn_margin: float = 0.15  # 설계치 + 마진 초과 시 경고 로그
    type_c_ratio_min_samples: int = 20  # 경고 판단 최소 표본 수

    # --- Cloudflare R2 (S3 호환 스토리지) ---
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_endpoint: str = ""

    # --- 스코어링 설정 파일 경로 ---
    scoring_config_path: Path = BACKEND_DIR / "config" / "scoring.yaml"

    # --- 도메인 사전 / 유사 매칭 ---
    domain_dict_dir: Path = BACKEND_DIR / "data" / "domain_dict"
    dict_fuzzy_threshold: float = 85.0  # rapidfuzz 점수(0~100) 이상이면 유사 보정 인정

    # --- Type A 마킹 감지 (파일럿 튜닝 대상) ---
    marking_density_marked: float = 0.06  # 잉크 밀도가 이 이상이면 마킹으로 판정
    marking_density_ambiguous: float = 0.025  # [ambiguous, marked) 구간은 모호 → HITL
    marking_color_ratio_marked: float = 0.04  # 빨강/파랑 펜 픽셀 비율 임계
    marking_border_margin: float = 0.18  # 체크박스 테두리 제외 비율(각 변)

    # --- Shade 마킹 감지 (파일럿 튜닝 대상) ---
    shade_mark_ratio: float = 0.03  # 셀 내 펜 마킹 픽셀 비율 임계

    @property
    def cors_origins_list(self) -> list[str]:
        """콤마 구분 문자열 → origin 리스트."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
