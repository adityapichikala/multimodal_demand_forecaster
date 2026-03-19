import os
import json
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

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

# OpenRouter Fallback Models
openrouter_kwargs = {
    "base_url": "https://openrouter.ai/api/v1",
    "api_key": os.getenv("OPENROUTER_API_KEY"),
    "model": "qwen/qwen2.5-vl-7b:free",
}

fallback_llm = ChatOpenAI(**openrouter_kwargs, temperature=0.2)
fallback_drafter = ChatOpenAI(**openrouter_kwargs, temperature=0.5)
fallback_auditor = ChatOpenAI(**openrouter_kwargs, temperature=0.0)

# Bind Fallbacks into standard chains
safe_llm = llm.with_fallbacks([fallback_llm])
safe_drafter = drafter_llm.with_fallbacks([fallback_drafter])
safe_auditor = auditor_llm.with_fallbacks([fallback_auditor])

def run_verification_pipeline(forecast_summary: dict, weather_text: str, news_text: str) -> str:
    """
    Executes the 4-Agent Actor-Critic verification pipeline.
    """
    print("--- Starting Multi-Agent Pipeline ---")
    
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
    """
    analyst_output = safe_llm.invoke([HumanMessage(content=analyst_prompt)]).content
    time.sleep(5) # Prevent burst limit on free tier where possible
    
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
    researcher_output = safe_llm.invoke([HumanMessage(content=researcher_prompt)]).content
    time.sleep(5)
    
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
    
    Ensure your final report includes:
    1. Executive Summary
    2. Quantitative Forecast (The Math)
    3. Qualitative Context (News/Weather Impact)
    4. Actionable Inventory Recommendation
    """
    draft_report = safe_drafter.invoke([HumanMessage(content=drafter_prompt)]).content
    time.sleep(5)
    
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
    final_verified_report = safe_auditor.invoke([HumanMessage(content=auditor_prompt)]).content
    
    print("--- Pipeline Complete ---")
    return final_verified_report
