from graph import build_graph, DEFAULT_DB_SCHEMA
from state import AgentState
from dotenv import load_dotenv

load_dotenv()


def main():
    print("=" * 60)
    print("  Med-Rec")
    print("=" * 60)
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
            # Invoke the graph. For SQL flows the graph will:
            # router -> english_to_sql -> execute_sql -> results_llm
            result = graph.invoke(initial_state)

            # Prefer the final agent_output produced by the graph (LLM-friendly text),
            # otherwise surface any error.
            friendly = result.get("agent_output")
            if friendly:
                print(f"\nAssistant: {friendly}\n")
            else:
                err = result.get("error") or "No output produced by agents."
                print(f"\n[Error] {err}\n")
        except Exception as exc:
            print(f"\n[Error] {exc}\n")


if __name__ == "__main__":
    main()
