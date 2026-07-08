import os
from dotenv import load_dotenv
from groq import Groq

from state import AgentState

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

SYSTEM_PROMPT = """
You are an expert SQL correction assistant for the movie recommender database.
The user asked for a movie query and the SQL returned by the generator failed.
Your job is to fix only the SQL query so it is valid for the provided schema,
while preserving the original intent. Output ONLY the corrected SQL query.
Do not add explanations, markdown, or comments.
"""

def build_user_prompt(sql: str, sql_error: str, schema: str, user_question: str | None) -> str:
    prompt = f"""Original user request:
{user_question or '(unknown)'}

Failed SQL:
{sql}

Database error:
{sql_error}

Schema:
{schema}

Please rewrite the SQL to be valid and preserve the intent."""
    return prompt

def run(state: AgentState) -> AgentState:
    sql = state.get("agent_output")
    if not sql:
        return {**state, "error": "No SQL to correct.", "agent_output": None}

    sql_error = state.get("sql_error", "")
    user_question = state.get("latest_user_question")
    schema = state.get("db_schema", "")

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0.0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(sql, sql_error, schema, user_question)},
        ],
    )
    corrected_sql = response.choices[0].message.content.strip()

    return {
        **state,
        "agent_output": corrected_sql,
        "sql_correction_attempted": True,
    }