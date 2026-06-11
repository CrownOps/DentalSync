"""add confidence component columns to order_fields

임계값 튜닝 분석용 — confidence 구성요소(ocr_conf, rule_pass, dict_match)를
JSONB(score_components) 외에 개별 컬럼으로도 보존한다.

Revision ID: a1c3e9f02d41
Revises: 5287b87ac5bb
Create Date: 2026-06-11

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c3e9f02d41"
down_revision: str | None = "5287b87ac5bb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("order_fields", sa.Column("ocr_conf", sa.Float(), nullable=True))
    op.add_column("order_fields", sa.Column("rule_pass", sa.Float(), nullable=True))
    op.add_column("order_fields", sa.Column("dict_match", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("order_fields", "dict_match")
    op.drop_column("order_fields", "rule_pass")
    op.drop_column("order_fields", "ocr_conf")
