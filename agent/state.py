"""
state.py — Shared TypedDict that flows through every node in the graph.

To add fields for a new agent, extend AgentState here.
"""

from typing import Any, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    # Conversation history in OpenAI-style format
    messages: list[dict[str, str]]

    # Final text output produced by whichever agent handled the request
    agent_output: Optional[str]

    # Routing decision set by the router node
    route: Optional[str]

    # SQL-agent specific: database schema description
    db_schema: Optional[str]

    # Any error message surfaced during execution
    error: Optional[str]
    # Rows returned from executing an SQL query
    query_result: Optional[list[dict]]
