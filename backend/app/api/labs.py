"""기공소 회원가입 / 로그인 엔드포인트.

기존 orders 라우터와 동일하게 앱 단위 토큰(require_auth) 게이트를 유지한다(폐쇄 베타 전제).
로그인은 lab_id(내부 PK)를 돌려주는 식별 수준 — 세션/JWT 발급은 Phase 2.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_auth
from app.domain.errors import DuplicateLabCodeError
from app.schemas.labs import LabAuthResponse, LabLoginRequest, LabSignupRequest
from app.services.lab_account import authenticate_lab, signup_lab

router = APIRouter(prefix="/api/labs", tags=["labs"], dependencies=[Depends(require_auth)])


@router.post("/signup", response_model=LabAuthResponse, status_code=201)
def signup(
    body: LabSignupRequest,
    session: Annotated[Session, Depends(get_db)],
) -> LabAuthResponse:
    try:
        lab = signup_lab(
            session, name=body.name, code=body.code, password=body.password
        )
    except DuplicateLabCodeError as exc:
        raise HTTPException(
            status_code=409, detail=f"이미 사용 중인 로그인 코드입니다: {exc.code}"
        ) from exc
    return LabAuthResponse.from_lab(lab)


@router.post("/login", response_model=LabAuthResponse)
def login(
    body: LabLoginRequest,
    session: Annotated[Session, Depends(get_db)],
) -> LabAuthResponse:
    lab = authenticate_lab(session, code=body.code, password=body.password)
    if lab is None:
        raise HTTPException(
            status_code=401, detail="로그인 코드 또는 비밀번호가 올바르지 않습니다."
        )
    return LabAuthResponse.from_lab(lab)
