"""
Causal Inference tests — naive estimator, model validation, QUBO selection.
Coverage target: ≥80%
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ds_workbench.ml.causal_analyst import CausalAnalyst
from ds_workbench.ml.quantum import _classical_qubo_selection, select_features_qubo
from ds_workbench.models import CausalAnalysisRequest, CausalAnalysisResponse


# ── TestNaiveDiffInMeans ──────────────────────────────────────────────────────


class TestNaiveDiffInMeans:
    """Unit tests for the naive diff-in-means fallback estimator."""

    def test_basic_treatment_effect(self) -> None:
        """Treated group with higher outcome yields positive ATE."""
        rng = np.random.default_rng(42)
        n = 100
        treatment = rng.choice([0.0, 1.0], size=n)
        # Treated units get +5 outcome boost
        outcome = treatment * 5.0 + rng.normal(0, 1, n)
        df = pd.DataFrame({"treatment": treatment, "outcome": outcome})

        analyst = CausalAnalyst()
        ate, ci, p_value, method = analyst._naive_diff_in_means(df, "treatment", "outcome")

        assert ate > 0.0, f"Expected positive ATE, got {ate}"
        assert ci[0] < ci[1], "CI lower bound must be below upper"
        assert method == "diff_in_means_fallback"
        assert p_value is None

    def test_no_effect_when_equal(self) -> None:
        """When treated and control have same outcome, ATE should be near zero."""
        rng = np.random.default_rng(0)
        n = 200
        treatment = rng.choice([0.0, 1.0], size=n)
        outcome = rng.normal(10, 1, n)  # No treatment effect
        df = pd.DataFrame({"treatment": treatment, "outcome": outcome})

        analyst = CausalAnalyst()
        ate, ci, p_value, method = analyst._naive_diff_in_means(df, "treatment", "outcome")

        # With no real effect, ATE should be close to 0 (within 3 std of noise)
        assert abs(ate) < 1.0, f"Expected near-zero ATE, got {ate}"
        assert ci[0] < ate < ci[1], "ATE should be within its own CI"

    def test_negative_treatment_effect(self) -> None:
        """Treated group with lower outcome yields negative ATE."""
        rng = np.random.default_rng(7)
        n = 100
        treatment = rng.choice([0.0, 1.0], size=n)
        outcome = -treatment * 3.0 + rng.normal(0, 0.5, n)
        df = pd.DataFrame({"treatment": treatment, "outcome": outcome})

        analyst = CausalAnalyst()
        ate, ci, _, _ = analyst._naive_diff_in_means(df, "treatment", "outcome")
        assert ate < 0.0

    def test_ci_width_scales_with_variance(self) -> None:
        """High-variance outcome should produce wider confidence intervals."""
        rng = np.random.default_rng(11)
        n = 50
        t = rng.choice([0.0, 1.0], size=n)

        df_low_var = pd.DataFrame({"t": t, "y": rng.normal(0, 0.1, n)})
        df_high_var = pd.DataFrame({"t": t, "y": rng.normal(0, 10.0, n)})

        analyst = CausalAnalyst()
        _, ci_low, _, _ = analyst._naive_diff_in_means(df_low_var, "t", "y")
        _, ci_high, _, _ = analyst._naive_diff_in_means(df_high_var, "t", "y")

        width_low = ci_low[1] - ci_low[0]
        width_high = ci_high[1] - ci_high[0]
        assert width_high > width_low, "High-variance CI should be wider"


# ── TestCausalModels ──────────────────────────────────────────────────────────


class TestCausalModels:
    """Pydantic model validation for causal request/response types."""

    def test_request_defaults(self) -> None:
        """CausalAnalysisRequest has correct defaults."""
        req = CausalAnalysisRequest(
            data=[{"t": 1, "y": 2.0}],
            treatment_col="t",
            outcome_col="y",
            tenant_id="t1",
        )
        assert req.method == "backdoor"
        assert req.covariates == []
        assert req.use_llm_reasoning is True
        assert req.user_id == "system"

    def test_request_with_covariates(self) -> None:
        """CausalAnalysisRequest accepts covariates list."""
        req = CausalAnalysisRequest(
            data=[{"t": 1, "y": 2.0, "age": 30}],
            treatment_col="t",
            outcome_col="y",
            covariates=["age"],
            method="econml_dml",
            tenant_id="t1",
            use_llm_reasoning=False,
        )
        assert req.covariates == ["age"]
        assert req.method == "econml_dml"
        assert req.use_llm_reasoning is False

    def test_response_model(self) -> None:
        """CausalAnalysisResponse validates all required fields."""
        resp = CausalAnalysisResponse(
            causal_estimate=1.23,
            confidence_interval=(0.8, 1.7),
            method_used="dowhy_backdoor",
            ate=1.23,
            p_value=0.04,
            reasoning="Effect is significant.",
            feature_importance={"age": 0.45},
            analysis_ms=123.4,
        )
        assert resp.causal_estimate == pytest.approx(1.23)
        assert resp.confidence_interval == (0.8, 1.7)
        assert resp.ate == pytest.approx(1.23)
        assert resp.p_value == pytest.approx(0.04)
        assert "significant" in resp.reasoning

    def test_response_optional_p_value(self) -> None:
        """CausalAnalysisResponse p_value is optional (None allowed)."""
        resp = CausalAnalysisResponse(
            causal_estimate=0.5,
            confidence_interval=(0.1, 0.9),
            method_used="diff_in_means_fallback",
            ate=0.5,
            p_value=None,
            reasoning="Fallback estimate.",
            analysis_ms=50.0,
        )
        assert resp.p_value is None


# ── TestQuantumFallback ───────────────────────────────────────────────────────


class TestQuantumFallback:
    """Unit tests for classical QUBO feature selection fallback."""

    def _make_correlated_df(self, n_features: int = 20, n_rows: int = 200) -> pd.DataFrame:
        """Create a DataFrame where the first 5 features are strongly correlated with target."""
        rng = np.random.default_rng(42)
        target = rng.normal(0, 1, n_rows)
        data: dict[str, np.ndarray] = {"target": target}
        for i in range(n_features):
            if i < 5:
                # Strong correlation with target
                data[f"f{i}"] = target + rng.normal(0, 0.1, n_rows)
            else:
                # Noise features
                data[f"f{i}"] = rng.normal(0, 1, n_rows)
        return pd.DataFrame(data)

    def test_classical_selection_returns_subset(self) -> None:
        """Classical QUBO selection returns at most n_select features."""
        df = self._make_correlated_df(n_features=20)
        selected = select_features_qubo(df, "target", n_features_to_select=5)
        assert len(selected) <= 5
        assert all(f != "target" for f in selected)

    def test_classical_selects_most_relevant(self) -> None:
        """Classical QUBO should prefer the highly correlated features."""
        df = self._make_correlated_df(n_features=20)
        selected = select_features_qubo(df, "target", n_features_to_select=5)
        # At least 3 of the top-5 strongly correlated features should be selected
        relevant = {f"f{i}" for i in range(5)}
        overlap = len(relevant & set(selected))
        assert overlap >= 3, f"Only {overlap} relevant features selected: {selected}"

    def test_returns_all_when_fewer_than_requested(self) -> None:
        """When n_features < n_select, return all features."""
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "target": [0, 1]})
        selected = select_features_qubo(df, "target", n_features_to_select=10)
        assert set(selected) == {"a", "b"}

    def test_classical_qubo_direct(self) -> None:
        """_classical_qubo_selection returns correct count and excludes target."""
        df = self._make_correlated_df(n_features=10)
        feature_cols = [c for c in df.columns if c != "target"]
        selected = _classical_qubo_selection(df, "target", feature_cols, n_select=4)
        assert len(selected) <= 4
        assert "target" not in selected

    def test_no_numeric_features_returns_empty(self) -> None:
        """DataFrame with only string features returns empty or minimal selection."""
        df = pd.DataFrame({
            "str_feat": ["a", "b", "c"],
            "target": [1.0, 2.0, 3.0],
        })
        # str_feat won't appear in df_numeric, so selection may return empty
        selected = select_features_qubo(df, "target", n_features_to_select=5)
        # Should not crash; result is a list
        assert isinstance(selected, list)
