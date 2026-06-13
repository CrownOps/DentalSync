"""add error_detail to orders

OCR 실패(status=ocr_failed) 시 사유(CLOVA code/message, 스토리지 오류 등)를
영속화해, 로그 보존기간과 무관하게 사후 원인 추적을 가능케 한다.

Revision ID: b7f4c2a91e8d
Revises: a1c3e9f02d41
Create Date: 2026-06-14

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7f4c2a91e8d"
down_revision: str | None = "a1c3e9f02d41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("error_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "error_detail")
