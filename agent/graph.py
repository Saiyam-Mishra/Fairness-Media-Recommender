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
from fairness_agent import run as fairness_agent
from master_agent import run as master_agent
from analyze_query import run as analyze_query_agent
from llm_router import router_node

# ── Default sample schema (override via AgentState["db_schema"]) ──────────────
DEFAULT_DB_SCHEMA = ''

# ── Agent registry ────────────────────────────────────────────────────────────
# Maps route names to their run() callables.
_AGENTS: dict[str, Callable[[AgentState], AgentState]] = {
    "english_to_sql": sql_agent,
    # after producing SQL, execute it and then render results via the conversation agent
    "execute_sql": execute_sql_agent,
    "conversation": conversation_agent,
    "fairness": fairness_agent,
}


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

    # Pre-router decides whether the request is a fairness challenge.
    builder.add_node("router", router_node)
    builder.set_entry_point("router")

    # Master agent decides whether to call the SQL pipeline or the conversation
    # agent.
    builder.add_node("master", master_agent)

    # Query analyzer (runs before SQL agent to detect vector search potential)
    builder.add_node("analyze_query", analyze_query_agent)

    # Register every agent as a node
    for name, fn in _AGENTS.items():
        builder.add_node(name, fn)

    # Fallback for unknown routes
    builder.add_node("error", error_node)

    # Router sends fairness challenges directly to the fairness agent; all other
    # traffic continues through the existing master agent.
    builder.add_conditional_edges(
        "router",
        lambda state: state.get("route", "master"),
        {
            "fairness": "fairness",
            "master": "master",
        },
    )

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

    # Fairness assessment ends directly after producing the report.
    builder.add_edge("fairness", END)

    # Conversation node ends directly
    builder.add_edge("conversation", END)
    
    # Error ends directly
    builder.add_edge("error", END)

    return builder.compile()