"""require_auth dependency 테스트."""

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


@pytest.fixture
def client_with_token() -> Iterator[TestClient]:
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

    settings = Settings(api_auth_token="test-secret-token")
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings_dep] = lambda: settings
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_review_queue_without_token_returns_401(client_with_token: TestClient) -> None:
    resp = client_with_token.get("/api/v1/review/queue")
    assert resp.status_code == 401


def test_review_queue_with_wrong_token_returns_401(client_with_token: TestClient) -> None:
    resp = client_with_token.get(
        "/api/v1/review/queue", headers={"Authorization": "Bearer wrong"}
    )
    assert resp.status_code == 401


def test_review_queue_with_valid_token_passes(client_with_token: TestClient) -> None:
    resp = client_with_token.get(
        "/api/v1/review/queue", headers={"Authorization": "Bearer test-secret-token"}
    )
    assert resp.status_code == 200
