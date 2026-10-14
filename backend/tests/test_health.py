import pytest
from fastapi.testclient import TestClient
from app.config import get_settings
from app.errors import AppError
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()

    @app.get("/test-error")
    async def trigger_error():
        raise AppError(message="Custom failure", status_code=400, code="VALIDATION_FAILED")

    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data
    assert "app" in data


def test_health_check_api_prefix(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_custom_error_handling(client):
    response = client.get("/test-error")
    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "VALIDATION_FAILED", "message": "Custom failure"}
    }


def test_not_found_structured_error(client):
    response = client.get("/nonexistent")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "HTTP_404", "message": "Not Found"}
    }


def test_cors_preflight(client):
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_settings_override(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Test PolicyPilot")
    monkeypatch.setenv("ENVIRONMENT", "testing")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.app_name == "Test PolicyPilot"
    assert settings.environment == "testing"
    get_settings.cache_clear()
