"""
Quantum Feature Selection — D-Wave QUBO (>50 features) with classical fallback.
Day 18: Phase 4 — QUBO-based feature selection with D-Wave Leap integration.

Protocols: None
SOLID: SRP (feature selection only), OCP (fallback via classical if D-Wave unavailable)
SLO: Classical fallback always available. D-Wave used when api token is set AND features > 50.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import structlog

from ds_workbench.config import settings

log = structlog.get_logger(__name__)


def select_features_qubo(
    df: pd.DataFrame,
    target_col: str,
    n_features_to_select: int = 10,
) -> list[str]:
    """Select top features using QUBO formulation.

    Decision logic:
    - If D-Wave API token is set AND features > 50: use D-Wave Leap hybrid sampler.
    - Otherwise: classical QUBO simulation via greedy correlation-based selection.

    Args:
        df: DataFrame with features and target column.
        target_col: Name of the target variable column.
        n_features_to_select: Maximum number of features to return.

    Returns:
        List of selected feature column names, ordered by QUBO score.
    """
    feature_cols = [c for c in df.columns if c != target_col]

    if len(feature_cols) <= n_features_to_select:
        return feature_cols

    if settings.dwave_api_token and len(feature_cols) > 50:
        try:
            return _dwave_qubo_selection(df, target_col, feature_cols, n_features_to_select)
        except Exception as exc:
            log.warning(
                "quantum.dwave.failed",
                error=str(exc),
                fallback="classical",
                n_features=len(feature_cols),
            )

    return _classical_qubo_selection(df, target_col, feature_cols, n_features_to_select)


def _classical_qubo_selection(
    df: pd.DataFrame,
    target_col: str,
    feature_cols: list[str],
    n_select: int,
) -> list[str]:
    """Simulate QUBO objective classically via greedy search.

    QUBO objective (maximise):
        Σᵢ aᵢxᵢ - λ Σᵢⱼ bᵢⱼxᵢxⱼ
    where:
        aᵢ = |corr(feature_i, target)|  (relevance)
        bᵢⱼ = |corr(feature_i, feature_j)|  (redundancy penalty)
        λ = 0.5 (redundancy weight)

    Greedy solution: at each step pick the feature with highest marginal QUBO gain.

    Args:
        df: DataFrame with features and target.
        target_col: Target column name.
        feature_cols: Candidate feature column names.
        n_select: Number of features to select.

    Returns:
        List of selected feature names.
    """
    df_numeric = (
        df[feature_cols + [target_col]].select_dtypes(include=[np.number]).fillna(0)
    )
    available = [c for c in feature_cols if c in df_numeric.columns]
    target = target_col if target_col in df_numeric.columns else df_numeric.columns[-1]

    corr_matrix = df_numeric.corr()
    relevance = {c: abs(float(corr_matrix.loc[c, target])) for c in available}

    selected: list[str] = []
    for _ in range(min(n_select, len(available))):
        best: str | None = None
        best_score = -1.0
        for c in available:
            if c in selected:
                continue
            # Relevance term
            score = relevance.get(c, 0.0)
            # Redundancy penalty (λ=0.5)
            if selected:
                redundancy = (
                    sum(abs(float(corr_matrix.loc[c, s])) for s in selected)
                    * 0.5
                    / len(selected)
                )
                score -= redundancy
            if score > best_score:
                best_score = score
                best = c
        if best:
            selected.append(best)

    return selected


def _dwave_qubo_selection(
    df: pd.DataFrame,
    target_col: str,
    feature_cols: list[str],
    n_select: int,
) -> list[str]:
    """Run D-Wave Leap hybrid sampler for QUBO feature selection.

    Uses D-Wave's LeapHybridSampler which handles large QUBO problems (>50 variables)
    that are infeasible for pure QPU embedding.

    Args:
        df: DataFrame with features and target.
        target_col: Target column name.
        feature_cols: Candidate feature column names.
        n_select: Number of features to select.

    Returns:
        List of selected feature names from D-Wave sample.

    Raises:
        ImportError: If dwave-system or dimod are not installed.
        RuntimeError: If D-Wave sampler returns invalid response.
    """
    from dwave.system import LeapHybridSampler  # type: ignore[import]

    df_numeric = (
        df[feature_cols + [target_col]].select_dtypes(include=[np.number]).fillna(0)
    )
    available = [c for c in feature_cols if c in df_numeric.columns]
    corr_matrix = df_numeric.corr()
    target = target_col if target_col in df_numeric.columns else df_numeric.columns[-1]

    # Build QUBO dictionary
    Q: dict[tuple[str, str], float] = {}
    for i, fi in enumerate(available):
        # Linear terms: negate relevance (minimise → maximise relevance)
        Q[(fi, fi)] = -abs(float(corr_matrix.loc[fi, target]))
        for fj in available[i + 1 :]:
            # Quadratic terms: redundancy penalty
            Q[(fi, fj)] = abs(float(corr_matrix.loc[fi, fj])) * 0.5

    sampler = LeapHybridSampler(
        token=settings.dwave_api_token,
        endpoint=settings.dwave_endpoint,
    )
    response = sampler.sample_qubo(Q, label="datamind-feature-selection")

    best_sample = response.first.sample
    selected = [f for f, val in best_sample.items() if val == 1]

    log.info(
        "quantum.dwave.completed",
        n_selected=len(selected),
        n_candidates=len(available),
    )
    return selected[:n_select]
