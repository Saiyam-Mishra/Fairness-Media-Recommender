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
    
    # Maintain session state across multiple user inputs so the master agent
    # can see previously retrieved data and decide if fresh data is needed.
    session_state: AgentState = {
        "messages": [],
        "agent_output": None,
        "route": None,
        "db_schema": DEFAULT_DB_SCHEMA,
        "error": None,
        "query_result": None,  # persist across invocations
    }

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Bye!")
            break

        # Append the user message to the session conversation history
        session_state["messages"].append({"role": "user", "content": user_input})

        try:
            # Invoke the graph with the persisted session state.
            # The graph will update agent_output, route, error, and possibly query_result.
            result = graph.invoke(session_state)
            
            # Update session state with the result so subsequent invocations see updated data
            session_state = result

            # Debugging: if the master agent saved routing info, show it so it's
            # easy to understand why we ended up at the conversation node.
            route_raw = result.get("route_model_raw")
            route_reason = result.get("route_reason")
            if route_raw or route_reason:
                print(f"[Router debug] model_output={route_raw!r} reason={route_reason!r}")

            # Prefer the final agent_output produced by the graph (LLM-friendly text),
            # otherwise surface any error.
            friendly = result.get("agent_output")
            if friendly:
                # Append assistant response to conversation history for next iteration context
                session_state["messages"].append({"role": "assistant", "content": friendly})
                print(f"\nAssistant: {friendly}\n")
            else:
                err = result.get("error") or "No output produced by agents."
                print(f"\n[Error] {err}\n")
        except Exception as exc:
            print(f"\n[Error] {exc}\n")


if __name__ == "__main__":
    main()
