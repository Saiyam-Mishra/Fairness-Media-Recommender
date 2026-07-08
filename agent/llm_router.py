"""
llm_router.py — LLM-based router that replaces the keyword router_node in graph.py.

Decides between:
  - "fairness"  : user is questioning the fairness/diversity of previous results
  - "master"    : everything else (new recommendations, clarifications, conversation)

Import and use in graph.py:
    from llm_router import router_node
"""

import os
from dotenv import load_dotenv
from groq import Groq
from state import AgentState

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

_MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = """You are a routing assistant for a movie recommendation chatbot.

Given the recent conversation and the latest user message, decide whether the user is questioning the FAIRNESS or DIVERSITY of previously recommended movies, or whether they are making any other kind of request.

Answer with exactly one of these two tokens (uppercase):
  FAIRNESS
  MASTER

Rules:
1. Answer FAIRNESS if the user is questioning, challenging, or asking to explain the diversity or representation of a PREVIOUS recommendation. Examples:
   - "Why are all of these directed by men?"
   - "Are there any female directors in these results?"
   - "Why are all these American films?"
   - "These are all action movies, where's the variety?"
   - "Why is there no Asian cinema here?"
   - "Aren't there any non-English films?"
   - "This seems biased towards Hollywood"

2. Answer MASTER for everything else, including:
   - New recommendation requests ("give me thriller movies")
   - Follow-up questions about a specific movie ("tell me more about Parasite")
   - General conversation or clarifications
   - Requests that mention fairness concepts but are asking FOR diverse recommendations rather than QUESTIONING existing ones ("recommend me some films by female directors")

3. If there are NO previous results in the conversation, always answer MASTER — fairness assessment requires a previous result set to assess.

4. When in doubt, answer MASTER.

Output only the single token. No other text."""


def _keyword_fallback(user_text: str) -> str:
    """Conservative fallback if the LLM call fails."""
    fairness_triggers = (
        "why are all", "why is there no", "aren't there", "biased",
        "unfair", "no diversity", "all male", "all american", "all english",
        "all action", "no female", "no women", "no asian", "no non-english",
    )
    text = user_text.lower()
    for kw in fairness_triggers:
        if kw in text:
            return "fairness"
    return "master"


def router_node(state: AgentState) -> AgentState:
    """LLM-based router: classifies message as fairness challenge or general request."""
    messages = state.get("messages", [])
    last_results = state.get("last_results")

    # Extract latest user message
    user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_text = msg.get("content", "")
            break

    if not user_text:
        return {**state, "route": "master", "route_reason": "no_user_message"}

    # Build recent conversation context (last 4 messages)
    recent = messages[-4:] if len(messages) > 4 else messages
    context_lines = []
    for msg in recent:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")[:300]
        context_lines.append(f"{role}: {content}")
    context_str = "\n".join(context_lines)

    # Tell the LLM whether previous results exist
    if last_results:
        data_status = f"Previous recommendation exists: {len(last_results)} movies were shown to the user."
    else:
        data_status = "No previous recommendation has been made yet in this session."

    user_prompt = (
        f"Recent conversation:\n{context_str}\n\n"
        f"Data status: {data_status}\n\n"
        f"Latest user message: {user_text}"
    )

    try:
        response = client.chat.completions.create(
            model=_MODEL,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content.strip()
        upper = raw.upper()
        print(f"[llm_router] raw={raw!r}")

        if "FAIRNESS" in upper:
            print("[llm_router] -> fairness")
            return {**state, "route": "fairness", "route_reason": "llm_router", "route_model_raw": raw}
        if "MASTER" in upper:
            print("[llm_router] -> master")
            return {**state, "route": "master", "route_reason": "llm_router", "route_model_raw": raw}

        # Unexpected output — fall through to keyword fallback
        print(f"[llm_router] unexpected output: {raw!r}, using keyword fallback")

    except Exception as exc:
        print(f"[llm_router] LLM call failed: {exc}, using keyword fallback")

    route = _keyword_fallback(user_text)
    print(f"[llm_router] keyword_fallback -> {route}")
    return {**state, "route": route, "route_reason": "keyword_fallback"}