import os
from dotenv import load_dotenv
import requests

load_dotenv()

NEWSAPI_AI_KEY = os.getenv("NEWSAPI_AI_KEY", os.getenv("THENEWSAPI_KEY", ""))
BASE_URL = "https://eventregistry.org/api/v1/article/getArticles"

terms_to_test = [
    "retail",
    "supply",
    "supply chain",
    "Amazon",
    "business"
]

def test_news():
    for term in terms_to_test:
        print(f"\nTesting term: '{term}'")
        params = {
            "apiKey": NEWSAPI_AI_KEY,
            "keyword": term,
            "lang": "eng",
            "articlesCount": 2,
            "resultType": "articles",
        }
        try:
            resp = requests.get(BASE_URL, params=params, timeout=10)
            data = resp.json()
            articles = data.get("articles", {}).get("results", [])
            print(f"  Found {len(articles)} articles.")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    with open("news_test_output.txt", "w", encoding="utf-8") as f:
        import sys
        sys.stdout = f
        test_news()
