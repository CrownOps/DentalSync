"""기공소 회원가입 / 로그인 — API + 해싱 단위 테스트."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_settings_dep
from app.core.config import Settings
from app.db.base import Base
from app.main import app
from app.services.auth import hash_password, verify_password


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _db() -> Iterator[Session]:
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


# --- 해싱 단위 ---


def test_hash_roundtrip() -> None:
    stored = hash_password("s3cret-pw")
    assert verify_password("s3cret-pw", stored)
    assert not verify_password("wrong", stored)


def test_verify_rejects_sentinel_and_malformed() -> None:
    # 마이그레이션 백필 sentinel 은 어떤 평문과도 불일치해야 한다.
    assert not verify_password("anything", "disabled")
    assert not verify_password("anything", "")


# --- API ---


def test_signup_success_returns_lab_id_without_secret(client: TestClient) -> None:
    resp = client.post(
        "/api/labs/signup",
        json={"name": "크라운옵스 기공소", "code": "crownops-01", "password": "pw123456"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == "crownops-01"
    assert body["name"] == "크라운옵스 기공소"
    assert isinstance(body["lab_id"], int)
    # 비밀번호/해시는 절대 응답에 포함되지 않는다.
    assert "password" not in body
    assert "password_hash" not in body


def test_signup_duplicate_code_returns_409(client: TestClient) -> None:
    payload = {"name": "A", "code": "dup-code", "password": "pw123456"}
    assert client.post("/api/labs/signup", json=payload).status_code == 201
    resp = client.post("/api/labs/signup", json={**payload, "name": "B"})
    assert resp.status_code == 409


def test_signup_validation_rejects_short_fields(client: TestClient) -> None:
    resp = client.post(
        "/api/labs/signup",
        json={"name": "A", "code": "ab", "password": "short"},
    )
    assert resp.status_code == 422


def test_login_success(client: TestClient) -> None:
    client.post(
        "/api/labs/signup",
        json={"name": "A", "code": "login-ok", "password": "pw123456"},
    )
    resp = client.post(
        "/api/labs/login", json={"code": "login-ok", "password": "pw123456"}
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == "login-ok"


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    client.post(
        "/api/labs/signup",
        json={"name": "A", "code": "login-bad", "password": "pw123456"},
    )
    resp = client.post(
        "/api/labs/login", json={"code": "login-bad", "password": "nope-wrong"}
    )
    assert resp.status_code == 401


def test_login_unknown_code_returns_401(client: TestClient) -> None:
    resp = client.post(
        "/api/labs/login", json={"code": "ghost", "password": "whatever"}
    )
    assert resp.status_code == 401
