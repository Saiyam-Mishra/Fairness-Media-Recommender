from graph import build_graph, DEFAULT_DB_SCHEMA
from state import AgentState
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
)
cur = conn.cursor(cursor_factory=RealDictCursor)


def main():
    print("=" * 60)
    print("  LangGraph Multi-Agent System")
    print("=" * 60)
    print("\nAvailable agents:")
    print("  • english_to_sql  — Converts natural language to SQL")
    print("  • summarizer      — Summarizes text")
    print("\nRouting is automatic based on your query.\n")
    print("Type 'exit' to quit.\n")

    graph = build_graph()

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Bye!")
            break

        initial_state: AgentState = {
            "messages": [{"role": "user", "content": user_input}],
            "agent_output": None,
            "route": None,
            "db_schema": DEFAULT_DB_SCHEMA,
            "error": None,
        }

        try:
            result = graph.invoke(initial_state)
            output = result.get("agent_output") or result.get("error") or "No output."
            cur.execute(output)
            for row in cur.fetchall():
                print(" ", dict(row))
            # print(f"\nAssistant: {output}\n")
        except Exception as exc:
            print(f"\n[Error] {exc}\n")


if __name__ == "__main__":
    main()
