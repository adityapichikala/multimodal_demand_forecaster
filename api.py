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
import os
import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from typing import Optional
from celery.result import AsyncResult
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from celery_worker import run_async_forecast, celery_app
from models import HistoricalSale, Product, Merchant
from auth import get_password_hash, verify_password, create_access_token, get_current_merchant, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import timedelta

from forecast_model import run_forecast
from weather_api import get_weather_summary
from news_api import get_retail_news
from agents import run_verification_pipeline

import redis.asyncio as redis_async
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from database import engine, Base, get_db
import models
from sqlalchemy.orm import Session

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Redis Cache
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    r = redis_async.from_url(redis_url, encoding="utf8", decode_responses=True)
    FastAPICache.init(RedisBackend(r), prefix="fastapi-cache")
    yield

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Multimodal Demand Forecaster API",
    description="Two-stage AI demand forecasting: Prophet → Gemini 2.0 Flash",
    version="2.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Auth Endpoints ──────────────────────────────────────────────────────────
@app.post("/register")
async def register(
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form("Default Merchant"),
    db: Session = Depends(get_db)
):
    db_merchant = db.query(Merchant).filter(Merchant.email == email).first()
    if db_merchant:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(password)
    new_merchant = Merchant(email=email, name=name, hashed_password=hashed_password)
    db.add(new_merchant)
    db.commit()
    db.refresh(new_merchant)
    return {"success": True, "message": "Merchant created"}

@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    merchant = db.query(Merchant).filter(Merchant.email == form_data.username).first()
    if not merchant or not verify_password(form_data.password, merchant.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": merchant.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# ─── Health ──────────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Multimodal Demand Forecaster API"}


# ─── Stage 1a: Upload Data ───────────────────────────────────────────────────
@app.post("/upload-data")
@limiter.limit("5/minute")
async def upload_data(
    request: Request,
    csv_file: UploadFile = File(..., description="CSV with columns: date, store, item, sales"),
    db: Session = Depends(get_db),
    current_merchant: Merchant = Depends(get_current_merchant)
):
    """
    Ingests CSV data into the PostgreSQL HistoricalSale table.
    """
    try:
        contents = await csv_file.read()
        df = pd.read_csv(io.BytesIO(contents), parse_dates=["date"])
        
        # Ensure products exist for relational integrity
        product_items = df["item"].unique()
        product_map = {}
        for p_id in product_items:
            p_id_int = int(p_id)
            prod = db.query(Product).filter(Product.item_id == p_id_int, Product.merchant_id == current_merchant.id).first()
            if not prod:
                prod = Product(item_id=p_id_int, name=f"Product {p_id_int}", merchant_id=current_merchant.id)
                db.add(prod)
                db.commit()
                db.refresh(prod)
            product_map[p_id_int] = prod.id
            
        # Batch insert into DB
        sales_records = []
        for _, row in df.iterrows():
            sales_records.append(
                HistoricalSale(
                    store_id=row["store"],
                    product_id=product_map[int(row["item"])],
                    date=row["date"].date(),
                    sales=row["sales"]
                )
            )
        db.add_all(sales_records)
        db.commit()
        return {"success": True, "message": f"Inserted {len(sales_records)} records"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to ingest CSV: {e}")

# ─── Stage 1b: Train Prophet asynchronously ──────────────────────────────────
@app.post("/train-async")
@limiter.limit("10/minute")
async def train_async(
    request: Request,
    store: int = Form(...),
    item: int = Form(...),
    db: Session = Depends(get_db),
    current_merchant: Merchant = Depends(get_current_merchant)
):
    """
    Enqueues a background task to train a Prophet model and returns a task_id.
    """
    product = db.query(Product).filter(Product.item_id == item, Product.merchant_id == current_merchant.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found. Please upload historical data for this item first.")
        
    task = run_async_forecast.delay(store_id=store, product_pk=product.id)
    return JSONResponse(status_code=202, content={"task_id": task.id, "status": "Processing"})

@app.get("/task/{task_id}")
@limiter.limit("30/minute")
async def get_task_status(
    request: Request,
    task_id: str,
    current_merchant: Merchant = Depends(get_current_merchant)
):
    """
    Polling endpoint to check if the background ML Task finished.
    """
    task_result = AsyncResult(task_id, app=celery_app)
    result = {
        "task_id": task_id,
        "task_status": task_result.status,
    }
    
    if task_result.status == "SUCCESS":
        result["result"] = task_result.result
    elif task_result.status == "FAILURE":
        result["error"] = str(task_result.result)
        
    return result


# ─── Stage 2: Gather context + call Gemini ───────────────────────────────────
@app.post("/analyze")
@limiter.limit("5/minute") # Strict LLM Rate Limits
async def analyze(
    request: Request,
    forecast_id: int = Form(..., description="The ID of the generated forecast"),
    city: str = Form("New York"),
    image_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_merchant: Merchant = Depends(get_current_merchant)
):
    """
    Step 2 of the pipeline.
    Fetches forecast data from DB using forecast_id, fetches weather + news,
    and sends everything to the Multi-Agent Verification Pipeline.
    """
    forecast = db.query(models.Forecast).filter(models.Forecast.id == forecast_id).first()
    if not forecast:
        raise HTTPException(status_code=404, detail="Forecast not found")
        
    if forecast.product.merchant_id != current_merchant.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this forecast")
        
    summary = forecast.forecast_data.get("summary") if forecast.forecast_data else {}

    # Fetch weather and news in sequence (both are fast I/O calls)
    weather_text = get_weather_summary(city=city)
    news_text    = get_retail_news(city=city, item=f"item {summary.get('item', '')}")

    # Optional image (ignored in this phase but prepared for Future Phase 4)
    image_bytes = None
    if image_file and image_file.filename:
        try:
            image_bytes = await image_file.read()
        except Exception:
            image_bytes = None

    # Call Multi-Agent Pipeline
    report = run_verification_pipeline(
        forecast_summary=summary,
        weather_text=weather_text,
        news_text=news_text
    )

    # Save the agent feedback back to the database
    forecast.gemini_report = report
    db.commit()

    return JSONResponse(content={
        "success":         True,
        "weather_summary": weather_text,
        "news_summary":    news_text,
        "gemini_report":   report,
    })
