"""
gemini_agent.py
---------------
Multimodal reasoning agent using Google Gemini 2.0 Flash.
Uses the new `google-genai` SDK (google.genai.Client).
Combines demand forecast, weather, and news signals to generate
a structured narrative demand report. Supports optional image input
(weather map / news screenshot) via PIL.Image.
"""

import os
import io
from dotenv import load_dotenv

load_dotenv()

from google import genai
from PIL import Image

MODEL_NAME = "gemini-2.0-flash"

# Client is instantiated once at module level — safe for Cloud Run (stateless)
_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def build_prompt(forecast_summary: dict, weather_text: str, news_text: str) -> str:
    """Build the structured prompt sent to Gemini."""
    store = forecast_summary.get("store", "N/A")
    item = forecast_summary.get("item", "N/A")
    avg_demand = forecast_summary.get("next_7_days_avg", "N/A")
    max_demand = forecast_summary.get("max_demand", "N/A")
    min_demand = forecast_summary.get("min_demand", "N/A")
    max_day = forecast_summary.get("max_day", "N/A")
    min_day = forecast_summary.get("min_day", "N/A")
    trend = forecast_summary.get("trend", "stable")
    last_7_avg = forecast_summary.get("last_7_days_avg", "N/A")
    forecast_dates = forecast_summary.get("forecast_dates", [])
    forecast_values = forecast_summary.get("forecast_values", [])

    daily_breakdown = ""
    if forecast_dates and forecast_values:
        daily_breakdown = "\n".join(
            f"  {date}: {val} units"
            for date, val in zip(forecast_dates, forecast_values)
        )

    prompt = f"""You are an expert supply chain analyst and demand forecaster.
Analyze the following demand forecast, weather data, and news headlines for a retail store.
Generate a structured, professional demand forecast report.

═══════════════════════════════════════════════════════════
DEMAND FORECAST DATA
═══════════════════════════════════════════════════════════
Store ID      : {store}
Product/Item  : Item {item}
Last 7-day avg (historical): {last_7_avg} units/day
Predicted Avg Demand Next 7 Days: {avg_demand} units/day
Trend         : {trend.upper()}

Peak Demand   : {max_demand} units on {max_day}
Lowest Demand : {min_demand} units on {min_day}

Daily Breakdown:
{daily_breakdown}

═══════════════════════════════════════════════════════════
WEATHER FORECAST
═══════════════════════════════════════════════════════════
{weather_text}

═══════════════════════════════════════════════════════════
RELEVANT NEWS HEADLINES
═══════════════════════════════════════════════════════════
{news_text}

═══════════════════════════════════════════════════════════
YOUR TASK
═══════════════════════════════════════════════════════════
Based on ALL the above signals, write a structured demand forecast report with these exact sections:

**DEMAND FORECAST REPORT**

Product       : Item {item}
Store         : Store {store}

Predicted Demand (Next 7 Days): {avg_demand} units/day average

**Explanation:**
[2-4 sentences explaining WHY demand is expected to be {trend}. Reference specific weather conditions,
news events, and historical patterns. Be concrete and analytical.]

**Key Risk Factors:**
[Bullet list of 2-3 specific risks that could cause demand to deviate up or down]

**Recommendation:**
[1-2 actionable recommendations for inventory management, e.g. "Increase stock by X%" or
"Maintain current inventory levels as demand is stable"]

**Confidence Level:** [High / Medium / Low with one sentence justification]

Keep the report professional, specific, and actionable. Do not use vague or generic statements.
"""
    return prompt


def generate_forecast_report(
    forecast_summary: dict,
    weather_text: str,
    news_text: str,
    image_bytes: bytes = None,
) -> str:
    """
    Call Gemini 2.0 Flash with the combined forecast, weather, and news context.
    Optionally includes an image (weather map or news screenshot) via PIL.Image.

    Parameters
    ----------
    forecast_summary : dict from forecast_model.run_forecast()
    weather_text     : formatted weather string from weather_api
    news_text        : formatted news string from news_api
    image_bytes      : optional raw image bytes (PNG/JPG/WEBP)

    Returns
    -------
    str: The Gemini-generated demand forecast report
    """
    prompt_text = build_prompt(forecast_summary, weather_text, news_text)

    # Build contents list — text always first, PIL image appended if provided
    contents = [prompt_text]

    if image_bytes:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            contents.append(image)
        except Exception as e:
            # Image failed to parse — proceed text-only, don't crash
            print(f"[gemini_agent] Image parse error (proceeding without image): {e}")

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
        )
        return response.text
    except Exception as e:
        store = forecast_summary.get("store")
        item = forecast_summary.get("item")
        avg = forecast_summary.get("next_7_days_avg")
        trend = forecast_summary.get("trend", "stable").upper()
        return (
            f"[Gemini Error] Failed to generate report: {e}\n\n"
            f"Fallback Summary:\n"
            f"Store {store} | Item {item}\n"
            f"Predicted 7-day avg demand: {avg} units\n"
            f"Trend: {trend}"
        )
