"""
Forecasting Router — Prophet, NeuralForecast, Chronos, and classical endpoints.
Day 18: Phase 4 — REST API for time-series forecasting with confidence intervals.

Protocols: None
SOLID: SRP (HTTP routing only), DIP (IForecaster injected via factory)
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import pandas as pd
import structlog
from fastapi import APIRouter, HTTPException

from ds_workbench.models import ForecastPredictRequest, ForecastResponse, ForecastTrainRequest
from ds_workbench.ml.forecaster import compute_metrics, get_forecaster

router = APIRouter(prefix="/api/forecast", tags=["Forecasting"])
log = structlog.get_logger(__name__)

# In-memory store for fitted forecasters: job_id → metadata dict
_fitted: dict[str, Any] = {}


@router.post("/train")
async def train_forecast(body: ForecastTrainRequest) -> dict:
    """Train a forecasting model on the provided time series data.

    The model is fitted synchronously (in thread pool) and stored in memory
    keyed by job_id for subsequent prediction requests.

    Args:
        body: ForecastTrainRequest with data, date/value columns, model type, frequency.

    Returns:
        Dict with job_id, model_used, and status "completed".
    """
    job_id = f"forecast-{uuid.uuid4().hex[:8]}"
    forecaster = get_forecaster(body.model)
    df = pd.DataFrame(body.data)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, forecaster.fit, df, body.date_col, body.value_col, body.frequency
    )
    _fitted[job_id] = {
        "forecaster": forecaster,
        "df": df,
        "date_col": body.date_col,
        "value_col": body.value_col,
    }
    log.info("forecast.train.done", job_id=job_id, model=forecaster.name())
    return {"job_id": job_id, "model_used": forecaster.name(), "status": "completed"}


@router.post("/predict")
async def predict_forecast(body: ForecastPredictRequest) -> ForecastResponse:
    """Generate forecast with confidence intervals for a trained model.

    Args:
        body: ForecastPredictRequest with job_id, periods, confidence_level, tenant_id.

    Returns:
        ForecastResponse with forecast points, metrics, and latency.

    Raises:
        HTTPException 404: If forecast job not found.
    """
    if body.job_id not in _fitted:
        raise HTTPException(
            status_code=404, detail=f"Forecast job {body.job_id} not found"
        )

    entry = _fitted[body.job_id]
    start = time.perf_counter()
    forecaster = entry["forecaster"]

    loop = asyncio.get_event_loop()
    forecast_points = await loop.run_in_executor(
        None, forecaster.predict, body.periods, body.confidence_level
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Compute metrics if we have enough historical data to hold out
    df: pd.DataFrame = entry["df"]
    value_col: str = entry["value_col"]
    mape: float | None = None
    rmse: float | None = None

    actual_tail = df[value_col].tail(min(body.periods, len(df))).tolist()
    if len(actual_tail) == len(forecast_points):
        predicted_vals = [p.yhat for p in forecast_points[: len(actual_tail)]]
        metrics = compute_metrics(actual_tail, predicted_vals)
        mape = metrics.get("mape")
        rmse = metrics.get("rmse")

    return ForecastResponse(
        job_id=body.job_id,
        forecast=forecast_points,
        model_used=forecaster.name(),
        mape=mape,
        rmse=rmse,
        confidence_level=body.confidence_level,
        generation_ms=round(elapsed_ms, 2),
    )
