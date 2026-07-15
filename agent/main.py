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
        "last_results": None,  # for fairness assessment
        "last_query": None,  # for fairness assessment
        "fairness_report": None,  # report from fairness agent
        # Vector search fields
        "vector_search_query": None,
        "vector_embeddings": None,
        "use_vector_search": False,
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
                if isinstance(friendly, dict):
                    explanation = friendly.get("explanation", "")
                    results = friendly.get("results", [])
                    session_state["messages"].append({"role": "assistant", "content": explanation})
                    print(f"\nAssistant: {explanation}\n")
                    if results:
                        # Append re-ranked results to message history so conversation agent
                        # has visibility of injected films in subsequent turns
                        results_summary = "The improved recommendations are:\n" + "\n".join(
                            f"{i}. {r.get('title', 'Unknown')} ({r.get('release_year', '?')}) "
                            f"— {r.get('vote_average', '?')}★ — {', '.join(r.get('genres') or [])}. "
                            f"{r.get('overview', '')}"
                            for i, r in enumerate(results, 1)
                        )
                        session_state["messages"].append({"role": "assistant", "content": results_summary})

                        print("Improved Results:")
                        for i, r in enumerate(results, 1):
                            title = r.get("title", "Unknown")
                            year = r.get("release_year", "?")
                            rating = r.get("vote_average", "?")
                            genres = ", ".join(r.get("genres") or [])
                            directors = ", ".join(r.get("director_names") or [])
                            origin = ", ".join(r.get("origin_countries") or [])
                            lang = r.get("original_language", "")
                            print(f"  {i}. {title} ({year}) — {rating}★ — {genres}")
                            if directors:
                                print(f"     Director(s): {directors}")
                            if origin:
                                print(f"     Origin: {origin} | Language: {lang}")
                        report = result.get("fairness_report")
                        if report:
                            before = report.get("metrics_before", {})
                            after = report.get("metrics_after", {})
                            print("Fairness Metrics:")
                            print(f"  {'Metric':<12} {'Before':>10} {'After':>10}")
                            print(f"  {'-' * 34}")
                            for key in ("spd", "eod", "oaed"):
                                b = before.get(key)
                                a = after.get(key)
                                b_str = f"{b:.4f}" if b is not None else "N/A"
                                a_str = f"{a:.4f}" if a is not None else "N/A"
                                print(f"  {key.upper():<12} {b_str:>10} {a_str:>10}")
                            exp_b = before.get("exposure_k", {})
                            exp_a = after.get("exposure_k", {})
                            print(
                                f"  {'Exp@K (G+)':<12} {str(round(exp_b.get('protected') or 0, 4)):>10} {str(round(exp_a.get('protected') or 0, 4)):>10}")
                            print(
                                f"  {'Exp@K (G-)':<12} {str(round(exp_b.get('unprotected') or 0, 4)):>10} {str(round(exp_a.get('unprotected') or 0, 4)):>10}")
                            print()
                else:
                    session_state["messages"].append({"role": "assistant", "content": friendly})
                    print(f"\nAssistant: {friendly}\n")
            else:
                err = result.get("error") or "No output produced by agents."
                print(f"\n[Error] {err}\n")
        except Exception as exc:
            print(f"\n[Error] {exc}\n")


if __name__ == "__main__":
    main()
