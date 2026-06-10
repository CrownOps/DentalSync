"""도메인 enum 정의 (DB enum 타입과 1:1)."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """사용자 역할 — RBAC 세분화는 Phase 2, 현재는 owner/staff 만."""

    owner = "owner"
    staff = "staff"


class OrderStatus(StrEnum):
    """의뢰서 처리 상태."""

    uploaded = "uploaded"
    preprocessing = "preprocessing"
    ocr_running = "ocr_running"
    routing = "routing"
    needs_review = "needs_review"
    auto_confirmed = "auto_confirmed"
    confirmed = "confirmed"
    ocr_failed = "ocr_failed"


class FieldType(StrEnum):
    """스마트 라우팅 타입 — A(체크박스)/B(정규식)/C(자유텍스트)/SHADE(색상)."""

    A = "A"
    B = "B"
    C = "C"
    SHADE = "SHADE"


class CorrectedBy(StrEnum):
    """보정 주체 — 시스템 룰 / LLM / 사람(HITL)."""

    system = "system"
    llm = "llm"
    human = "human"


class FieldStatus(StrEnum):
    """필드 단위 확정 상태."""

    confirmed = "confirmed"
    needs_review = "needs_review"
