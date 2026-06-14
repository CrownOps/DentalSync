"""add login code + password_hash to labs

기공소 회원가입/로그인 — 사람이 읽는 로그인 코드(unique)와 비밀번호 해시 컬럼 추가.
내부 PK(labs.id)는 그대로 코드 동작용 식별자로 유지한다.

기존 행 백필:
- code = 'lab-' || id (유일 보장)
- password_hash = 'disabled' (sentinel — 어떤 평문과도 불일치하여 로그인 불가)
  → 운영 기존 기공소는 코드/비번 재설정 전까지 로그인 불가 (Phase 1 범위 밖, 수동 처리).

Revision ID: c8d2f1a3b4e5
Revises: a1c3e9f02d41
Create Date: 2026-06-14

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d2f1a3b4e5"
down_revision: str | None = "a1c3e9f02d41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) nullable 로 추가 → 기존 행 안전
    op.add_column("labs", sa.Column("code", sa.String(length=64), nullable=True))
    op.add_column(
        "labs", sa.Column("password_hash", sa.String(length=255), nullable=True)
    )

    # 2) 기존 행 백필
    op.execute("UPDATE labs SET code = 'lab-' || id WHERE code IS NULL")
    op.execute("UPDATE labs SET password_hash = 'disabled' WHERE password_hash IS NULL")

    # 3) NOT NULL + unique 제약
    op.alter_column("labs", "code", existing_type=sa.String(length=64), nullable=False)
    op.alter_column(
        "labs", "password_hash", existing_type=sa.String(length=255), nullable=False
    )
    op.create_unique_constraint("uq_labs_code", "labs", ["code"])


def downgrade() -> None:
    op.drop_constraint("uq_labs_code", "labs", type_="unique")
    op.drop_column("labs", "password_hash")
    op.drop_column("labs", "code")
