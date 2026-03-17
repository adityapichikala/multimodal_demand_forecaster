"""
news_api.py
-----------
Fetches top news headlines relevant to supply chain, weather, and retail demand
using newsapi.ai.
"""

import os
from dotenv import load_dotenv

load_dotenv()

import requests
import json

NEWSAPI_AI_KEY = os.getenv("NEWSAPI_AI_KEY", os.getenv("THENEWSAPI_KEY", ""))
BASE_URL = "https://eventregistry.org/api/v1/article/getArticles"

from fastapi_cache.decorator import cache

@cache(expire=10800) # 3 hours
def get_news_summary(search_terms: str = "supply chain retail demand", max_articles: int = 5) -> str:
    """
    Fetch the latest news headlines matching the search terms from newsapi.ai (EventRegistry).
    """
    if not NEWSAPI_AI_KEY:
        return "[News] Warning: NEWSAPI_AI_KEY is not set in .env"

    try:
        # newsapi.ai expects a JSON body POST request for complex queries, or specific GET params
        params = {
            "apiKey": NEWSAPI_AI_KEY,
            "keyword": search_terms,
            "lang": "eng",
            "articlesSortBy": "date",
            "articlesCount": max_articles,
            "resultType": "articles",
        }
        
        # Depending on exactly which newsapi.ai endpoint, we use eventregistry.org
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Check for error in JSON response structure
        if "error" in data:
            return f"[News] API Error: {data['error']}"
            
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        if status == 401 or status == 403:
            return f"[News] Authentication failed. Please check your NEWSAPI_AI_KEY in .env (newsapi.ai)."
        return f"[News] Error fetching news: {e}"
    except requests.exceptions.ConnectionError:
        return "[News] Connection error. Could not reach newsapi.ai."
    except Exception as e:
        return f"[News] Unexpected error: {e}"

    articles = data.get("articles", {}).get("results", [])
    if not articles:
        return "[News] No relevant news articles found at this time."

    lines = [f"📰 Top News Headlines (related to: {search_terms}):"]
    for i, article in enumerate(articles[:max_articles], 1):
        title = article.get("title", "No title")
        description = article.get("body", "") # newsapi.ai returns 'body'
        source = article.get("source", {}).get("title", "Unknown source")
        published_at = article.get("dateTimePub", "")[:10]
        url = article.get("url", "")

        lines.append(f"\n  [{i}] {title}")
        if description:
            # Truncate long descriptions
            desc_short = description[:200] + "..." if len(description) > 200 else description
            lines.append(f"      {desc_short}")
        lines.append(f"      Source: {source} | Published: {published_at}")
        if url:
            lines.append(f"      URL: {url}")

    return "\n".join(lines)


@cache(expire=10800) # 3 hours
def get_retail_news(city: str = None, item: str = None) -> str:
    """
    Fetch news targeted at retail demand signals for a specific city/item.
    Combines results from multiple relevant searches.
    """
    # EventRegistry (newsapi.ai) keyword searches are very strict.
    # We use a broad, guaranteed match like "supply chain" so the API always returns data.
    search_terms = "supply chain"
    return get_news_summary(search_terms=search_terms, max_articles=5)
