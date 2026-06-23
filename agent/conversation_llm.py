import os
import json

from google import genai
from google.genai import types
from dotenv import load_dotenv

from state import AgentState

load_dotenv()

# reuse the same client pattern as other agents
client = genai.Client(api_key=os.getenv("GEMINI_KEY", ""))

_SYSTEM_PROMPT = """You are an assistant that converses with user about media reccomendation.
When given data, you convert database query results into a concise, friendly response for an end user.
When the user asks a question, you should answer it based on the data provided. If the data is insufficient to answer the question, you should say so.
Do not make up any information that is not present in the data. If the user asks a question that is not related to the data, you should say so.
ONLY talk about media reccomendations. Do not talk about anything else. If the user asks a question that is not related to media reccomendations, you should say so.
Given the original user question and up to the first 20 rows of query results, produce a short natural-language summary suitable for display.
Rules:
- Keep the answer concise (under 300 words).
- If no rows were returned, say "No results found." and offer one-sentence suggestions to refine the query.
- Do not output SQL or internal debugging information.
"""

_MODEL = "gemini-2.5-flash"
_CONFIG = types.GenerateContentConfig(
    system_instruction=_SYSTEM_PROMPT,
    temperature=0.2,
)


def _rows_to_text(rows: list[dict], max_rows: int = 20) -> str:
    if not rows:
        return ""
    sample = rows[:max_rows]
    lines = []
    for i, r in enumerate(sample, start=1):
        # Convert each row to a compact JSON-like line
        safe = {k: (v if v is not None else "") for k, v in r.items()}
        lines.append(f"{i}. " + json.dumps(safe, default=str, ensure_ascii=False))
    return "\n".join(lines)


def run(state: AgentState) -> AgentState:
    """LLM-based agent: convert state['query_result'] into a user-facing string.

    Expects: state['query_result'] -> list[dict]
    Produces: state['agent_output'] -> str
    """
    # If there's already an error from an earlier agent, pass it through
    if state.get("error"):
        return state

    rows = state.get("query_result")
    messages = state.get("messages", [])
    # find original user question
    user_question = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_question = msg.get("content", "")
            break

    if rows is None:
        return {**state, "agent_output": None, "error": "No query results provided to LLM summarizer."}

    try:
        rows_text = _rows_to_text(rows, max_rows=20)

        prompt = f"User question: {user_question}\n\nQuery results (first {min(len(rows),20)} rows):\n{rows_text}\n\nWrite a concise, friendly summary for the user based on the results."

        response = client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=_CONFIG,
        )
        text = response.text.strip()

        return {**state, "agent_output": text, "error": None}

    except Exception as exc:
        return {**state, "agent_output": None, "error": f"LLM summarizer error: {exc}"}

