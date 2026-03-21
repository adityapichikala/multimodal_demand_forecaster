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
import pandas as pd
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends, Request, Response
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

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    print(f"DEBUG: Incoming {request.method} request to {request.url}")
    print(f"DEBUG: Origin: {request.headers.get('origin')}")
    print(f"DEBUG: Auth: {request.headers.get('authorization')[:20] if request.headers.get('authorization') else 'None'}")
    response = await call_next(request)
    return response

# Production-grade CORS
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
origins = [url.strip() for url in frontend_url.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
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


# ─── Dashboard Meta ────────────────────────────────────────────────────────────
@app.get("/dashboard-meta")
async def get_dashboard_meta(response: Response, db: Session = Depends(get_db), current_merchant: Merchant = Depends(get_current_merchant)):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    # Fetch distinct products that actually HAVE sales data for this merchant
    products = db.query(Product.item_id, Product.name).join(HistoricalSale, Product.id == HistoricalSale.product_id).filter(Product.merchant_id == current_merchant.id).distinct().all()
    
    # Format as a list of dictionaries
    pr_list = [{"id": p.item_id, "name": p.name} for p in products]
    pr_list = sorted(pr_list, key=lambda x: x["id"])

    # Fetch distinct stores that actually HAVE sales data for this merchant
    stores = db.query(HistoricalSale.store_id).join(Product, HistoricalSale.product_id == Product.id).filter(Product.merchant_id == current_merchant.id).distinct().all()
    st_ids = sorted([s[0] for s in stores])

    return {"products": pr_list, "stores": st_ids}

# ─── Forecast History ────────────────────────────────────────────────────────
@app.get("/forecast-history")
async def get_forecast_history(
    db: Session = Depends(get_db), 
    current_merchant: Merchant = Depends(get_current_merchant)
):
    """
    Retrieves all past forecasts for the current merchant, ordered by date.
    """
    forecasts = db.query(models.Forecast).join(models.Product).filter(
        models.Product.merchant_id == current_merchant.id
    ).order_by(models.Forecast.forecast_date.desc()).all()
    
    return [
        {
            "id": f.id,
            "created_at": f.created_at.isoformat(),
            "store_id": f.store_id,
            "product_name": f.product.name,
            "product_id": f.product.item_id,
            "summary": f.forecast_data.get("summary") if f.forecast_data else None,
            "has_report": f.gemini_report is not None
        } for f in forecasts
    ]

@app.get("/forecast/{forecast_id}")
async def get_forecast_detail(
    forecast_id: int,
    db: Session = Depends(get_db),
    current_merchant: Merchant = Depends(get_current_merchant)
):
    """
    Retrieves the full detail of a specific forecast.
    """
    forecast = db.query(models.Forecast).filter(models.Forecast.id == forecast_id).first()
    if not forecast:
        raise HTTPException(status_code=404, detail="Forecast not found")
        
    if forecast.product.merchant_id != current_merchant.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    return {
        "id": forecast.id,
        "created_at": forecast.created_at.isoformat(),
        "store_id": forecast.store_id,
        "product_name": forecast.product.name,
        "product_id": forecast.product.item_id,
        "summary": forecast.forecast_data.get("summary") if forecast.forecast_data else None,
        "gemini_report": forecast.gemini_report
    }

# ─── Stage 1a: Upload Data ───────────────────────────────────────────────────
@app.post("/upload-data")
@limiter.limit("5/minute")
async def upload_data(
    request: Request,
    csv_file: UploadFile = File(..., description="CSV or Excel file"),
    clear_all: bool = Form(False),
    db: Session = Depends(get_db),
    current_merchant: Merchant = Depends(get_current_merchant)
):
    """
    Ingests CSV data into the PostgreSQL HistoricalSale table.
    """
    try:
        if clear_all:
            # Wipe everything for this merchant
            # Delete Forecasts
            db.query(models.Forecast).filter(models.Forecast.product_id.in_(db.query(models.Product.id).filter(models.Product.merchant_id == current_merchant.id))).delete(synchronize_session=False)
            # Delete Historical Sales
            db.query(models.HistoricalSale).filter(models.HistoricalSale.product_id.in_(db.query(models.Product.id).filter(models.Product.merchant_id == current_merchant.id))).delete(synchronize_session=False)
            # Delete Products
            db.query(models.Product).filter(models.Product.merchant_id == current_merchant.id).delete()
            db.commit()

        contents = await csv_file.read()
        filename = csv_file.filename.lower()
        
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents), parse_dates=["date"])
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(contents), parse_dates=["date"])
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV or Excel.")
        
        # Ensure products exist for relational integrity, using names from the data if available
        product_map = {}
        # Get first occurrence of each item to extract name
        unique_products = df.groupby("item").first()
        
        for p_id_raw, row in unique_products.iterrows():
            p_id_str = str(p_id_raw)
            p_name = str(row.get("item_name", f"Product {p_id_str}"))
            
            prod = db.query(Product).filter(Product.item_id == p_id_str, Product.merchant_id == current_merchant.id).first()
            if not prod:
                prod = Product(item_id=p_id_str, name=p_name, merchant_id=current_merchant.id)
                db.add(prod)
                db.commit()
                db.refresh(prod)
            else:
                # Always sync name with the latest uploaded dataset
                if p_name and p_name != prod.name:
                    prod.name = p_name
                    db.commit()
            
            product_map[p_id_str] = prod.id
            
        # Clear existing historical sales for these products to prevent duplicates
        for p_id in product_map.values():
            db.query(HistoricalSale).filter(HistoricalSale.product_id == p_id).delete()
        db.commit()

        # Batch insert into DB
        sales_records = []
        for _, row in df.iterrows():
            sales_records.append(
                HistoricalSale(
                    store_id=row["store"],
                    product_id=product_map[str(row["item"])],
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
    item: str = Form(...),
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
    weather_text = await get_weather_summary(city=city)
    news_text    = await get_retail_news(city=city, item=f"item {summary.get('item', '')}")

    # Optional image (ignored in this phase but prepared for Future Phase 4)
    image_bytes = None
    if image_file and image_file.filename:
        try:
            image_bytes = await image_file.read()
        except Exception:
            image_bytes = None

    # Call Multi-Agent Pipeline
    try:
        report = run_verification_pipeline(
            forecast_summary=summary,
            weather_text=weather_text,
            news_text=news_text
        )
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower() or "rate limit" in str(e).lower():
            raise HTTPException(status_code=429, detail="AI Quota Exceeded (Gemini 2.0 Flash) AND Fallback (OpenRouter) is currently overloaded globally upstream. Please wait a few minutes and try again.")
        raise HTTPException(status_code=500, detail=f"AI Pipeline Error: {str(e)}")

    # Save the agent feedback back to the database
    forecast.gemini_report = report
    db.commit()

    return JSONResponse(content={
        "success":         True,
        "weather_summary": weather_text,
        "news_summary":    news_text,
        "gemini_report":   report,
    })
