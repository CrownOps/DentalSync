"""기공소 회원가입 / 로그인 API 스키마."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.models import Lab


class LabSignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LabLoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LabAuthResponse(BaseModel):
    """가입/로그인 응답 — 비밀번호/해시는 절대 포함하지 않는다."""

    lab_id: int
    name: str
    code: str

    @classmethod
    def from_lab(cls, lab: Lab) -> LabAuthResponse:
        return cls(lab_id=lab.id, name=lab.name, code=lab.code)
