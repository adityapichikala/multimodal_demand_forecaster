# ───────────────────────────────────────────────────────────────────
# Multimodal Demand Forecaster – Backend Dockerfile
# Serves FastAPI (api service) and Celery (worker service) via
# docker-compose.yml – the CMD is overridden per service.
# ───────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# System dependencies for Prophet / PyStan compilation
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpython3-dev \
    build-essential \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Default command (overridden in docker-compose per service)
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
