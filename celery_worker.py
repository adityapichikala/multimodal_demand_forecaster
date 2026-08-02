import os
import pandas as pd
from celery import Celery
from database import SessionLocal
from models import HistoricalSale, Forecast
from forecast_model import run_forecast
from dotenv import load_dotenv
from models import ForecastMetrics


load_dotenv()

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("demand_forecaster", broker=redis_url, backend=redis_url)


@celery_app.task(bind=True)
def run_async_forecast(self, store_id: int, product_pk: int):
    """
    Background task to train Prophet on historical sales data.
    """
    db = SessionLocal()
    try:
        # Fetch historical data
        sales = (
            db.query(HistoricalSale)
            .filter(
                HistoricalSale.store_id == store_id,
                HistoricalSale.product_id == product_pk,
            )
            .order_by(HistoricalSale.date)
            .all()
        )

        if not sales:
            return {
                "success": False,
                "error": "No historical data found for this store and product.",
            }

        # Fetch product to log item_id
        from models import Product

        prod = db.query(Product).filter(Product.id == product_pk).first()
        item_id = str(prod.item_id) if prod else str(product_pk)

        # Format into Pandas DataFrame for Prophet
        df = pd.DataFrame(
            [
                {"date": s.date, "store": s.store_id, "item": item_id, "sales": s.sales}
                for s in sales
            ]
        )
        df["date"] = pd.to_datetime(df["date"])

        # Run Prophet
        result = run_forecast(df, store=store_id, item=item_id, periods=7)

        # We only really need to store the summary/charts in the Forecast table
        # For full implementation, we'd store exact numbers. Here we store the JSON summary.
        forecast_record = Forecast(
            product_id=product_pk,
            store_id=store_id,
            forecast_data={
                "summary": result["summary"],
                "last_historical_date": str(df["date"].max()),
            },
        )
        db.add(forecast_record)
        db.commit()
        db.refresh(forecast_record)

        return {
            "success": True,
            "store": store_id,
            "item": item_id,
            "forecast_id": forecast_record.id,
            "summary": result["summary"],
        }

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

try:
    metrics_dict = evaluate_model(model, df, horizon_days=30)
    if metrics_dict:
        db = SessionLocal()
        try:
            db_metrics = ForecastMetrics(
                forecast_id=forecast_id,  # the ID of the just-saved Forecast row
                mae=metrics_dict["mae"],
                rmse=metrics_dict["rmse"],
                mape=metrics_dict["mape"],
                coverage=metrics_dict.get("coverage") or 0.0,
                horizon_days=metrics_dict["horizon_days"],
            )
            db.add(db_metrics)
            db.commit()
        finally:
            db.close()
except Exception as e:
    # Metrics are best-effort — don't fail the entire task if they error
    print(f"[celery_worker] Metrics computation failed (non-fatal): {e}")