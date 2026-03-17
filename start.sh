#!/bin/bash
# start.sh – Boot script for Docker / Google Cloud Run container.
# Cloud Run injects $PORT for the public-facing port (default 8080).
# FastAPI runs internally on port 8000; Streamlit binds to $PORT.

set -e

# Cloud Run sets $PORT; fall back to 8080 for local Docker runs
STREAMLIT_PORT="${PORT:-8080}"

echo "🚀 Starting FastAPI backend on port 8000..."
uvicorn api:app --host 0.0.0.0 --port 8000 &

echo "🌐 Starting Streamlit frontend on port ${STREAMLIT_PORT}..."
exec streamlit run app.py \
    --server.port "${STREAMLIT_PORT}" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
