import requests
import time
import os

BASE_URL = "http://localhost:8000"
TEST_EMAIL = "evaluator3@example.com"
TEST_PASSWORD = "password123"

print("1. Registering User...")
res = requests.post(f"{BASE_URL}/register", data={"name": "Eval", "email": TEST_EMAIL, "password": TEST_PASSWORD})
if res.status_code not in [200, 400]:
    print(f"Register failed: {res.text}")
    exit(1)

print("2. Logging In...")
res = requests.post(f"{BASE_URL}/token", data={"username": TEST_EMAIL, "password": TEST_PASSWORD})
if not res.ok:
    print(f"Login failed: {res.text}")
    exit(1)
token = res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("3. Uploading Data...")
csv_path = r"c:\Users\adity\OneDrive\Desktop\Github\multimodal_demand_forecaster\data\train.csv"
with open(csv_path, "rb") as f:
    res = requests.post(f"{BASE_URL}/upload-data", headers=headers, files={"csv_file": f})
if not res.ok:
    print(f"Upload failed: {res.text}")
    exit(1)

print("4. Generating Forecast...")
res = requests.post(f"{BASE_URL}/train-async", headers=headers, data={"store": 1, "item": 1})
if not res.ok:
    print(f"Generate forecast failed: {res.text}")
    exit(1)
task_id = res.json()["task_id"]

print("5. Polling Task...")
forecast_id = None
for _ in range(30):
    res = requests.get(f"{BASE_URL}/task/{task_id}", headers=headers)
    data = res.json()
    if data["task_status"] == "SUCCESS":
        forecast_id = data["result"]["forecast_id"]
        break
    elif data["task_status"] == "FAILURE":
        print(f"Task failed: {data.get('error')}")
        exit(1)
    time.sleep(2)

if not forecast_id:
    print("Task timeout.")
    exit(1)

print("6. Requesting AI Analysis (with Fallback)...")
res = requests.post(f"{BASE_URL}/analyze", headers=headers, data={"forecast_id": forecast_id, "city": "New York"})
if not res.ok:
    print(f"Analysis failed: {res.text}")
    exit(1)

print("\n--- AI REPORT ---")
print(res.json()["gemini_report"])
print("--- END REPORT ---")
print("SUCCESS!")
