import requests
import json
import time

API_URL = "http://localhost:8000"
CSV_PATH = "data/train.csv"

def run_test():
    with open("test_output.txt", "w", encoding="utf-8") as f:
        f.write("🚀 Starting End-to-End Pipeline Test...\n\n")
        
        # --- STAGE 1 & 2: Upload & Train ---
        f.write("⏳ Stage 1 & 2: Uploading CSV and Training Prophet...\n")
        try:
            with open(CSV_PATH, "rb") as csv_f:
                files = {"csv_file": ("train.csv", csv_f, "text/csv")}
                data = {"store": "1", "item": "1"}
                
                t0 = time.time()
                resp = requests.post(f"{API_URL}/train", files=files, data=data, timeout=60)
                resp.raise_for_status()
                train_result = resp.json()
                
                summary = train_result.get("summary", {})
                f.write(f"✅ Training successful! ({round(time.time() - t0, 2)}s)\n")
                f.write(f"   Forecast 7-day Avg: {summary.get('next_7_days_avg')} units\n")
                f.write(f"   Trend: {summary.get('trend').capitalize()}\n\n")
                
        except Exception as e:
            f.write(f"❌ Training Failed: {e}\n")
            return

        # --- STAGE 3 & 4: Context & Gemini ---
        f.write("⏳ Stage 3 & 4: Fetching Context and Calling Gemini 2.0 Flash...\n")
        try:
            analyze_data = {
                "forecast_summary": json.dumps(summary),
                "city": "New York"
            }
            
            t0 = time.time()
            resp = requests.post(f"{API_URL}/analyze", data=analyze_data, timeout=120)
            resp.raise_for_status()
            analyze_result = resp.json()
            
            f.write(f"✅ Analysis successful! ({round(time.time() - t0, 2)}s)\n")
            f.write(f"\n🌤 Weather Fetched:\n{analyze_result.get('weather_summary', '')[:150]}...\n\n")
            f.write(f"📰 News Fetched:\n{analyze_result.get('news_summary', '')[:150]}...\n\n")
            
            f.write("🤖 Gemini 2.0 Flash Report Snapshot:\n")
            report = analyze_result.get("gemini_report", "")
            f.write("-" * 50 + "\n")
            f.write(f"{report[:1000]}...\n[Report Truncated]\n")
            f.write("-" * 50 + "\n")
            
        except Exception as e:
            f.write(f"❌ Analysis Failed: {e}\n")

if __name__ == "__main__":
    run_test()
    print("Test finished - results written to test_output.txt")
