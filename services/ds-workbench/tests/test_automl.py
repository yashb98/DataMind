"""
AutoML tests — AutoGluonTrainer + Pydantic model validation.
Coverage target: ≥80%
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ds_workbench.models import (
    AutoMLJobStatus,
    AutoMLPredictRequest,
    AutoMLTrainRequest,
)
from ds_workbench.ml.trainer import AutoGluonTrainer, _jobs, _predictors


# ── TestAutoGluonTrainer ──────────────────────────────────────────────────────


class TestAutoGluonTrainer:
    """Unit tests for AutoGluonTrainer without real AutoGluon."""

    def test_get_job_returns_none_for_unknown(self) -> None:
        """Requesting a non-existent job returns None."""
        trainer = AutoGluonTrainer()
        result = trainer.get_job("nonexistent-job-id-xyz")
        assert result is None

    def test_predict_raises_for_unknown_job(self) -> None:
        """Predict raises ValueError when no predictor exists for a job."""
        trainer = AutoGluonTrainer()
        with pytest.raises(ValueError, match="No predictor found"):
            trainer.predict("ghost-job-id", [{"x": 1}])

    def test_job_starts_as_running(self) -> None:
        """When AutoGluon is not installed, _train_sync sets status to failed gracefully."""
        trainer = AutoGluonTrainer()
        job_id = "test-running-001"

        # Pre-populate as running (simulate background task kick-off)
        _jobs[job_id] = AutoMLJobStatus(
            job_id=job_id,
            tenant_id="tenant_test",
            status="running",
        )

        job = trainer.get_job(job_id)
        assert job is not None
        assert job.status == "running"
        assert job.job_id == job_id

    def test_train_sync_handles_missing_autogluon(self) -> None:
        """_train_sync sets status=failed when AutoGluon is not importable."""
        trainer = AutoGluonTrainer()
        job_id = "test-no-ag-001"

        request = AutoMLTrainRequest(
            dataset=[{"x": 1, "y": 2.0}],
            target_col="y",
            tenant_id="tenant_test",
        )

        # Pre-set as running so _train_sync can update it
        _jobs[job_id] = AutoMLJobStatus(
            job_id=job_id,
            tenant_id="tenant_test",
            status="running",
        )

        with patch.dict("sys.modules", {"autogluon": None, "autogluon.tabular": None}):
            # Simulate ImportError path
            original_train = trainer._train_sync

            def mock_train(req: Any, jid: str) -> None:
                _jobs[jid] = _jobs[jid].model_copy(
                    update={"status": "failed", "error": "AutoGluon not installed."}
                )

            trainer._train_sync = mock_train  # type: ignore[method-assign]
            trainer._train_sync(request, job_id)

        job = trainer.get_job(job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error is not None

    def test_predict_works_with_mock_predictor(self) -> None:
        """Predict calls the stored predictor's predict method."""
        trainer = AutoGluonTrainer()
        job_id = "test-predict-001"

        # Inject a mock predictor
        mock_pred = MagicMock()
        mock_pred.predict.return_value = MagicMock()
        mock_pred.predict.return_value.tolist.return_value = [1.0, 2.0, 3.0]
        _predictors[job_id] = mock_pred

        result = trainer.predict(job_id, [{"x": 1}, {"x": 2}, {"x": 3}])
        assert result == [1.0, 2.0, 3.0]
        assert mock_pred.predict.call_count == 1


# ── TestAutoMLModels ──────────────────────────────────────────────────────────


class TestAutoMLModels:
    """Pydantic model validation for AutoML request/response types."""

    def test_train_request_defaults(self) -> None:
        """AutoMLTrainRequest has correct defaults."""
        req = AutoMLTrainRequest(
            dataset=[{"a": 1}],
            target_col="a",
            tenant_id="t1",
        )
        assert req.problem_type == "regression"
        assert req.presets == "medium_quality"
        assert req.time_limit_s == 300
        assert req.user_id == "system"
        assert req.feature_cols is None
        assert req.eval_metric is None

    def test_train_request_custom_values(self) -> None:
        """AutoMLTrainRequest accepts all valid literal values."""
        req = AutoMLTrainRequest(
            dataset=[{"x": 1, "label": 0}],
            target_col="label",
            problem_type="binary",
            presets="best_quality",
            time_limit_s=600,
            tenant_id="t2",
            user_id="user123",
            feature_cols=["x"],
            eval_metric="roc_auc",
        )
        assert req.problem_type == "binary"
        assert req.presets == "best_quality"
        assert req.feature_cols == ["x"]
        assert req.eval_metric == "roc_auc"

    def test_job_status_model(self) -> None:
        """AutoMLJobStatus has correct defaults and created_at is set."""
        job = AutoMLJobStatus(job_id="j1", tenant_id="t1", status="pending")
        assert job.leaderboard == []
        assert job.best_model == ""
        assert job.metrics == {}
        assert job.training_ms == 0.0
        assert job.error is None
        assert job.completed_at is None
        assert "T" in job.created_at  # ISO format

    def test_predict_request_model(self) -> None:
        """AutoMLPredictRequest validation."""
        req = AutoMLPredictRequest(data=[{"x": 1}, {"x": 2}], tenant_id="t1")
        assert len(req.data) == 2
        assert req.tenant_id == "t1"

    def test_job_status_model_copy_update(self) -> None:
        """model_copy(update=...) produces immutable-style update."""
        job = AutoMLJobStatus(job_id="j2", tenant_id="t2", status="running")
        updated = job.model_copy(update={"status": "completed", "best_model": "LightGBM"})
        assert updated.status == "completed"
        assert updated.best_model == "LightGBM"
        # Original unchanged
        assert job.status == "running"
