"""기공소 계정 — 회원가입 / 로그인 인증.

Phase 1 인증 깊이: 코드+비밀번호를 검증해 Lab(내부 PK 포함)을 식별하는 수준이며,
세션/JWT 는 발급하지 않는다. API 게이트는 별도 ``require_auth``(앱 단위 토큰)가 담당한다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Lab
from app.domain.errors import DuplicateLabCodeError
from app.services.auth import hash_password, verify_password


def signup_lab(session: Session, *, name: str, code: str, password: str) -> Lab:
    """신규 기공소 등록. code 중복 시 DuplicateLabCodeError."""
    code = code.strip()
    existing = session.scalar(select(Lab).where(Lab.code == code))
    if existing is not None:
        raise DuplicateLabCodeError(code)

    lab = Lab(name=name.strip(), code=code, password_hash=hash_password(password))
    session.add(lab)
    session.commit()
    session.refresh(lab)
    return lab


def authenticate_lab(session: Session, *, code: str, password: str) -> Lab | None:
    """코드+비밀번호 검증. 성공 시 Lab, 실패 시 None."""
    lab = session.scalar(select(Lab).where(Lab.code == code.strip()))
    if lab is None or not verify_password(password, lab.password_hash):
        return None
    return lab
