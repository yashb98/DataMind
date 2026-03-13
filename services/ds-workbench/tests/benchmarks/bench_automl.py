"""
Benchmark: DS Workbench performance SLOs.
Day 18: Phase 4 — Latency benchmarks for forecasting, QUBO selection.

SLOs:
- ClassicalForecaster.fit()     < 50ms   on 100 rows
- ClassicalForecaster.predict() < 20ms   on 30 periods
- QUBO classical selection      < 100ms  on 50 features
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from ds_workbench.ml.forecaster import ClassicalForecaster
from ds_workbench.ml.quantum import _classical_qubo_selection


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def daily_df_100() -> pd.DataFrame:
    """100-row daily time series."""
    base = date(2024, 1, 1)
    rng = np.random.default_rng(0)
    dates = [(base + timedelta(days=i)).isoformat() for i in range(100)]
    values = np.cumsum(rng.normal(0, 1, 100)) + 50.0
    return pd.DataFrame({"ds": dates, "y": values.tolist()})


@pytest.fixture()
def fitted_forecaster(daily_df_100: pd.DataFrame) -> ClassicalForecaster:
    """Pre-fitted ClassicalForecaster for predict benchmarks."""
    f = ClassicalForecaster()
    f.fit(daily_df_100, "ds", "y", "D")
    return f


@pytest.fixture()
def feature_df_50() -> tuple[pd.DataFrame, list[str]]:
    """50-feature DataFrame for QUBO benchmarking."""
    rng = np.random.default_rng(42)
    n_rows, n_feats = 200, 50
    target = rng.normal(0, 1, n_rows)
    data: dict[str, np.ndarray] = {"target": target}
    for i in range(n_feats):
        data[f"f{i}"] = target * rng.uniform(0.1, 1.0) + rng.normal(0, 0.5, n_rows)
    df = pd.DataFrame(data)
    feature_cols = [f"f{i}" for i in range(n_feats)]
    return df, feature_cols


# ── Benchmarks ────────────────────────────────────────────────────────────────


def test_classical_forecaster_fit_perf(
    benchmark: pytest.FixtureRequest,
    daily_df_100: pd.DataFrame,
) -> None:
    """ClassicalForecaster.fit() SLO: < 50ms on 100 rows."""
    f = ClassicalForecaster()

    result = benchmark(f.fit, daily_df_100, "ds", "y", "D")  # type: ignore[arg-type]

    # Validate SLO via pytest-benchmark stats
    stats = benchmark.stats  # type: ignore[attr-defined]
    mean_ms = stats["mean"] * 1000
    assert mean_ms < 50, f"fit() mean={mean_ms:.2f}ms exceeds 50ms SLO"


def test_classical_forecaster_predict_perf(
    benchmark: pytest.FixtureRequest,
    fitted_forecaster: ClassicalForecaster,
) -> None:
    """ClassicalForecaster.predict() SLO: < 20ms for 30 periods."""
    result = benchmark(fitted_forecaster.predict, 30, 0.95)  # type: ignore[arg-type]

    stats = benchmark.stats  # type: ignore[attr-defined]
    mean_ms = stats["mean"] * 1000
    assert mean_ms < 20, f"predict() mean={mean_ms:.2f}ms exceeds 20ms SLO"

    # Functional correctness
    assert len(result) == 30


def test_qubo_classical_selection_perf(
    benchmark: pytest.FixtureRequest,
    feature_df_50: tuple[pd.DataFrame, list[str]],
) -> None:
    """Classical QUBO feature selection SLO: < 100ms on 50 features."""
    df, feature_cols = feature_df_50

    result = benchmark(  # type: ignore[call-arg]
        _classical_qubo_selection, df, "target", feature_cols, 10
    )

    stats = benchmark.stats  # type: ignore[attr-defined]
    mean_ms = stats["mean"] * 1000
    assert mean_ms < 100, f"QUBO classical mean={mean_ms:.2f}ms exceeds 100ms SLO"

    # Functional correctness
    assert len(result) <= 10
    assert "target" not in result


def test_classical_forecaster_large_predict_perf(
    benchmark: pytest.FixtureRequest,
    fitted_forecaster: ClassicalForecaster,
) -> None:
    """ClassicalForecaster.predict() for 365 periods should complete < 200ms."""
    result = benchmark(fitted_forecaster.predict, 365, 0.95)  # type: ignore[arg-type]

    stats = benchmark.stats  # type: ignore[attr-defined]
    mean_ms = stats["mean"] * 1000
    assert mean_ms < 200, f"predict(365) mean={mean_ms:.2f}ms exceeds 200ms SLO"
    assert len(result) == 365
