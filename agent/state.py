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
    
    # Previous turn's ranked recommendation results and query text (for fairness assessment)
    last_results: Optional[list[dict]]
    last_query: Optional[str]
    
    # Fairness assessment payload produced by fairness_agent
    fairness_report: Optional[dict]
    
    # Vector search fields (set by analyze_query agent)
    vector_search_query: Optional[str]  # the semantic portion to embed
    vector_embeddings: Optional[list[float]]  # encoded vector (384-dim for all-MiniLM-L6-v2)
    use_vector_search: Optional[bool]  # whether to include vector distance in results
