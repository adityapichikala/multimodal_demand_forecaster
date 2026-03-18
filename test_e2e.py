"""
test_e2e.py
-----------
End-to-end integration test for the v2 Enterprise Pipeline.
Tests the full flow: Register → Login → Upload CSV → Train Async → Poll → Analyze
"""
import os
import time
import requests
import pytest

API_URL = os.getenv("API_URL", "http://localhost:8000")
CSV_PATH = "data/train.csv"
TEST_EMAIL = "test_e2e@nexus.ai"
TEST_PASSWORD = "supersecretpassword"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_token(session: requests.Session) -> str:
    # Try to register first (idempotent: ignore 400 if already exists)
    session.post(f"{API_URL}/register", data={
        "email": TEST_EMAIL, "password": TEST_PASSWORD, "name": "E2E Test Merchant"
    })
    resp = session.post(f"{API_URL}/token", data={
        "username": TEST_EMAIL, "password": TEST_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_health():
    resp = requests.get(f"{API_URL}/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_full_pipeline():
    session = requests.Session()

    # Step 1: Authenticate
    token = get_token(session)
    headers = {"Authorization": f"Bearer {token}"}

    # Step 2: Upload historical CSV data
    assert os.path.exists(CSV_PATH), f"CSV not found at {CSV_PATH}"
    with open(CSV_PATH, "rb") as f:
        resp = session.post(
            f"{API_URL}/upload-data",
            headers=headers,
            files={"csv_file": ("train.csv", f, "text/csv")},
            timeout=60
        )
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    assert resp.json()["success"] is True

    # Step 3: Kick off asynchronous Prophet training
    resp = session.post(
        f"{API_URL}/train-async",
        headers=headers,
        data={"store": "1", "item": "1"},
        timeout=30
    )
    assert resp.status_code == 202, f"train-async failed: {resp.text}"
    task_id = resp.json()["task_id"]
    assert task_id, "No task_id returned"

    # Step 4: Poll task status until SUCCESS or timeout
    forecast_id = None
    for _ in range(30):  # Max 60 seconds (30 * 2s)
        time.sleep(2)
        resp = session.get(f"{API_URL}/task/{task_id}", headers=headers, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        status = data.get("task_status")
        if status == "SUCCESS":
            forecast_id = data["result"]["forecast_id"]
            break
        elif status == "FAILURE":
            pytest.fail(f"Celery task failed: {data.get('error')}")

    assert forecast_id is not None, "Task never completed within timeout"

    # Step 5: Run AI multi-agent analysis using forecast_id
    resp = session.post(
        f"{API_URL}/analyze",
        headers=headers,
        data={"forecast_id": str(forecast_id), "city": "New York"},
        timeout=120
    )
    assert resp.status_code == 200, f"Analyze failed: {resp.text}"
    result = resp.json()
    assert result.get("success") is True
    assert result.get("gemini_report"), "No AI report returned"

    print(f"\n✅ Full pipeline success! Forecast ID: {forecast_id}")
    print(f"   AI Report snippet: {result['gemini_report'][:200]}...")
