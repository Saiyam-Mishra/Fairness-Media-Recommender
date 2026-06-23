"""LLM-based master agent.

This agent classifies whether the user's latest message requires a database
lookup (route -> "english_to_sql") or can be handled by the conversation
agent directly (route -> "conversation"). It uses a small LLM classifier
call and falls back to a conservative keyword heuristic if the model fails.
"""
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

from state import AgentState

load_dotenv()

# Gemini client
client = genai.Client(api_key=os.getenv("GEMINI_KEY", ""))

_SYSTEM_PROMPT = """You are a routing assistant. Given a user message and the
conversation context, decide whether the user's request requires retrieving
data from a database (SQL) or can be answered directly by the conversation
agent without a database lookup.

Answer with exactly one of the following tokens (uppercase):
  SQL
  CONVERSATION

Do not output any other text. If the message mentions tables, counts, lists,
joins, filters, or otherwise asks to fetch/return rows from a database, choose
SQL. If the message asks for general advice, recommendations, explanations,
or conversational responses that don't need the database, choose CONVERSATION.
If unsure, prefer CONVERSATION.
"""

_MODEL = "gemini-2.5-flash"
_CONFIG = types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT, temperature=0.0)


def _keyword_fallback(user_text: str) -> str:
    # Conservative fallback: only route to SQL on clear data-retrieval keywords
    sql_triggers = (
        "select",
        "query",
        "sql",
        "database",
        "table",
        "fetch",
        "retrieve",
        "find all",
        "get all",
        "list all",
        "how many",
        "count",
        "where",
    )
    text = user_text.lower()
    for kw in sql_triggers:
        if kw in text:
            return "english_to_sql"
    return "conversation"


def run(state: AgentState) -> AgentState:
    messages = state.get("messages", [])
    user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_text = msg.get("content", "")
            break

    if not user_text:
        return {**state, "route": "conversation"}

    try:
        response = client.models.generate_content(
            model=_MODEL, contents=user_text, config=_CONFIG
        )
        choice = response.text.strip().upper()
        if choice == "SQL":
            return {**state, "route": "english_to_sql"}
        if choice == "CONVERSATION":
            return {**state, "route": "conversation"}

    except Exception:
        # fall through to keyword fallback
        pass

    # Keyword fallback if LLM fails or returns unexpected text
    return {**state, "route": _keyword_fallback(user_text)}


