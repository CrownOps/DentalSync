"""DB 예외가 미처리 500(=CORS 차단으로 둔갑)이 아니라 CORS 헤더가 붙은 5xx로
처리되는지 검증.

배경: Starlette 에서 `Exception` 키 핸들러는 ServerErrorMiddleware(CORS 미들웨어 바깥)에서
실행되어 응답에 CORS 헤더가 붙지 않는다. DB 예외를 `SQLAlchemyError` 같은 구체 타입으로
처리해야 ExceptionMiddleware(CORS 안쪽)에서 응답이 만들어져 헤더가 붙는다.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.main import app

_ORIGIN = "http://localhost:3000"


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def _override_db_raising(exc: Exception) -> None:
    def _db() -> Iterator[Session]:
        # raise 뒤의 yield 는 도달 불가지만, get_db 를 제너레이터 의존성으로 유지하기 위함
        if False:  # pragma: no cover
            yield
        raise exc

    app.dependency_overrides[get_db] = _db


def test_operational_error_returns_503_with_cors(client: TestClient) -> None:
    """연결 실패(OperationalError) → 503 + CORS 헤더."""
    _override_db_raising(OperationalError("SELECT 1", {}, Exception("db down")))

    resp = client.get("/api/orders", headers={"Origin": _ORIGIN})

    assert resp.status_code == 503
    assert resp.headers.get("access-control-allow-origin") == _ORIGIN


def test_programming_error_returns_500_with_cors(client: TestClient) -> None:
    """스키마 누락(ProgrammingError, 예: relation does not exist) → 500 + CORS 헤더."""
    _override_db_raising(
        ProgrammingError("SELECT 1", {}, Exception('relation "labs" does not exist'))
    )

    resp = client.get("/api/orders", headers={"Origin": _ORIGIN})

    assert resp.status_code == 500
    assert resp.headers.get("access-control-allow-origin") == _ORIGIN
