"""SQLAlchemy 2.0 ORM 모델 — DentalSync DB 스키마.

개인정보 최소수집 원칙: 환자명(필드 데이터로만 보관) 외 주민번호/전화번호 등
개인정보 컬럼은 만들지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin
from app.domain.enums import (
    CorrectedBy,
    FieldStatus,
    FieldType,
    OrderStatus,
    UserRole,
)

# Postgres 는 JSONB, sqlite(테스트)는 JSON 으로 폴백
JSONB_VARIANT = JSONB().with_variant(JSON(), "sqlite")

# 여러 컬럼이 공유하는 enum 타입은 단일 인스턴스를 재사용해야 Postgres 에서
# CREATE TYPE 가 중복되지 않는다.
USER_ROLE_ENUM = Enum(UserRole, name="user_role")
ORDER_STATUS_ENUM = Enum(OrderStatus, name="order_status")
FIELD_TYPE_ENUM = Enum(FieldType, name="field_type")
CORRECTED_BY_ENUM = Enum(CorrectedBy, name="corrected_by")
FIELD_STATUS_ENUM = Enum(FieldStatus, name="field_status")


class Lab(Base, CreatedAtMixin):
    """기공소."""

    __tablename__ = "labs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_id: Mapped[str | None] = mapped_column(String(128), default=None)

    # 사람이 읽는 로그인 코드 (내부 PK=id 는 코드 동작용으로 유지). 가입/로그인 식별자.
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # 비밀번호 해시만 저장 (평문/해시 응답 금지). pbkdf2_sha256 포맷 — app.services.auth.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="lab")
    orders: Mapped[list[Order]] = relationship(back_populates="lab")


class User(Base, CreatedAtMixin):
    """사용자 (RBAC 세분화는 Phase 2)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("labs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(USER_ROLE_ENUM, nullable=False)

    lab: Mapped[Lab] = relationship(back_populates="users")


class Order(Base, TimestampMixin):
    """의뢰서 — OCR 처리 1건 단위."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("labs.id", ondelete="CASCADE"), index=True)

    image_url: Mapped[str] = mapped_column(String(512), nullable=False)  # R2 객체 키
    image_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    status: Mapped[OrderStatus] = mapped_column(
        ORDER_STATUS_ENUM,
        default=OrderStatus.uploaded,
        nullable=False,
    )

    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    due_date: Mapped[date | None] = mapped_column(Date, default=None)

    lab: Mapped[Lab] = relationship(back_populates="orders")
    fields: Mapped[list[OrderField]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderField(Base):
    """필드별 4종 저장: raw / corrected / score / flags(상태)."""

    __tablename__ = "order_fields"
    __table_args__ = (
        UniqueConstraint("order_id", "field_key", name="uq_order_fields_order_id_field_key"),
        Index("ix_order_fields_order_id", "order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))

    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    field_type: Mapped[FieldType] = mapped_column(FIELD_TYPE_ENUM, nullable=False)

    # --- raw (OCR 원본) ---
    raw_text: Mapped[str | None] = mapped_column(Text, default=None)
    raw_bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB_VARIANT, default=None)
    raw_ocr_conf: Mapped[float | None] = mapped_column(Float, default=None)

    # --- corrected (보정값) ---
    corrected_value: Mapped[str | None] = mapped_column(Text, default=None)
    corrected_by: Mapped[CorrectedBy | None] = mapped_column(CORRECTED_BY_ENUM, default=None)

    # --- score (신뢰도) ---
    score: Mapped[float | None] = mapped_column(Float, default=None)
    score_components: Mapped[dict[str, Any] | None] = mapped_column(JSONB_VARIANT, default=None)
    # 구성요소 개별 컬럼 — 임계값 튜닝 분석 쿼리용 (JSONB 와 이중 기록)
    ocr_conf: Mapped[float | None] = mapped_column(Float, default=None)
    rule_pass: Mapped[float | None] = mapped_column(Float, default=None)
    dict_match: Mapped[float | None] = mapped_column(Float, default=None)

    # --- flags / 상태 ---
    flags: Mapped[dict[str, Any] | None] = mapped_column(JSONB_VARIANT, default=None)
    status: Mapped[FieldStatus] = mapped_column(
        FIELD_STATUS_ENUM,
        default=FieldStatus.needs_review,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    order: Mapped[Order] = relationship(back_populates="fields")


class TrainingLabel(Base, CreatedAtMixin):
    """학습셋 — HITL 등에서 확정된 (raw, corrected) 쌍을 적재."""

    __tablename__ = "training_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_field_id: Mapped[int] = mapped_column(
        ForeignKey("order_fields.id", ondelete="CASCADE"), index=True
    )
    raw_text: Mapped[str | None] = mapped_column(Text, default=None)
    corrected_value: Mapped[str] = mapped_column(Text, nullable=False)
    field_type: Mapped[FieldType] = mapped_column(FIELD_TYPE_ENUM, nullable=False)
    lab_id: Mapped[int] = mapped_column(ForeignKey("labs.id", ondelete="CASCADE"), index=True)
    corrected_by: Mapped[CorrectedBy] = mapped_column(CORRECTED_BY_ENUM, nullable=False)


class FieldAuditLog(Base, CreatedAtMixin):
    """필드 변경 이력."""

    __tablename__ = "field_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_field_id: Mapped[int] = mapped_column(
        ForeignKey("order_fields.id", ondelete="CASCADE"), index=True
    )
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB_VARIANT, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB_VARIANT, default=None)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
