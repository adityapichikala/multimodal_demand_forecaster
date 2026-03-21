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

warnings.filterwarnings("ignore")

MAX_TRAINING_ROWS = 5_000   # Memory safeguard: cap rows to prevent OOM on Cloud Run


def run_forecast(df: pd.DataFrame, store: int, item: int, periods: int = 7) -> dict:
    """
    Train a Prophet model on the uploaded CSV data and forecast `periods` days ahead.
    Called on every user request — no caching or model persistence.

    Parameters
    ----------
    df      : DataFrame with columns [date, store, item, sales]
    store   : store ID to filter on
    item    : item ID to filter on
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
        raise ValueError(f"CSV must contain columns: {required}. Got: {list(df.columns)}")

    df.columns = df.columns.str.lower()
    df["date"] = pd.to_datetime(df["date"])

    # ── Filter by store and item ──────────────────────────────────────────────
    filtered = df[(df["store"] == int(store)) & (df["item"] == int(item))].copy()
    if filtered.empty:
        raise ValueError(f"No data found for store={store}, item={item}")

    filtered = filtered.sort_values("date").reset_index(drop=True)

    # ── Rename to Prophet format ──────────────────────────────────────────────
    prophet_df = filtered[["date", "sales"]].rename(columns={"date": "ds", "sales": "y"})

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
        mcmc_samples=0,   # L-BFGS MAP — avoids MCMC memory spikes on Cloud Run
    )
    model.fit(prophet_df)

    # ── Forecast ──────────────────────────────────────────────────────────────
    future   = model.make_future_dataframe(periods=periods)
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
    max_day    = future_forecast.loc[future_forecast["yhat"].idxmax(), "ds"].strftime("%Y-%m-%d")
    min_day    = future_forecast.loc[future_forecast["yhat"].idxmin(), "ds"].strftime("%Y-%m-%d")

    last_7_avg = float(prophet_df.tail(7)["y"].mean())
    if avg_demand > last_7_avg * 1.05:
        trend = "increasing"
    elif avg_demand < last_7_avg * 0.95:
        trend = "decreasing"
    else:
        trend = "stable"

    summary = {
        "next_7_days_avg": avg_demand,
        "max_demand":      max_demand,
        "min_demand":      min_demand,
        "max_day":         max_day,
        "min_day":         min_day,
        "trend":           trend,
        "last_7_days_avg": round(last_7_avg, 2),
        "store":           store,
        "item":            item,
        "forecast_dates":  future_forecast["ds"].dt.strftime("%Y-%m-%d").tolist(),
        "forecast_values": [round(v, 2) for v in future_forecast["yhat"].tolist()],
    }

    return {
        "forecast_df":   forecast,
        "historical_df": filtered,
        "summary":       summary,
    }
