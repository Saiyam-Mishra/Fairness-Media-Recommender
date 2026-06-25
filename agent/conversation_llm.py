import os
import json

from groq import Groq
from dotenv import load_dotenv

from state import AgentState

load_dotenv()

# Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

_SYSTEM_PROMPT = """You are an assistant for media recommendations.

You have two modes:

MODE 1 - SUMMARIZE QUERY RESULTS:
When given database query results, convert them into a concise, friendly response for an end user.
- Keep the answer concise (under 300 words).
- If results are empty, say "No results found." and offer one-sentence suggestions to refine the query.
- Do not output SQL or internal debugging information.

MODE 2 - CONVERSATIONAL:
When answering follow-up questions about previously shown recommendations or media topics:
- Reference the data you were given earlier in the conversation.
- Answer user's clarifications or questions about the recommendations.
- Do not make up data not present in the provided results.
- Keep answers focused on media recommendations.

Rules for both modes:
- Do not make up any information.
- Only discuss media recommendations.
- Be helpful and concise.
"""

_MODEL = "llama-3.3-70b-versatile"


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
        # No SQL results — fall back to a conversational reply using the LLM.
        # Build a short prompt from recent messages and ask the model to reply.
        try:
            # Use last few messages as context
            convo = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in messages[-6:])
            prompt = f"You are a helpful assistant. Continue the conversation based on the context below:\n\n{convo}\n\nReply concisely and helpfully."

            response = client.chat.completions.create(
                model=_MODEL,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.choices[0].message.content.strip()
            return {**state, "agent_output": text, "error": None}
        except Exception as exc:
            return {**state, "agent_output": None, "error": f"LLM summarizer error: {exc}"}

    try:
        rows_text = _rows_to_text(rows, max_rows=20)

        prompt = f"User question: {user_question}\n\nQuery results (first {min(len(rows),20)} rows):\n{rows_text}\n\nWrite a concise, friendly summary for the user based on the results."

        response = client.chat.completions.create(
            model=_MODEL,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        text = response.choices[0].message.content.strip()

        return {**state, "agent_output": text, "error": None}

    except Exception as exc:
        return {**state, "agent_output": None, "error": f"LLM summarizer error: {exc}"}

