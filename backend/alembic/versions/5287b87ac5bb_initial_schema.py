"""initial schema

Revision ID: 5287b87ac5bb
Revises:
Create Date: 2026-06-10 21:07:32.722416

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5287b87ac5bb"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# enum 타입은 상단에서 1회만 생성한다(컬럼에서는 create_type=False 로 참조).
# field_type / corrected_by 는 두 테이블이 공유하므로 중복 CREATE TYPE 를 피해야 한다.
order_status = postgresql.ENUM(
    "uploaded", "preprocessing", "ocr_running", "routing",
    "needs_review", "auto_confirmed", "confirmed", "ocr_failed",
    name="order_status", create_type=False,
)
user_role = postgresql.ENUM("owner", "staff", name="user_role", create_type=False)
field_type = postgresql.ENUM("A", "B", "C", "SHADE", name="field_type", create_type=False)
corrected_by = postgresql.ENUM("system", "llm", "human", name="corrected_by", create_type=False)
field_status = postgresql.ENUM("confirmed", "needs_review", name="field_status", create_type=False)

_ENUMS = (order_status, user_role, field_type, corrected_by, field_status)
_JSONB = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in _ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "labs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("template_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_labs")),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lab_id", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=512), nullable=False),
        sa.Column("image_hash", sa.String(length=64), nullable=False),
        sa.Column("status", order_status, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lab_id"], ["labs.id"],
                                name=op.f("fk_orders_lab_id_labs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
    )
    op.create_index(op.f("ix_orders_image_hash"), "orders", ["image_hash"], unique=False)
    op.create_index(op.f("ix_orders_lab_id"), "orders", ["lab_id"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lab_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lab_id"], ["labs.id"],
                                name=op.f("fk_users_lab_id_labs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_lab_id"), "users", ["lab_id"], unique=False)
    op.create_table(
        "order_fields",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("field_key", sa.String(length=64), nullable=False),
        sa.Column("field_type", field_type, nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("raw_bbox", _JSONB, nullable=True),
        sa.Column("raw_ocr_conf", sa.Float(), nullable=True),
        sa.Column("corrected_value", sa.Text(), nullable=True),
        sa.Column("corrected_by", corrected_by, nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("score_components", _JSONB, nullable=True),
        sa.Column("flags", _JSONB, nullable=True),
        sa.Column("status", field_status, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"],
                                name=op.f("fk_order_fields_order_id_orders"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_fields")),
        sa.UniqueConstraint("order_id", "field_key", name="uq_order_fields_order_id_field_key"),
    )
    op.create_index("ix_order_fields_order_id", "order_fields", ["order_id"], unique=False)
    op.create_table(
        "field_audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_field_id", sa.Integer(), nullable=False),
        sa.Column("before", _JSONB, nullable=True),
        sa.Column("after", _JSONB, nullable=True),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_field_id"], ["order_fields.id"],
                                name=op.f("fk_field_audit_log_order_field_id_order_fields"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_field_audit_log")),
    )
    op.create_index(op.f("ix_field_audit_log_order_field_id"), "field_audit_log",
                    ["order_field_id"], unique=False)
    op.create_table(
        "training_labels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_field_id", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("corrected_value", sa.Text(), nullable=False),
        sa.Column("field_type", field_type, nullable=False),
        sa.Column("lab_id", sa.Integer(), nullable=False),
        sa.Column("corrected_by", corrected_by, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lab_id"], ["labs.id"],
                                name=op.f("fk_training_labels_lab_id_labs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_field_id"], ["order_fields.id"],
                                name=op.f("fk_training_labels_order_field_id_order_fields"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_labels")),
    )
    op.create_index(op.f("ix_training_labels_lab_id"), "training_labels", ["lab_id"], unique=False)
    op.create_index(op.f("ix_training_labels_order_field_id"), "training_labels",
                    ["order_field_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_training_labels_order_field_id"), table_name="training_labels")
    op.drop_index(op.f("ix_training_labels_lab_id"), table_name="training_labels")
    op.drop_table("training_labels")
    op.drop_index(op.f("ix_field_audit_log_order_field_id"), table_name="field_audit_log")
    op.drop_table("field_audit_log")
    op.drop_index("ix_order_fields_order_id", table_name="order_fields")
    op.drop_table("order_fields")
    op.drop_index(op.f("ix_users_lab_id"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_orders_lab_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_image_hash"), table_name="orders")
    op.drop_table("orders")
    op.drop_table("labs")

    bind = op.get_bind()
    for enum_type in reversed(_ENUMS):
        enum_type.drop(bind, checkfirst=True)
