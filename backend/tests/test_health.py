from contextlib import nullcontext
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_db_unavailable_without_leaking_details(monkeypatch):
    """DB 에 닿지 않으면 503 + degraded. 접속 정보·예외 문구는 응답에 없어야 한다. (DB 불필요)"""
    class UnavailableEngine:
        def connect(self):
            raise RuntimeError("secret_pw: simulated DB failure")

    monkeypatch.setattr("app.api.health.get_engine", UnavailableEngine)
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["database"] == {"status": "unavailable"}
    assert "secret_pw" not in r.text
    responses = client.get("/openapi.json").json()["paths"]["/health"]["get"]["responses"]
    assert responses["503"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/HealthDegraded"}


def test_health_200_shape_matches_openapi_with_connection_double(monkeypatch):
    from app.api.health import HealthOk

    connection = SimpleNamespace(execute=lambda _: SimpleNamespace(scalar_one=lambda: "16.6"))
    monkeypatch.setattr("app.api.health.get_engine", lambda: SimpleNamespace(connect=lambda: nullcontext(connection)))
    r = client.get("/health")
    assert r.status_code == 200
    assert HealthOk.model_validate(r.json()).database.server_version == "16.6"


def test_health_ok_with_real_db(test_engine, monkeypatch):
    """전용 PostgreSQL 컨테이너가 떠 있을 때만 실행."""
    assert test_engine.url.database == "chungpamo_regression"
    monkeypatch.setattr("app.api.health.get_engine", lambda: test_engine)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"]["status"] == "ok"
    assert body["database"]["server_version"].startswith("16")
