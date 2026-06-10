"""더미 테스트 — /health 가 200 과 {"status":"ok"} 를 반환하는지 (CI 통과 확인)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
