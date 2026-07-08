import os

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from sql_corrector import run as sql_corrector_agent
from state import AgentState

load_dotenv()


def _normalize_row(row: dict) -> dict:
    if row.get("vote_average") is None:
        row["vote_average"] = (
            row.get("ratings") or
            row.get("rating") or
            row.get("avg_rating") or
            row.get("score") or
            None
        )
    return row

def run(state: AgentState) -> AgentState:
    """Execute the SQL string found in state['agent_output'] and attach rows to state['query_result'].

    If the SQL contains an {{EMBEDDINGS_VECTOR}} placeholder and vector_embeddings are 
    available, replaces the placeholder with the actual embedding vector.

    Also persists the results to state['last_results'] and the user query to state['last_query']
    for fairness assessment on the next turn.

    Expects: state['agent_output'] -> SQL string
    Produces: state['query_result'] -> list[dict]
    """
    # If there's already an error from an earlier agent, just pass through
    if state.get("error"):
        return {**state, "query_result": None}
    
    # Extract the user's query for persistence
    messages = state.get("messages", [])
    user_query = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_query = msg.get("content", "")
            break

    sql = state.get("agent_output")
    if not sql:
        return {**state, "query_result": None, "error": "No SQL found to execute.", "agent_output": None}

    # Check if embeddings need to be substituted
    vector_embeddings = state.get("vector_embeddings")
    sql_has_vector = state.get("sql_has_vector", False)

    if vector_embeddings:
    # if sql_has_vector and vector_embeddings:
        # The SQL should have {{EMBEDDINGS_VECTOR}} placeholders to be replaced
        # For pgvector, we need to convert the embedding list to a PostgreSQL vector format
        # The embedding is a list of floats; we'll pass it as a parameter instead
        print(f"[execute_sql] replacing vector placeholder with actual embeddings")
        use_embeddings = vector_embeddings
    else:
        use_embeddings = None

    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT") or 5432),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # If we have embeddings, we need to handle the SQL specially
        # The LLM should have put the {{EMBEDDINGS_VECTOR}} placeholder
        # We'll replace it with a parameter placeholder
        if use_embeddings and "EMBEDDINGS_VECTOR" in sql:
            # Replace the placeholder with %s for parameter binding
            sql_escaped = sql.replace("%", "%%")
            sql_with_params = sql_escaped.replace("EMBEDDINGS_VECTOR", "%s::vector")
            print(f"[execute_sql] executing with vector parameter")
            print(f"[execute_sql] SQL: {sql_with_params}")
            cur.execute(sql_with_params, (use_embeddings,))
        elif use_embeddings and "embeddings_vector" in sql:
            # Replace the placeholder with %s for parameter binding
            sql_with_params = sql.replace("embeddings_vector", "%s::vector")
            print(f"[execute_sql] executing with vector parameter")
            cur.execute(sql_with_params, (use_embeddings,))
        else:
            # Standard SQL execution without embeddings
            cur.execute(sql)
        
        rows = cur.fetchall()
        cur.close()
        conn.close()

        normalized_rows = [_normalize_row(dict(r)) for r in rows]
        if normalized_rows:
            print(f"[execute_sql] result keys: {list(normalized_rows[0].keys())}")
        return {
            **state,
            "query_result": normalized_rows,
            "last_results": normalized_rows,
            "last_query": user_query,
            "error": None,
        }


    except Exception as exc:

        error_text = str(exc)

        correction_attempted = state.get("sql_correction_attempted", False)

        if not correction_attempted:

            print(f"[execute_sql] SQL execution failed: {error_text}. Attempting correction...")

            corrected_state = {

                **state,

                "sql_error": error_text,

                "sql_correction_attempted": True,

            }

            corrected_state = sql_corrector_agent(corrected_state)

            corrected_sql = corrected_state.get("agent_output")

            if corrected_sql and corrected_sql != sql:
                return run(corrected_state)

            print("[execute_sql] SQL correction did not produce a different query or failed.")

        return {

            **state,

            "query_result": None,

            "error": f"SQL execution error: {exc}",

            "agent_output": None,

        }

