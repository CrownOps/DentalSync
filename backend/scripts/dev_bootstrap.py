"""로컬 개발 부트스트랩 — SQLite 등 로컬 DB 에 테이블 생성 + 기본 Lab 시드.

운영(NEON Postgres) 스키마는 Alembic 마이그레이션으로만 관리한다.
이 스크립트는 외부 의존 없는 로컬 개발(.env 의 DATABASE_URL=sqlite...)
환경에서 프론트-백엔드 연동을 바로 돌려보기 위한 용도이며,
environment=local 이 아니면 실행을 거부한다.

사용법 (backend/ 에서):
    python -m scripts.dev_bootstrap
"""

from __future__ import annotations

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Lab  # noqa: F401 — 메타데이터 등록
from app.db.session import get_engine, get_session_factory


def main() -> None:
    settings = get_settings()
    if settings.environment != "local":
        raise SystemExit(
            f"environment={settings.environment!r} — 로컬 전용 스크립트입니다. "
            "운영 DB 는 Alembic 마이그레이션을 사용하세요."
        )

    engine = get_engine()
    Base.metadata.create_all(engine)

    with get_session_factory()() as session:
        lab = session.get(Lab, 1)
        if lab is None:
            session.add(Lab(name="로컬 개발 기공소"))
            session.commit()
            print("Lab(id=1, name='로컬 개발 기공소') 시드 완료")
        else:
            print(f"Lab(id=1, name={lab.name!r}) 이미 존재 — 시드 생략")

    print(f"테이블 생성 완료: {settings.database_url}")


if __name__ == "__main__":
    main()
