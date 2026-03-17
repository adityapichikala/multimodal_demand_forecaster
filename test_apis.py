import os
from dotenv import load_dotenv

load_dotenv()

from weather_api import get_weather_summary
from news_api import get_retail_news

with open("test_output.txt", "w", encoding="utf-8") as f:
    f.write("=== Testing WeatherAPI.com ===\n")
    weather = get_weather_summary("New York")
    f.write(weather + "\n\n")

    f.write("=== Testing newsapi.ai ===\n")
    news = get_retail_news("New York", "item 1")
    f.write(news + "\n")

print("API results written to test_output.txt")
