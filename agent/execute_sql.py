import os

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from state import AgentState

load_dotenv()


def run(state: AgentState) -> AgentState:
    """Execute the SQL string found in state['agent_output'] and attach rows to state['query_result'].

    Expects: state['agent_output'] -> SQL string
    Produces: state['query_result'] -> list[dict]
    """
    # If there's already an error from an earlier agent, just pass through
    if state.get("error"):
        return {**state, "query_result": None}

    sql = state.get("agent_output")
    if not sql:
        return {**state, "query_result": None, "error": "No SQL found to execute.", "agent_output": None}

    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT") or 5432),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        return {**state, "query_result": rows, "error": None}

    except Exception as exc:
        return {**state, "query_result": None, "error": f"SQL execution error: {exc}", "agent_output": None}

