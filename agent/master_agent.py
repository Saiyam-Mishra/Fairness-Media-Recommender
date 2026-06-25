"""LLM-based master agent.

This agent classifies whether the user's latest message requires a new database
lookup (route -> "english_to_sql"), or can be answered using existing data
(route -> "conversation"). It uses a small LLM classifier with conversation
context and known data state to make routing decisions, with a keyword fallback.
"""
import os
from dotenv import load_dotenv
from groq import Groq

from state import AgentState

load_dotenv()

# Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

_SYSTEM_PROMPT = """You are a routing assistant. Given recent conversation context and the latest user message, decide whether the request requires a new database lookup (SQL) or can be answered using existing data (CONVERSATION).

Answer with exactly one of the following tokens (uppercase):
  SQL
  CONVERSATION

Rules:
1. If NO DATA HAS BEEN RETRIEVED YET (conversation just started), always answer SQL to retrieve initial recommendations.
2. If DATA EXISTS and the user is asking about, clarifying, or discussing the recommendations already presented, answer CONVERSATION. The summarizer/conversation agent will use the existing data to answer.
3. If the user is asking for NEW recommendations (different criteria, different search), answer SQL.
4. Do not make or recommend anything without data. If the user asks for recommendations without data present, route to SQL.

Do not output any other text."""

_MODEL = "llama-3.3-70b-versatile"


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
    query_result = state.get("query_result")
    
    # Extract the last 4 messages for context (or fewer if not available)
    recent_messages = messages[-4:] if len(messages) > 4 else messages
    
    # Build a context string showing recent conversation
    context_lines = []
    for msg in recent_messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")[:200]  # truncate long messages for brevity
        context_lines.append(f"{role}: {content}")
    
    context_str = "\n".join(context_lines) if context_lines else "(No messages)"
    
    # Indicate to the model whether data has been retrieved
    data_status = ""
    if query_result is not None:
        result_count = len(query_result) if isinstance(query_result, (list, tuple)) else 1
        data_status = f"\n\n--- CONTEXT ---\nExisting data retrieved: {result_count} results available\n"
    else:
        data_status = "\n\n--- CONTEXT ---\nNo data retrieved yet (conversation just started)\n"
    
    user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_text = msg.get("content", "")
            break

    if not user_text:
        return {**state, "route": "conversation"}

    try:
        # Build a user prompt that includes recent conversation and data status
        user_prompt = f"Recent conversation:\n{context_str}{data_status}\nLatest user message: {user_text}"
        
        response = client.chat.completions.create(
            model=_MODEL,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        # Be tolerant to model output: allow surrounding text, case differences,
        # or extra punctuation. Record the raw model output in state for debugging.
        raw = response.choices[0].message.content.strip()
        upper = raw.upper()
        # Save the raw model output so it's easy to debug routing decisions later
        state = {**state, "route_model_raw": raw}

        # Emit a visible debug line so interactive runs always show routing info
        try:
            print(f"[master_agent] model_raw={raw!r} -> routing_decision_preview={upper}")
        except Exception:
            # Don't fail the agent if printing has issues
            pass

        # If the model mentions SQL anywhere, route to the SQL pipeline.
        if "SQL" in upper:
            print("[master_agent] routing -> english_to_sql (model)")
            return {**state, "route": "english_to_sql", "route_reason": "model"}
        # If the model mentions CONVERSATION anywhere, route to the conversation agent.
        if "CONVERSATION" in upper:
            print("[master_agent] routing -> conversation (model)")
            return {**state, "route": "conversation", "route_reason": "model"}

    except Exception as exc:
        # If the model call fails, fall through to keyword fallback. Record an
        # error indicator in state to aid debugging.
        state = {**state, "route_model_error": True}
        print(f"[master_agent] model call failed: {exc}, using keyword fallback")
        # fall through to keyword fallback
        pass

    # Keyword fallback if LLM fails or returns unexpected text
    fallback_route = _keyword_fallback(user_text)
    print(f"[master_agent] keyword_fallback -> {fallback_route}")
    return {**state, "route": fallback_route, "route_reason": "keyword_fallback"}


