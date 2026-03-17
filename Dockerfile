# ───────────────────────────────────────────────────────────────────
# Multimodal Demand Forecaster – Dockerfile
# Runs FastAPI (port 8000) + Streamlit (port 8080) in one container
# ───────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# System dependencies needed for Prophet / PyStan compilation
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpython3-dev \
    build-essential \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Make startup script executable
RUN chmod +x start.sh

# Expose Streamlit port (Cloud Run routes to this)
EXPOSE 8080

# Start both services via shell script
CMD ["./start.sh"]
