# 📦 Multimodal Demand Forecaster

An end-to-end AI-powered supply chain and retail demand forecasting application. Combines historical sales data with real-time weather and news signals, uses **Facebook Prophet** for time-series forecasting, and generates a narrative analysis report with **Google Gemini 2.0 Flash**.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Streamlit UI  (app.py)                     │
│  CSV Upload │ Store/Item Selector │ Charts │ Report     │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP POST /forecast
┌──────────────────────▼──────────────────────────────────┐
│              FastAPI Backend  (api.py)                  │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ forecast_   │  │ weather_     │  │ news_api.py   │  │
│  │ model.py    │  │ api.py       │  │ (TheNewsAPI)  │  │
│  │ (Prophet)   │  │ (OpenWeather)│  └───────┬───────┘  │
│  └──────┬──────┘  └──────┬───────┘          │          │
│         └────────────────┴──────────────────┘          │
│                           │                             │
│                  ┌────────▼────────┐                   │
│                  │ gemini_agent.py │                   │
│                  │ Gemini 2.0 Flash│                   │
│                  └────────┬────────┘                   │
└───────────────────────────┼─────────────────────────────┘
                            │ Demand Report JSON
                    Streamlit Dashboard
```

---

## 📁 Project Structure

```
multimodal_demand_forecaster/
├── app.py                  # Streamlit UI
├── api.py                  # FastAPI backend
├── forecast_model.py       # Prophet time-series model
├── weather_api.py          # OpenWeatherMap integration
├── news_api.py             # TheNewsAPI integration
├── gemini_agent.py         # Gemini 2.0 Flash reasoning
├── data/
│   └── train.csv           # Sample dataset
├── requirements.txt
├── Dockerfile
├── start.sh
└── README.md
```

---

## 🚀 Quick Start (Local)

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

> **Note:** Prophet requires a C++ compiler. On Windows, install [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/).

### 2. Start the FastAPI Backend

```bash
uvicorn api:app --reload --port 8000
```

The API docs will be available at: `http://localhost:8000/docs`

### 3. Start the Streamlit Frontend

Open a **second terminal** and run:

```bash
streamlit run app.py
```

The UI will open at: `http://localhost:8501`

### 4. Use the App

1. Upload `data/train.csv` (or the full Kaggle dataset) using the sidebar
2. Select **Store** and **Item** from the dropdowns
3. Enter your **City** for weather context
4. Optionally upload a weather map or news screenshot
5. Click **🚀 Generate Forecast**

---

## 🤖 AI & API Keys

| Service | Key Location |
|---|---|
| Google Gemini 2.0 Flash | `gemini_agent.py` → `GEMINI_API_KEY` |
| OpenWeatherMap | `weather_api.py` → `OPENWEATHER_API_KEY` |
| TheNewsAPI | `news_api.py` → `THENEWSAPI_KEY` |

> **Security Tip:** For production, move API keys to environment variables and use a `.env` file.

---

## 🐳 Docker Deployment

### Build the Image

```bash
docker build -t multimodal-demand-forecaster .
```

### Run the Container

```bash
docker run -p 8080:8080 multimodal-demand-forecaster
```

Open `http://localhost:8080`

---

## ☁️ Google Cloud Run Deployment

### 1. Authenticate & Configure

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 2. Build & Push to Artifact Registry

```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/demand-forecaster
```

### 3. Deploy to Cloud Run

```bash
gcloud run deploy demand-forecaster \
  --image gcr.io/YOUR_PROJECT_ID/demand-forecaster \
  --platform managed \
  --region us-central1 \
  --port 8080 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2
```

> Cloud Run will return a public URL on deployment.

---

## 📊 Sample Dataset

The included `data/train.csv` follows the [Kaggle Store Item Demand Forecasting](https://www.kaggle.com/competitions/demand-forecasting-kernels-only) format:

| Column | Type | Description |
|--------|------|-------------|
| `date` | date | Sales date |
| `store` | int | Store ID |
| `item` | int | Product ID |
| `sales` | int | Units sold |

---

## 📈 Output Example

```
DEMAND FORECAST REPORT

Product       : Item 1
Store         : Store 1

Predicted Demand (Next 7 Days): 68.4 units/day average

Explanation:
Demand is expected to increase due to rising temperatures and a heatwave
alert issued for the New York region. Historically, similar conditions
have driven a 12-15% uplift in demand for this item category.

Key Risk Factors:
• Supply chain disruptions if extreme weather affects logistics
• Competitor promotions reducing market share
• Weekend demand spike exceeding forecast upper bound

Recommendation:
Increase inventory by approximately 18% for the upcoming week.
Prioritize replenishment orders by Day 3 of the forecast window.

Confidence Level: High — Strong alignment between forecast trend,
weather signals, and recent news coverage.
```

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Forecasting | Facebook Prophet |
| LLM | Google Gemini 2.0 Flash |
| Backend | FastAPI + Uvicorn |
| Frontend | Streamlit + Plotly |
| Weather | OpenWeatherMap API |
| News | TheNewsAPI |
| Containerization | Docker |
| Cloud | Google Cloud Run |

---

## 📄 License

MIT License — see [LICENSE](LICENSE)
