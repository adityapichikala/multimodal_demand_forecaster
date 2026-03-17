"""
weather_api.py
--------------
Fetches 5-day / 3-hour weather forecasts from WeatherAPI.com and returns
a human-readable summary string for use by the Gemini agent.
"""

import os
from dotenv import load_dotenv

load_dotenv()

import requests

# Using WeatherAPI.com as requested
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY", os.getenv("OPENWEATHER_API_KEY", ""))
BASE_URL = "https://api.weatherapi.com/v1/forecast.json"


def get_weather_summary(city: str = "New York") -> str:
    """
    Fetch a 5-day weather forecast for the given city from WeatherAPI.com
    and return a concise formatted text summary.
    """
    if not WEATHERAPI_KEY:
        return "[Weather] Warning: WEATHERAPI_KEY is not set in .env"

    try:
        params = {
            "key": WEATHERAPI_KEY,
            "q": city,
            "days": 5,
            "aqi": "no",
            "alerts": "yes",
        }
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        if status == 401 or status == 403:
            return f"[Weather] Authentication failed. Please check your WEATHERAPI_KEY in .env (weatherapi.com)."
        return f"[Weather] Error fetching data for '{city}': {e}"
    except requests.exceptions.ConnectionError:
        return f"[Weather] Connection error. Could not reach WeatherAPI.com."
    except Exception as e:
        return f"[Weather] Unexpected error: {e}"

    location = data.get("location", {})
    city_name = location.get("name", city)
    country = location.get("country", "")
    forecasts = data.get("forecast", {}).get("forecastday", [])

    if not forecasts:
        return f"[Weather] No forecast data available for {city}."

    lines = [f"📍 Weather Forecast for {city_name}, {country}:"]
    temps_max = []
    temps_min = []
    conditions = []

    for day in forecasts:
        date = day.get("date", "")
        day_data = day.get("day", {})
        
        max_temp = day_data.get("maxtemp_c", 0)
        min_temp = day_data.get("mintemp_c", 0)
        desc = day_data.get("condition", {}).get("text", "Unknown")
        max_wind = day_data.get("maxwind_kph", 0)
        
        temps_max.append(max_temp)
        temps_min.append(min_temp)
        conditions.append(desc)
        
        lines.append(
            f"  • {date} | High: {max_temp}°C | Low: {min_temp}°C | "
            f"Wind max: {max_wind} km/h | {desc}"
        )

    avg_max = round(sum(temps_max) / len(temps_max), 1)
    avg_min = round(sum(temps_min) / len(temps_min), 1)

    lines.append(f"\n📊 Summary: Avg High {avg_max}°C | Avg Low {avg_min}°C")
    lines.append(f"🌤  Dominant Conditions: {', '.join(set(conditions))}")

    # Process alerts mapping from WeatherAPI
    api_alerts = data.get("alerts", {}).get("alert", [])
    
    heuristics_alerts = []
    if max(temps_max) > 35:
        heuristics_alerts.append("⚠️  HEAT ALERT: Temperatures exceeding 35°C expected.")
    if min(temps_min) < 0:
        heuristics_alerts.append("⚠️  COLD ALERT: Sub-zero temperatures expected.")
    if any("storm" in c.lower() or "thunder" in c.lower() for c in conditions):
        heuristics_alerts.append("⚠️  STORM ALERT: Thunderstorms/storms in the forecast.")
    if any("heavy rain" in c.lower() for c in conditions):
        heuristics_alerts.append("⚠️  HEAVY RAIN: Possible supply chain disruptions.")

    if api_alerts or heuristics_alerts:
        lines.append("\n🚨 Weather Alerts:")
        for a in api_alerts:
            lines.append(f"  [OFFICIAL] {a.get('headline', 'Weather Alert')}")
        for a in heuristics_alerts:
            lines.append(f"  {a}")

    return "\n".join(lines)
