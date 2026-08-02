"""
forecast_model.py
-----------------
Time-series demand forecasting using Facebook Prophet.

The model is trained dynamically on-the-fly each time a user uploads
a CSV and clicks "Generate Forecast". No pre-trained models are loaded
or saved — every request trains fresh from the uploaded data.
"""

import warnings
import pandas as pd
from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics

warnings.filterwarnings("ignore")

MAX_TRAINING_ROWS = 5_000  # Memory safeguard: cap rows to prevent OOM on Cloud Run


def run_forecast(df: pd.DataFrame, store: int, item: str, periods: int = 7) -> dict:
    """
    Train a Prophet model on the uploaded CSV data and forecast `periods` days ahead.
    Called on every user request — no caching or model persistence.

    Parameters
    ----------
    df      : DataFrame with columns [date, store, item, sales]
    store   : store ID to filter on
    item    : item ID to filter on (semantic string)
    periods : number of future days to predict (default 7)

    Returns
    -------
    dict with keys:
        - forecast_df   : full Prophet forecast DataFrame
        - historical_df : filtered historical data
        - summary       : forecast summary dict
    """
    # ── Validate columns ──────────────────────────────────────────────────────
    required = {"date", "store", "item", "sales"}
    if not required.issubset(set(df.columns.str.lower())):
        raise ValueError(
            f"CSV must contain columns: {required}. Got: {list(df.columns)}"
        )

    df.columns = df.columns.str.lower()
    df["date"] = pd.to_datetime(df["date"])

    # ── Filter by store and item ──────────────────────────────────────────────
    filtered = df[
        (df["store"] == int(store)) & (df["item"].astype(str) == str(item))
    ].copy()
    if filtered.empty:
        raise ValueError(f"No data found for store={store}, item={item}")

    filtered = filtered.sort_values("date").reset_index(drop=True)

    # ── Rename to Prophet format ──────────────────────────────────────────────
    prophet_df = filtered[["date", "sales"]].rename(
        columns={"date": "ds", "sales": "y"}
    )

    # ── Prophet memory spike safeguard ────────────────────────────────────────
    # Cloud Run has limited RAM. Cap training rows and use L-BFGS MAP (mcmc_samples=0)
    # to prevent Stan's MCMC from spiking above 2 GB.
    if len(prophet_df) > MAX_TRAINING_ROWS:
        prophet_df = prophet_df.tail(MAX_TRAINING_ROWS).reset_index(drop=True)

    # ── Train Prophet on-the-fly ──────────────────────────────────────────────
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        mcmc_samples=0,  # L-BFGS MAP — avoids MCMC memory spikes on Cloud Run
    )
    model.fit(prophet_df)

    # ── Forecast ──────────────────────────────────────────────────────────────
    future = model.make_future_dataframe(periods=periods)
    forecast = model.predict(future)

    # ── Non-Negative Constraint ──────────────────────────────────────────────
    # Prophet is mathematical and can sometimes predict negative values on
    # sharp downward trends. We clip these to zero for retail logic.
    for col in ["yhat", "yhat_lower", "yhat_upper"]:
        forecast[col] = forecast[col].clip(lower=0)

    # ── Build summary ─────────────────────────────────────────────────────────
    future_forecast = forecast.tail(periods)
    avg_demand = round(float(future_forecast["yhat"].mean()), 2)
    max_demand = round(float(future_forecast["yhat"].max()), 2)
    min_demand = round(float(future_forecast["yhat"].min()), 2)
    max_day = future_forecast.loc[future_forecast["yhat"].idxmax(), "ds"].strftime(
        "%Y-%m-%d"
    )
    min_day = future_forecast.loc[future_forecast["yhat"].idxmin(), "ds"].strftime(
        "%Y-%m-%d"
    )

    last_7_avg = float(prophet_df.tail(7)["y"].mean())
    if avg_demand > last_7_avg * 1.05:
        trend = "increasing"
    elif avg_demand < last_7_avg * 0.95:
        trend = "decreasing"
    else:
        trend = "stable"

    summary = {
        "next_7_days_avg": avg_demand,
        "max_demand": max_demand,
        "min_demand": min_demand,
        "max_day": max_day,
        "min_day": min_day,
        "trend": trend,
        "last_7_days_avg": round(last_7_avg, 2),
        "store": store,
        "item": item,
        "forecast_dates": future_forecast["ds"].dt.strftime("%Y-%m-%d").tolist(),
        "forecast_values": [round(v, 2) for v in future_forecast["yhat"].tolist()],
    }

    return {
        "forecast_df": forecast,
        "historical_df": filtered,
        "summary": summary,
    }

def evaluate_model(model: Prophet, df: pd.DataFrame, horizon_days: int = 30) -> dict:
    """
    Run Prophet cross-validation on the trained model and return accuracy metrics.

    Uses a rolling-window approach:
    - initial training period = 80% of total data history
    - cutoff period = horizon_days / 2 (rolling window step)
    - horizon = horizon_days

    Returns a dict with mae, rmse, mape (%), coverage (%), horizon_days.

    NOTE: Cross-validation adds ~2-5x the training time. For datasets with
    < 60 days of history, it falls back to a simple in-sample error estimate
    to avoid insufficient-data errors from Prophet's CV engine.
    """
    data_days = int((df['ds'].max() - df['ds'].min()).days)

    # Minimum viable data for CV: need at least 2x horizon
    if data_days < horizon_days * 2:
        # Fallback: compute in-sample MAE from the fitted model's predictions
        forecast = model.predict(df[['ds']])
        merged = df.merge(forecast[['ds', 'yhat']], on='ds')
        mae = float((merged['y'] - merged['yhat']).abs().mean())
        rmse = float(((merged['y'] - merged['yhat']) ** 2).mean() ** 0.5)
        mape = float(((merged['y'] - merged['yhat']).abs() / merged['y'].replace(0, 1)).mean() * 100)
        return {
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "mape": round(mape, 2),
            "coverage": None,  # Cannot compute coverage from in-sample
            "horizon_days": horizon_days,
            "method": "in_sample",  # Flag so frontend can show a note
        }

    initial_days = max(int(data_days * 0.8), horizon_days * 2)
    period_days = max(horizon_days // 2, 7)  # At least weekly cutoffs

    try:
        cv_df = cross_validation(
            model,
            initial=f"{initial_days} days",
            period=f"{period_days} days",
            horizon=f"{horizon_days} days",
            parallel="processes",
        )
        metrics_df = performance_metrics(cv_df)

        return {
            "mae": round(float(metrics_df["mae"].mean()), 4),
            "rmse": round(float(metrics_df["rmse"].mean()), 4),
            "mape": round(float(metrics_df["mape"].mean() * 100), 2),
            "coverage": round(float(metrics_df["coverage"].mean() * 100), 2),
            "horizon_days": horizon_days,
            "method": "cross_validation",
        }

    except Exception as e:
        # CV can fail on sparse data — log and return None gracefully
        print(f"[evaluate_model] Cross-validation failed: {e}. Metrics will be unavailable.")
        return None