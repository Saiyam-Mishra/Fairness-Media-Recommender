"""
graph.py — Builds the LangGraph StateGraph and wires up all agents.

HOW TO ADD A NEW AGENT
──────────────────────
1. Create agents/<your_agent>.py with a function:
       def run(state: AgentState) -> AgentState
2. Import it here and register it with `register_agent(...)`.
3. Add a routing keyword in `ROUTE_KEYWORDS` below.
That's it — no other files need to change.
"""

from typing import Callable

from langgraph.graph import END, StateGraph

from state import AgentState
from english_to_sql import run as sql_agent
from execute_sql import run as execute_sql_agent
from conversation_llm import run as conversation_agent
from master_agent import run as master_agent
from analyze_query import run as analyze_query_agent

# ── Default sample schema (override via AgentState["db_schema"]) ──────────────
DEFAULT_DB_SCHEMA = ''

# ── Keyword-based routing table ───────────────────────────────────────────────
# Keys are the route names; values are lists of trigger keywords (lower-case).
# The router picks the FIRST route whose keywords appear in the user message.
ROUTE_KEYWORDS: dict[str, list[str]] = {
    "english_to_sql": [
        "select", "query", "sql", "database", "table", "fetch", "retrieve",
        "find all", "get all", "list all", "show me", "how many", "count",
        "insert", "update", "delete", "join", "where", "group by",
    ],
}

# ── Agent registry ────────────────────────────────────────────────────────────
# Maps route names to their run() callables.
_AGENTS: dict[str, Callable[[AgentState], AgentState]] = {
    "english_to_sql": sql_agent,
    # after producing SQL, execute it and then render results via the conversation agent
    "execute_sql": execute_sql_agent,
    "conversation": conversation_agent,
}


def register_agent(
    route_name: str,
    run_fn: Callable[[AgentState], AgentState],
    keywords: list[str],
) -> None:
    """Register a new agent at runtime (useful for testing or plugins)."""
    _AGENTS[route_name] = run_fn
    ROUTE_KEYWORDS[route_name] = keywords


# ── Router node ───────────────────────────────────────────────────────────────

def router_node(state: AgentState) -> AgentState:
    """Inspect the latest user message and set state['route']."""
    messages = state.get("messages", [])
    user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_text = msg["content"].lower()
            break

    chosen_route = "english_to_sql"          # sensible default
    for route, keywords in ROUTE_KEYWORDS.items():
        if any(kw in user_text for kw in keywords):
            chosen_route = route
            break

    return {**state, "route": chosen_route}


def route_decision(state: AgentState) -> str:
    """Conditional edge: return the route name so LangGraph jumps to the right node."""
    return state.get("route", "conversation")


# ── Error-handler node ────────────────────────────────────────────────────────

def error_node(state: AgentState) -> AgentState:
    route = state.get("route", "unknown")
    return {
        **state,
        "agent_output": None,
        "error": f"No agent registered for route '{route}'.",
    }


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    # Master agent decides whether to call the SQL pipeline or the conversation
    # agent. It is the entry point of the graph.
    builder.add_node("master", master_agent)
    builder.set_entry_point("master")

    # Query analyzer (runs before SQL agent to detect vector search potential)
    builder.add_node("analyze_query", analyze_query_agent)

    # Register every agent as a node
    for name, fn in _AGENTS.items():
        builder.add_node(name, fn)

    # Fallback for unknown routes
    builder.add_node("error", error_node)

    # Conditional routing from master to:
    # - analyze_query (if going to SQL)
    # - conversation (if going to conversation)
    # - error (if unknown route)
    def route_from_master(state: AgentState) -> str:
        route = state.get("route", "conversation")
        if route == "english_to_sql":
            return "analyze_query"  # go through analyzer before SQL
        elif route == "conversation":
            return "conversation"
        else:
            return "error"

    builder.add_conditional_edges(
        "master",
        route_from_master,
        {
            "analyze_query": "analyze_query",
            "conversation": "conversation",
            "error": "error",
        },
    )

    # analyze_query always flows to english_to_sql
    builder.add_edge("analyze_query", "english_to_sql")

    # Wire the SQL pipeline:
    # english_to_sql -> execute_sql -> conversation -> END
    builder.add_edge("english_to_sql", "execute_sql")
    builder.add_edge("execute_sql", "conversation")
    builder.add_edge("conversation", END)

    # Conversation node ends directly
    builder.add_edge("conversation", END)
    
    # Error ends directly
    builder.add_edge("error", END)

    return builder.compile()