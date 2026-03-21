import os
import json
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.callbacks import StdOutCallbackHandler
from tenacity import retry, wait_exponential, stop_after_attempt
from datetime import date

# Initialize Gemini models via LangChain
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.2 # low temperature for more deterministic analysis
)

drafter_llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.5 # slightly higher for drafting a narrative
)

auditor_llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.0 # Strict deterministic checking
)

# OpenRouter Fallback Models (Free Tier)
openrouter_kwargs = {
    "base_url": "https://openrouter.ai/api/v1",
    "api_key": os.getenv("OPENROUTER_API_KEY"),
    "model": "openrouter/free",
}

fallback_llm = ChatOpenAI(**openrouter_kwargs, temperature=0.2)
fallback_drafter = ChatOpenAI(**openrouter_kwargs, temperature=0.5)
fallback_auditor = ChatOpenAI(**openrouter_kwargs, temperature=0.0)

# Bind Fallbacks into standard chains
safe_llm = llm.with_fallbacks([fallback_llm])
safe_drafter = drafter_llm.with_fallbacks([fallback_drafter])
safe_auditor = auditor_llm.with_fallbacks([fallback_auditor])

@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(3))
def run_verification_pipeline(forecast_summary: dict, weather_text: str, news_text: str) -> str:
    """
    Executes the 4-Agent Actor-Critic verification pipeline with observability and retries.
    """
    print("--- Starting Multi-Agent Pipeline ---")
    
    # Observability: Initialize basic callback handler
    # Note: In a real production env, this would be Langfuse or LangSmith
    config = {"callbacks": [StdOutCallbackHandler()]}
    
    # --- Agent 1: Data Analyst ---
    print("Agent 1: Data Analyst running...")
    analyst_prompt = f"""
    You are an expert Data Analyst specializing in time-series forecasting.
    Analyze the following raw Prophet model JSON summary. 
    Extract the key mathematical bounds exactly as they appear (do not round or alter them).
    Identify the overarching trajectory: is demand increasing, decreasing, or flat?
    Provide a concise bulleted summary of the "math facts".
    
    Data:
    {json.dumps(forecast_summary, indent=2)}
    
    IMPORTANT: Explicitly identify the PEAK (Maximum) forecasted value in your summary.
    """
    analyst_output = safe_llm.invoke([HumanMessage(content=analyst_prompt)], config=config).content
    
    # --- Agent 2: Context Researcher ---
    print("Agent 2: Context Researcher running...")
    researcher_prompt = f"""
    You are an expert Supply Chain Risk Analyst.
    Analyze the following recent weather patterns and news headlines.
    Provide a brief, factual summary of any risks or opportunities that could affect retail demand.
    If there are no major risks, state that explicitly.
    
    Weather:
    {weather_text}
    
    News:
    {news_text}
    """
    researcher_output = safe_llm.invoke([HumanMessage(content=researcher_prompt)], config=config).content
    
    # --- Agent 3: Supply Chain Director (Drafter) ---
    print("Agent 3: Supply Chain Director drafting report...")
    drafter_prompt = f"""
    You are a Director of Supply Chain issuing an inventory recommendation.
    Draft a comprehensive, highly readable Markdown report combining the Mathematical Facts from the Data Analyst 
    and the Contextual Risks from the Context Researcher. 
    
    Store ID: {forecast_summary.get('store', 'N/A')}
    Product ID: {forecast_summary.get('item', 'N/A')}
    Last Historical Date: {forecast_summary.get('last_historical_date', 'N/A')}
    
    Math Facts:
    {analyst_output}
    
    Contextual Risk:
    {researcher_output}
    
    1. Executive Summary (Use current date: {date.today().strftime('%B %d, %Y')})
    2. Quantitative Forecast (The Math)
    3. Qualitative Context (News/Weather Impact)
    4. Actionable Inventory Recommendation (Analyze the trend: If demand is increasing, prioritize stockout prevention using PEAK forecasted values. If demand is crashing or decreasing, focus on avoiding overstocking and dead inventory, and recommend tapering down orders).
    
    RETURN ONLY THE MARKDOWN REPORT. No introductory or concluding remarks.
    """
    draft_report = safe_drafter.invoke([HumanMessage(content=drafter_prompt)], config=config).content
    
    # --- Agent 4: QA Auditor (Critic) ---
    print("Agent 4: QA Auditor verifying...")
    auditor_prompt = f"""
    You are a strict QA Auditor preventing AI hallucinations.
    Your job is to read the 'Drafted Report' and ensure it does NOT contradict the 'Math Facts'.
    Specifically check that any numbers mentioned in the Draft exist exactly in the Math Facts.
    
    Math Facts (TRUTH):
    {analyst_output}
    
    Drafted Report:
    {draft_report}
    
    Does the Drafted Report hallucinate any numbers or make claims that violently contradict the Math Facts?
    If YES: Rewrite the Drafted Report to fix the hallucinations but keep the structure.
    If NO: Return the Drafted Report exactly as is.
    
    RETURN ONLY THE FINAL APPROVED MARKDOWN TEXT. Do not add conversational filler like "Here is the rewritten report".
    """
    final_verified_report = safe_auditor.invoke([HumanMessage(content=auditor_prompt)], config=config).content
    
    print("--- Pipeline Complete ---")
    return final_verified_report.strip()
