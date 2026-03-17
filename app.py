"""
app.py
------
Streamlit UI for the Multimodal Demand Forecaster.

Strict 4-stage execution flow:
  Stage 1 → Wait for CSV upload (app halts here until CSV is present)
  Stage 2 → User selects store/item, clicks "Train & Forecast"
             Prophet trains on-the-fly; forecast stored in st.session_state
             (no retraining on subsequent button clicks)
  Stage 3 → Forecast chart shown; weather + news auto-fetched and cached
             in session_state; optional image upload appears
  Stage 4 → "Analyze with Gemini" button → sends forecast + weather +
             news + image to Gemini 2.0 Flash; displays full report
"""

import hashlib
import io
import json

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Multimodal Demand Forecaster",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE_URL = "http://localhost:8000"

# ─── Session State Init ───────────────────────────────────────────────────────
# All pipeline state is stored here so widget interactions never re-trigger
# expensive operations (Prophet training, API fetches).
for key, default in {
    "forecast_data":    None,   # result from /train
    "forecast_key":     None,   # hash to detect input changes
    "context_data":     None,   # result from weather + news
    "context_key":      None,   # hash to detect city changes
    "gemini_report":    None,   # final Gemini text
    "gemini_key":       None,   # hash to detect analysis input changes
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ─── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 1.8rem 2.5rem; border-radius: 16px; margin-bottom: 1.5rem;
        text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }
    .main-header h1 { color: #e2e8f0; font-size: 2.2rem; font-weight: 700; margin: 0; }
    .main-header p  { color: #94a3b8; font-size: 0.95rem; margin: 0.4rem 0 0; }
    .main-header span { color: #38bdf8; }

    .stage-header {
        display: flex; align-items: center; gap: 0.75rem;
        margin: 1.5rem 0 0.75rem;
    }
    .stage-badge {
        background: linear-gradient(135deg, #1d4ed8, #7c3aed);
        color: white; border-radius: 99px; padding: 2px 12px;
        font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em;
    }
    .stage-title { color: #e2e8f0; font-size: 1.1rem; font-weight: 600; }

    .metric-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid #334155; border-radius: 12px;
        padding: 1.1rem 1.4rem; text-align: center;
    }
    .metric-card .mv { font-size: 1.8rem; font-weight: 700; color: #38bdf8; }
    .metric-card .ml { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase;
                       letter-spacing: 0.05em; margin-top: 0.2rem; }
    .metric-card .md { font-size: 0.8rem; margin-top: 0.25rem; }
    .delta-up   { color: #34d399; }
    .delta-down { color: #f87171; }
    .delta-stable { color: #fbbf24; }

    .report-card {
        background: linear-gradient(135deg, #0f172a, #1e293b);
        border: 1px solid #1e40af; border-radius: 16px; padding: 2rem;
        color: #e2e8f0; line-height: 1.8;
        box-shadow: 0 8px 32px rgba(30,64,175,0.15);
    }
    .ctx-card {
        background: #1e293b; border: 1px solid #334155; border-radius: 12px;
        padding: 1.25rem; font-size: 0.8rem; color: #cbd5e1;
        white-space: pre-wrap; max-height: 260px; overflow-y: auto;
    }

    .stButton > button {
        background: linear-gradient(135deg, #1d4ed8, #7c3aed);
        color: white; border: none; border-radius: 10px;
        padding: 0.7rem 2rem; font-size: 0.95rem; font-weight: 600;
        width: 100%; transition: all 0.2s ease;
    }
    .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(29,78,216,0.4); }
    .stButton > button:disabled { opacity: 0.45; transform: none; }

    div[data-testid="stSidebarContent"] { background: #0f172a; }
    .stSelectbox label, .stTextInput label, .stFileUploader label {
        color: #94a3b8 !important; font-size: 0.83rem !important; font-weight: 500 !important;
    }
</style>
""", unsafe_allow_html=True)


# ─── Header ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>📦 Multimodal Demand <span>Forecaster</span></h1>
    <p>Upload CSV → Train Prophet → Fetch context → Analyze with Gemini 2.0 Flash</p>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — CSV Upload
# ══════════════════════════════════════════════════════════════════════════════
def stage_badge(n, label):
    st.markdown(f"""
    <div class="stage-header">
        <span class="stage-badge">STEP {n}</span>
        <span class="stage-title">{label}</span>
    </div>""", unsafe_allow_html=True)

stage_badge(1, "Upload Sales CSV")

csv_file = st.file_uploader(
    "Upload your sales dataset (columns: date, store, item, sales)",
    type=["csv"],
    key="csv_uploader",
    help="Kaggle Store Item Demand format",
)

# ── HALT HERE until CSV is present ───────────────────────────────────────────
if csv_file is None:
    st.info("👆 Upload a CSV file above to begin. You can use **data/train.csv** included in the project.")
    st.stop()

# CSV is present — parse for selectors
try:
    df_meta = pd.read_csv(io.BytesIO(csv_file.getvalue()), parse_dates=["date"])
    df_meta.columns = df_meta.columns.str.lower()
    stores = sorted(df_meta["store"].unique().tolist())
    items  = sorted(df_meta["item"].unique().tolist())
except Exception as e:
    st.error(f"❌ Failed to read CSV: {e}")
    st.stop()

st.success(f"✅ **{len(df_meta):,} rows** loaded — {len(stores)} stores, {len(items)} items "
           f"| Date range: {df_meta['date'].min().date()} → {df_meta['date'].max().date()}")


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 — Train Prophet & Generate Forecast
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
stage_badge(2, "Train Model & Generate Forecast")

col_s, col_i, col_btn = st.columns([1, 1, 2])
with col_s:
    store_id = st.selectbox("Store", stores, index=0, key="store_sel")
with col_i:
    item_id = st.selectbox("Item", items, index=0, key="item_sel")
with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    train_btn = st.button("⚡ Train & Forecast", key="train_btn")

# Compute a cache key — only retrain if store/item/CSV actually changed
csv_hash   = hashlib.md5(csv_file.getvalue()).hexdigest()[:8]
train_key  = f"{csv_hash}-s{store_id}-i{item_id}"

if train_btn and st.session_state.forecast_key != train_key:
    with st.spinner("🔄 Training Prophet model on your data…"):
        try:
            resp = requests.post(
                f"{API_BASE_URL}/train",
                data={"store": str(store_id), "item": str(item_id)},
                files={"csv_file": (csv_file.name, csv_file.getvalue(), "text/csv")},
                timeout=120,
            )
            resp.raise_for_status()
            st.session_state.forecast_data = resp.json()
            st.session_state.forecast_key  = train_key
            # Clear downstream state when inputs change
            st.session_state.context_data  = None
            st.session_state.context_key   = None
            st.session_state.gemini_report  = None
            st.session_state.gemini_key     = None
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot reach the FastAPI backend. Run: `uvicorn api:app --port 8000`")
            st.stop()
        except requests.exceptions.Timeout:
            st.error("⏱️ Training timed out — try a smaller date range or fewer stores/items.")
            st.stop()
        except requests.exceptions.HTTPError as e:
            st.error(f"❌ API error {e.response.status_code}: {e.response.text}")
            st.stop()

# ── HALT HERE until forecast is ready ────────────────────────────────────────
if st.session_state.forecast_data is None:
    st.info("👆 Select a **Store** and **Item**, then click **Train & Forecast**.")
    st.stop()

# ── Render forecast ───────────────────────────────────────────────────────────
fdata   = st.session_state.forecast_data
summary = fdata["summary"]
trend   = summary.get("trend", "stable")

st.success("✅ Prophet model trained successfully!")

# KPI cards
k1, k2, k3, k4 = st.columns(4)
td_map = {"increasing": ("delta-up", "↑"), "decreasing": ("delta-down", "↓"), "stable": ("delta-stable", "→")}
td_cls, td_icon = td_map.get(trend, ("delta-stable", "→"))
for col, val, label, extra in [
    (k1, f"{summary['next_7_days_avg']} units", "Avg Demand / Day",
         f'<span class="{td_cls}">{td_icon} {trend.capitalize()}</span>'),
    (k2, f"{summary['max_demand']} units",      "Peak Demand",
         f'<small style="color:#64748b">{summary["max_day"]}</small>'),
    (k3, f"{summary['min_demand']} units",      "Lowest Demand",
         f'<small style="color:#64748b">{summary["min_day"]}</small>'),
    (k4, f"{summary['last_7_days_avg']} units", "Historical Avg (7d)",
         '<small style="color:#64748b">before forecast window</small>'),
]:
    with col:
        st.markdown(f"""
        <div class="metric-card">
            <div class="mv">{val}</div>
            <div class="ml">{label}</div>
            <div class="md">{extra}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Plotly chart
hist  = fdata["history_chart"]
fcast = fdata["forecast_chart"]
fig   = make_subplots(specs=[[{"secondary_y": False}]])

fig.add_trace(go.Scatter(
    x=hist["dates"], y=hist["sales"],
    name="Historical Sales", mode="lines+markers",
    line=dict(color="#38bdf8", width=2), marker=dict(size=4),
))
fig.add_trace(go.Scatter(
    x=fcast["dates"] + fcast["dates"][::-1],
    y=fcast["yhat_upper"] + fcast["yhat_lower"][::-1],
    fill="toself", fillcolor="rgba(167,139,250,0.15)",
    line=dict(color="rgba(0,0,0,0)"), name="Confidence Interval",
))
fig.add_trace(go.Scatter(
    x=fcast["dates"], y=fcast["yhat"],
    name="Forecasted Demand", mode="lines+markers",
    line=dict(color="#a78bfa", width=3, dash="dash"),
    marker=dict(size=8, symbol="diamond"),
))
fig.update_layout(
    paper_bgcolor="#0f172a", plot_bgcolor="#1e293b",
    font=dict(color="#94a3b8", family="Inter"),
    legend=dict(bgcolor="#1e293b", bordercolor="#334155"),
    xaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#64748b")),
    yaxis=dict(gridcolor="#334155", tickfont=dict(color="#64748b"), title="Units"),
    margin=dict(l=50, r=20, t=20, b=40), height=360, hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)

# 7-day table
col_tbl, _ = st.columns([1, 1])
with col_tbl:
    fc_table = pd.DataFrame({
        "Date":                    summary["forecast_dates"],
        "Predicted Demand (units)": summary["forecast_values"],
    })
    fc_table.index = range(1, 8)
    st.dataframe(fc_table, use_container_width=True, height=282)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — Gather Context (weather + news auto-fetch, optional image)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
stage_badge(3, "Gather Context (Weather, News & Optional Image)")

city = st.text_input("City for weather forecast", value="New York",
                     placeholder="e.g. London, Mumbai", key="city_input")

ctx_key = f"{train_key}-{city}"

# Auto-fetch weather + news when context key changes (or on first load after forecast)
if st.session_state.context_key != ctx_key:
    with st.spinner("🌤 Fetching weather and news context…"):
        try:
            resp = requests.post(
                f"{API_BASE_URL}/analyze",
                data={
                    "forecast_summary": json.dumps(summary),
                    "city": city,
                },
                timeout=30,
            )
            resp.raise_for_status()
            ctx = resp.json()
            # Store weather + news (no image yet, no Gemini yet)
            st.session_state.context_data = ctx
            st.session_state.context_key  = ctx_key
            st.session_state.gemini_report = None  # reset Gemini if city changed
            st.session_state.gemini_key    = None
        except Exception as e:
            st.warning(f"⚠️ Could not fetch weather/news context: {e}")

# Show the fetched context
if st.session_state.context_data:
    ctx = st.session_state.context_data
    with st.expander("🌤 Weather Data", expanded=False):
        st.markdown(f'<div class="ctx-card">{ctx.get("weather_summary","N/A")}</div>',
                    unsafe_allow_html=True)
    with st.expander("📰 News Headlines", expanded=False):
        st.markdown(f'<div class="ctx-card">{ctx.get("news_summary","N/A")}</div>',
                    unsafe_allow_html=True)

# Optional image upload (shown only after forecast is ready)
st.markdown("**Optional: Upload a weather map or news screenshot for Gemini to analyze**")
image_file = st.file_uploader(
    "Upload image (PNG / JPG / WEBP)",
    type=["png", "jpg", "jpeg", "webp"],
    key="img_uploader",
    help="Gemini 2.0 Flash will include this image in its multimodal analysis",
)
if image_file:
    st.image(image_file, caption="Uploaded image — will be sent to Gemini", width=400)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — Gemini 2.0 Flash Analysis
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
stage_badge(4, "Analyze with Gemini 2.0 Flash")

img_hash    = hashlib.md5(image_file.getvalue()).hexdigest()[:6] if image_file else "none"
gemini_key  = f"{ctx_key}-{img_hash}"
analyze_btn = st.button("🤖 Analyze with Gemini 2.0 Flash", key="analyze_btn")

if analyze_btn and st.session_state.gemini_key != gemini_key:
    with st.spinner("🤖 Gemini 2.0 Flash is analyzing forecast, weather, and news…"):
        try:
            form_data = {
                "forecast_summary": json.dumps(summary),
                "city": city,
            }
            files = {}
            if image_file:
                files["image_file"] = (image_file.name, image_file.getvalue(), image_file.type)

            resp = requests.post(
                f"{API_BASE_URL}/analyze",
                data=form_data,
                files=files if files else None,
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
            st.session_state.gemini_report = result.get("gemini_report", "No report returned.")
            st.session_state.gemini_key    = gemini_key
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot reach the FastAPI backend.")
            st.stop()
        except requests.exceptions.Timeout:
            st.error("⏱️ Gemini request timed out. Please try again.")
            st.stop()
        except requests.exceptions.HTTPError as e:
            st.error(f"❌ API error {e.response.status_code}: {e.response.text}")
            st.stop()

# Render Gemini report (persisted in session_state)
if st.session_state.gemini_report:
    st.success("✅ Gemini analysis complete!")
    st.markdown("### 📋 Demand Forecast Report")
    report_html = st.session_state.gemini_report.replace("\n", "<br>")
    st.markdown(f'<div class="report-card">{report_html}</div>', unsafe_allow_html=True)
elif not analyze_btn:
    st.info("👆 Click **Analyze with Gemini** to generate the AI demand explanation and recommendations.")
