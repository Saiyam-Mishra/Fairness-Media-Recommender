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

import os
from typing import Callable

from langgraph.graph import END, StateGraph

from state import AgentState
from english_to_sql import run as sql_agent

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
    return state.get("route", "english_to_sql")


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

    # Always start with routing
    builder.add_node("router", router_node)
    builder.set_entry_point("router")

    # Register every agent as a node
    for name, fn in _AGENTS.items():
        builder.add_node(name, fn)

    # Fallback for unknown routes
    builder.add_node("error", error_node)

    # Conditional edges from router → agent nodes
    route_map = {name: name for name in _AGENTS}
    route_map["__default__"] = "error"        # LangGraph uses "__default__" as fallback

    builder.add_conditional_edges(
        "router",
        route_decision,
        {**route_map},
    )

    # Every agent leads to END
    for name in _AGENTS:
        builder.add_edge(name, END)
    builder.add_edge("error", END)

    return builder.compile()