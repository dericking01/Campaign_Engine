from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    """Liveness must never depend on Postgres/Redis/Kafka - see /ready for
    dependency checks."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_imports_upload_requires_auth() -> None:
    resp = client.post("/api/v1/imports/upload")
    assert resp.status_code == 401


def test_openapi_schema_is_served() -> None:
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "AfyaCall Campaign Engine"
