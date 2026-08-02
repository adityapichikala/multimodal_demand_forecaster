from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Date, JSON
from sqlalchemy.orm import relationship
from database import Base
import datetime


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    products = relationship("Product", back_populates="merchant")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(String, index=True)
    name = Column(String, index=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"))

    merchant = relationship("Merchant", back_populates="products")
    historical_sales = relationship("HistoricalSale", back_populates="product")
    forecasts = relationship("Forecast", back_populates="product")


class HistoricalSale(Base):
    __tablename__ = "historical_sales"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    store_id = Column(Integer, index=True)
    date = Column(Date, index=True)
    sales = Column(Float)

    product = relationship("Product", back_populates="historical_sales")


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    store_id = Column(Integer, index=True)
    forecast_date = Column(DateTime, default=datetime.datetime.utcnow)
    forecast_data = Column(JSON)  # Store Prophet output
    gemini_report = Column(JSON)  # Store final AI report
    metrics = relationship("ForecastMetrics", back_populates="forecast", uselist=False)
    product = relationship("Product", back_populates="forecasts")

class ForecastMetrics(Base):
    """
    Stores Prophet cross-validation accuracy metrics for a forecast.
    Created once per forecast run by the Celery worker after training.
    """
    __tablename__ = "forecast_metrics"

    id = Column(Integer, primary_key=True, index=True)
    forecast_id = Column(Integer, ForeignKey("forecasts.id"), nullable=False, unique=True)
    mae = Column(Float, nullable=False, comment="Mean Absolute Error")
    rmse = Column(Float, nullable=False, comment="Root Mean Squared Error")
    mape = Column(Float, nullable=False, comment="Mean Absolute Percentage Error (%)")
    coverage = Column(Float, nullable=False, comment="% of actuals within yhat_lower/upper interval")
    horizon_days = Column(Integer, nullable=False, default=30)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship back to parent forecast
    forecast = relationship("Forecast", back_populates="metrics")