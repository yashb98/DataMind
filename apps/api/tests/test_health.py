"""
Day 1 — Health endpoint tests.
Verifies API starts and health probes respond correctly.
"""
import pytest
from fastapi.testclient import TestClient

from datamind_api.main import app

client = TestClient(app)


def test_liveness_returns_200():
    """Liveness probe must always return 200 when process is running."""
    response = client.get("/health/liveness")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert "timestamp" in data


def test_readiness_returns_health_structure():
    """Readiness probe returns structured health data for all services."""
    response = client.get("/health/readiness")
    # In test env, dependencies may be unavailable — 200 or 503 both valid
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "services" in data
    assert isinstance(data["services"], list)
    assert data["version"] == "0.1.0"


def test_openapi_schema_available():
    """OpenAPI schema must be accessible for developer tooling."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "DataMind API"
    assert schema["info"]["version"] == "0.1.0"


def test_docs_available():
    """Swagger UI docs must be accessible."""
    response = client.get("/docs")
    assert response.status_code == 200
