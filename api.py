"""
api.py
------
FastAPI backend – split into two focused endpoints:

  POST /train    → reads CSV, runs Prophet on-the-fly, returns forecast data
  POST /analyze  → takes forecast summary + city + optional image,
                   fetches weather/news, calls Gemini 2.0 Flash, returns report
  GET  /health   → liveness check
"""

import io
import json

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional

from forecast_model import run_forecast
from weather_api import get_weather_summary
from news_api import get_retail_news
from gemini_agent import generate_forecast_report

app = FastAPI(
    title="Multimodal Demand Forecaster API",
    description="Two-stage AI demand forecasting: Prophet → Gemini 2.0 Flash",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ──────────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Multimodal Demand Forecaster API"}


# ─── Stage 1: Train Prophet on-the-fly ───────────────────────────────────────
@app.post("/train")
async def train(
    csv_file: UploadFile = File(..., description="CSV with columns: date, store, item, sales"),
    store: int = Form(...),
    item: int = Form(...),
):
    """
    Step 1 of the pipeline.
    Reads the uploaded CSV, trains a Prophet model in memory, and returns
    the 7-day forecast. Nothing is saved to disk.
    """
    try:
        contents = await csv_file.read()
        df = pd.read_csv(io.BytesIO(contents), parse_dates=["date"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read CSV: {e}")

    try:
        result = run_forecast(df, store=store, item=item, periods=7)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecasting error: {e}")

    summary = result["summary"]
    historical_df = result["historical_df"]
    forecast_df = result["forecast_df"]

    # Chart: last 60 days of history
    hist_tail = historical_df.tail(60)
    history_chart = {
        "dates": hist_tail["date"].dt.strftime("%Y-%m-%d").tolist(),
        "sales": hist_tail["sales"].tolist(),
    }

    # Future 7-day forecast with confidence interval
    future_n = forecast_df.tail(7)
    forecast_chart = {
        "dates":      future_n["ds"].dt.strftime("%Y-%m-%d").tolist(),
        "yhat":       [round(v, 2) for v in future_n["yhat"].tolist()],
        "yhat_lower": [round(v, 2) for v in future_n["yhat_lower"].tolist()],
        "yhat_upper": [round(v, 2) for v in future_n["yhat_upper"].tolist()],
    }

    return JSONResponse(content={
        "success":        True,
        "store":          store,
        "item":           item,
        "summary":        summary,
        "history_chart":  history_chart,
        "forecast_chart": forecast_chart,
    })


# ─── Stage 2: Gather context + call Gemini ───────────────────────────────────
@app.post("/analyze")
async def analyze(
    forecast_summary: str = Form(..., description="JSON-encoded forecast summary from /train"),
    city: str = Form("New York"),
    image_file: Optional[UploadFile] = File(None),
):
    """
    Step 2 of the pipeline.
    Accepts the forecast summary (as JSON string) produced by /train,
    fetches weather + news, and sends everything to Gemini 2.0 Flash.
    """
    try:
        summary = json.loads(forecast_summary)
    except Exception:
        raise HTTPException(status_code=400, detail="forecast_summary must be valid JSON")

    # Fetch weather and news in sequence (both are fast I/O calls)
    weather_text = get_weather_summary(city=city)
    news_text    = get_retail_news(city=city, item=f"item {summary.get('item', '')}")

    # Optional image
    image_bytes = None
    if image_file and image_file.filename:
        try:
            image_bytes = await image_file.read()
        except Exception:
            image_bytes = None

    # Call Gemini
    report = generate_forecast_report(
        forecast_summary=summary,
        weather_text=weather_text,
        news_text=news_text,
        image_bytes=image_bytes,
    )

    return JSONResponse(content={
        "success":         True,
        "weather_summary": weather_text,
        "news_summary":    news_text,
        "gemini_report":   report,
    })
