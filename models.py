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
    forecast_data = Column(JSON) # Store Prophet output
    gemini_report = Column(JSON) # Store final AI report
    
    product = relationship("Product", back_populates="forecasts")
