"""
Integration tests — Phase 4: Data Science Workbench.
Days 18-21: Requires running docker compose stack (DATAMIND_INTEGRATION_TESTS=true).

Usage:
    DATAMIND_INTEGRATION_TESTS=true pytest tests/integration/test_phase4_ds_workbench.py -v

SLO targets:
    ds-workbench health: < 100ms
    AutoML train start: < 1s (async, background)
    Forecast prediction: < 5s with confidence intervals
    Causal analysis: < 30s (includes optional LLM reasoning)
    Model deploy: < 30s
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

INTEGRATION = os.getenv("DATAMIND_INTEGRATION_TESTS", "false").lower() == "true"
pytestmark = pytest.mark.skipif(
    not INTEGRATION,
    reason="Set DATAMIND_INTEGRATION_TESTS=true to enable.",
)

DS_WORKBENCH_URL = os.getenv("DS_WORKBENCH_URL", "http://localhost:8120")
MLFLOW_URL = os.getenv("MLFLOW_URL", "http://localhost:5000")
JUPYTERHUB_URL = os.getenv("JUPYTERHUB_URL", "http://localhost:8888")
TEST_TENANT = "integration_test"

# ── Sample data ───────────────────────────────────────────────────────────────

SAMPLE_TABULAR = [
    {"age": 25, "income": 50000, "education": 12, "churn": 0},
    {"age": 35, "income": 75000, "education": 16, "churn": 0},
    {"age": 45, "income": 60000, "education": 14, "churn": 1},
    {"age": 28, "income": 45000, "education": 12, "churn": 1},
    {"age": 52, "income": 90000, "education": 18, "churn": 0},
    {"age": 31, "income": 55000, "education": 14, "churn": 0},
    {"age": 40, "income": 70000, "education": 16, "churn": 1},
    {"age": 22, "income": 35000, "education": 12, "churn": 1},
    {"age": 48, "income": 85000, "education": 17, "churn": 0},
    {"age": 36, "income": 65000, "education": 15, "churn": 0},
]

SAMPLE_TIMESERIES = [
    {"date": f"2024-{m:02d}-01", "revenue": 100000 + m * 5000 + (m % 3) * 2000}
    for m in range(1, 13)
]


# ── Health checks ─────────────────────────────────────────────────────────────


class TestDSWorkbenchHealth:
    def test_liveness(self) -> None:
        r = httpx.get(f"{DS_WORKBENCH_URL}/health/liveness", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "alive"
        assert r.json()["service"] == "ds-workbench"

    def test_readiness(self) -> None:
        r = httpx.get(f"{DS_WORKBENCH_URL}/health/readiness", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")

    def test_liveness_under_100ms(self) -> None:
        start = time.perf_counter()
        r = httpx.get(f"{DS_WORKBENCH_URL}/health/liveness", timeout=5)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 100, f"Health {elapsed_ms:.1f}ms > 100ms SLO"


class TestMLflowHealth:
    def test_mlflow_health(self) -> None:
        r = httpx.get(f"{MLFLOW_URL}/health", timeout=10)
        assert r.status_code == 200

    def test_mlflow_experiments_api(self) -> None:
        r = httpx.get(f"{MLFLOW_URL}/api/2.0/mlflow/experiments/search", timeout=10)
        assert r.status_code == 200


class TestJupyterHubHealth:
    def test_jupyterhub_health(self) -> None:
        r = httpx.get(f"{JUPYTERHUB_URL}/hub/health", timeout=10)
        assert r.status_code == 200

    def test_jupyterhub_api_accessible(self) -> None:
        r = httpx.get(f"{JUPYTERHUB_URL}/hub/api/", timeout=10)
        assert r.status_code in (200, 403)  # 403 means API is up (auth required)


# ── AutoML ────────────────────────────────────────────────────────────────────


class TestAutoML:
    def test_train_job_starts_immediately(self) -> None:
        """Train job must start (return job_id) in < 1s."""
        start = time.perf_counter()
        r = httpx.post(
            f"{DS_WORKBENCH_URL}/api/automl/train",
            json={
                "dataset": SAMPLE_TABULAR,
                "target_col": "churn",
                "problem_type": "binary",
                "tenant_id": TEST_TENANT,
                "time_limit_s": 30,
                "presets": "medium_quality",
            },
            timeout=5,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "started"
        assert elapsed_ms < 1000, f"Train start took {elapsed_ms:.1f}ms > 1s SLO"
        TestAutoML._job_id = data["job_id"]

    def test_poll_job_status(self) -> None:
        """Job status endpoint must return valid status."""
        if not hasattr(TestAutoML, "_job_id"):
            pytest.skip("Depends on test_train_job_starts_immediately")
        r = httpx.get(f"{DS_WORKBENCH_URL}/api/automl/jobs/{TestAutoML._job_id}", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert data["status"] in ("pending", "running", "completed", "failed")
        assert data["job_id"] == TestAutoML._job_id

    def test_unknown_job_returns_404(self) -> None:
        r = httpx.get(f"{DS_WORKBENCH_URL}/api/automl/jobs/nonexistent-xyz", timeout=5)
        assert r.status_code == 404

    def test_predict_before_completion_returns_400(self) -> None:
        """Predicting on a running job must return 400, not crash."""
        if not hasattr(TestAutoML, "_job_id"):
            pytest.skip("Depends on test_train_job_starts_immediately")
        job = httpx.get(f"{DS_WORKBENCH_URL}/api/automl/jobs/{TestAutoML._job_id}", timeout=5).json()
        if job["status"] == "completed":
            pytest.skip("Job already completed")
        r = httpx.post(
            f"{DS_WORKBENCH_URL}/api/automl/predict/{TestAutoML._job_id}",
            json={"data": SAMPLE_TABULAR[:3], "tenant_id": TEST_TENANT},
            timeout=5,
        )
        assert r.status_code == 400


# ── Forecasting ───────────────────────────────────────────────────────────────


class TestForecasting:
    def test_train_forecast_returns_job_id(self) -> None:
        r = httpx.post(
            f"{DS_WORKBENCH_URL}/api/forecast/train",
            json={
                "data": SAMPLE_TIMESERIES,
                "date_col": "date",
                "value_col": "revenue",
                "periods": 3,
                "frequency": "M",
                "model": "auto",
                "tenant_id": TEST_TENANT,
            },
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "completed"
        TestForecasting._job_id = data["job_id"]

    def test_forecast_returns_confidence_intervals(self) -> None:
        """All forecast points must include yhat_lower and yhat_upper (required per CLAUDE.md)."""
        if not hasattr(TestForecasting, "_job_id"):
            pytest.skip("Depends on test_train_forecast_returns_job_id")
        r = httpx.get(
            f"{DS_WORKBENCH_URL}/api/forecast/predict",
            params={"job_id": TestForecasting._job_id, "periods": 3, "tenant_id": TEST_TENANT},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "forecast" in data
        assert len(data["forecast"]) == 3
        for point in data["forecast"]:
            assert "yhat" in point, "Missing yhat in forecast point"
            assert "yhat_lower" in point, "Missing yhat_lower (CI required)"
            assert "yhat_upper" in point, "Missing yhat_upper (CI required)"
            assert point["yhat_lower"] <= point["yhat"] <= point["yhat_upper"], \
                f"CI order violated: {point['yhat_lower']} > {point['yhat']} or > {point['yhat_upper']}"

    def test_forecast_under_5s_slo(self) -> None:
        if not hasattr(TestForecasting, "_job_id"):
            pytest.skip("Depends on test_train_forecast_returns_job_id")
        start = time.perf_counter()
        httpx.get(
            f"{DS_WORKBENCH_URL}/api/forecast/predict",
            params={"job_id": TestForecasting._job_id, "periods": 6, "tenant_id": TEST_TENANT},
            timeout=10,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 5000, f"Forecast took {elapsed_ms:.0f}ms > 5s SLO"


# ── Causal Inference ──────────────────────────────────────────────────────────


class TestCausalInference:
    def test_causal_analysis_returns_ate(self) -> None:
        r = httpx.post(
            f"{DS_WORKBENCH_URL}/api/causal/analyze",
            json={
                "data": SAMPLE_TABULAR,
                "treatment_col": "income",
                "outcome_col": "churn",
                "covariates": ["age", "education"],
                "method": "backdoor",
                "tenant_id": TEST_TENANT,
                "use_llm_reasoning": False,  # Skip LLM in tests for speed
            },
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert "causal_estimate" in data
        assert "confidence_interval" in data
        assert isinstance(data["causal_estimate"], float)
        ci = data["confidence_interval"]
        assert len(ci) == 2
        assert ci[0] <= ci[1], "CI lower must be <= upper"

    def test_causal_analysis_includes_reasoning(self) -> None:
        r = httpx.post(
            f"{DS_WORKBENCH_URL}/api/causal/analyze",
            json={
                "data": SAMPLE_TABULAR,
                "treatment_col": "income",
                "outcome_col": "churn",
                "covariates": ["age"],
                "method": "backdoor",
                "tenant_id": TEST_TENANT,
                "use_llm_reasoning": False,
            },
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert "reasoning" in data
        assert isinstance(data["reasoning"], str)
        assert len(data["reasoning"]) > 0

    def test_causal_analysis_under_30s(self) -> None:
        start = time.perf_counter()
        httpx.post(
            f"{DS_WORKBENCH_URL}/api/causal/analyze",
            json={
                "data": SAMPLE_TABULAR,
                "treatment_col": "age",
                "outcome_col": "income",
                "covariates": [],
                "method": "backdoor",
                "tenant_id": TEST_TENANT,
                "use_llm_reasoning": False,
            },
            timeout=35,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 30_000, f"Causal took {elapsed_ms:.0f}ms > 30s SLO"


# ── Model Deployment ──────────────────────────────────────────────────────────


class TestModelDeployment:
    def test_list_models_returns_empty_for_new_tenant(self) -> None:
        r = httpx.get(
            f"{DS_WORKBENCH_URL}/api/models",
            params={"tenant_id": f"fresh_{int(time.time())}"},
            timeout=5,
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_deploy_unknown_job_returns_400(self) -> None:
        r = httpx.post(
            f"{DS_WORKBENCH_URL}/api/models/deploy",
            json={
                "job_id": "nonexistent-xyz",
                "model_name": "test-model",
                "tenant_id": TEST_TENANT,
            },
            timeout=5,
        )
        assert r.status_code == 400
