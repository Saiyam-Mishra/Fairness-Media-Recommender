"""
Demonstration of multi-turn conversation with state persistence.

This test simulates the new behavior where:
1. First message routes to SQL (no data yet)
2. SQL returns some results
3. Second message with existing data routes to CONVERSATION (can use existing data)
"""
import importlib.util
import sys
import types
from pathlib import Path


def make_fake_groq_response(content: str):
    """Create a fake response matching Groq API shape."""
    class FakeResponse:
        def __init__(self, content: str):
            self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=content))]

    class FakeCompletions:
        def __init__(self, content: str):
            self._content = content

        def create(self, *args, **kwargs):
            return FakeResponse(self._content)

    class FakeGroq:
        def __init__(self, api_key: str, content=content):
            self.chat = types.SimpleNamespace(completions=FakeCompletions(content))

    return FakeGroq


def inject_mocks():
    """Inject fake modules into sys.modules."""
    # groq (first call returns "SQL" for routing, second returns "CONVERSATION")
    # We'll set it to SQL for demo
    sys.modules["groq"] = types.ModuleType("groq")
    sys.modules["groq"].Groq = make_fake_groq_response("SQL")

    # google and google.genai
    google = types.ModuleType("google")
    genai = types.ModuleType("google.genai")
    genai.types = types.SimpleNamespace()
    google.genai = genai
    sys.modules["google"] = google
    sys.modules["google.genai"] = genai

    # langchain_core.messages
    lc = types.ModuleType("langchain_core")
    lc_msgs = types.ModuleType("langchain_core.messages")
    lc_msgs.HumanMessage = lambda content: content
    lc_msgs.SystemMessage = lambda content: content
    sys.modules["langchain_core"] = lc
    sys.modules["langchain_core.messages"] = lc_msgs

    # dotenv
    dot = types.ModuleType("dotenv")
    dot.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dot


def test_multi_turn_conversation_with_state_persistence():
    """
    Simulate a 2-turn conversation where:
    Turn 1: "Show me top movies" -> routes to SQL (no data yet) -> gets results
    Turn 2: "Tell me about the first one" -> routes to CONVERSATION (has data now)
    """
    inject_mocks()
    repo_root = Path(__file__).resolve().parents[1]
    agent_dir = repo_root / "agent"
    sys.path.insert(0, str(agent_dir))

    try:
        # Load master_agent module
        spec = importlib.util.spec_from_file_location("master_agent_demo", str(agent_dir / "master_agent.py"))
        master_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(master_mod)

        # Simulate persisted session state across multiple turns
        session_state = {
            "messages": [],
            "agent_output": None,
            "route": None,
            "query_result": None,
            "error": None,
        }

        # ===== TURN 1: First user message =====
        print("\n=== TURN 1: User asks for movies ===")
        session_state["messages"].append({"role": "user", "content": "Show me top movies"})

        # Master agent decides routing (mocked to return SQL)
        result1 = master_mod.run(session_state)
        session_state.update(result1)

        # Check: should route to SQL because no data yet
        print(f"Turn 1 routing decision: {result1.get('route')}")
        assert result1.get("route") == "english_to_sql", "First message should route to SQL"
        print("✓ Correctly routed to SQL for initial data fetch\n")

        # Simulate SQL agent producing SQL and execute_sql returning results
        session_state["agent_output"] = "SELECT * FROM movie_summary LIMIT 5"
        session_state["query_result"] = [
            {"title": "Movie A", "release_year": 2020, "vote_average": 8.5},
            {"title": "Movie B", "release_year": 2021, "vote_average": 8.2},
            {"title": "Movie C", "release_year": 2019, "vote_average": 8.0},
        ]
        session_state["agent_output"] = "Here are the top 3 movies: Movie A (2020, 8.5), Movie B (2021, 8.2), Movie C (2019, 8.0)"

        # ===== TURN 2: Follow-up message =====
        print("=== TURN 2: User asks about the first result ===")
        
        # Simulate Groq returning CONVERSATION for this turn
        sys.modules["groq"].Groq = make_fake_groq_response("CONVERSATION")
        
        # Reload the module to get the new mock
        if "master_agent_demo" in sys.modules:
            del sys.modules["master_agent_demo"]
        spec = importlib.util.spec_from_file_location("master_agent_demo", str(agent_dir / "master_agent.py"))
        master_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(master_mod)
        
        session_state["messages"].append({"role": "assistant", "content": session_state["agent_output"]})
        session_state["messages"].append({"role": "user", "content": "Tell me more about Movie A"})

        # Master agent decides routing for turn 2
        result2 = master_mod.run(session_state)
        session_state.update(result2)

        print(f"Turn 2 routing decision: {result2.get('route')}")
        print(f"Turn 2 query_result status: {bool(session_state.get('query_result'))}")
        
        # Check: should route to CONVERSATION because data already exists
        assert result2.get("route") == "conversation", "Follow-up should route to CONVERSATION when data exists"
        print("✓ Correctly routed to CONVERSATION to discuss existing data\n")

        # Verify state persistence across turns
        assert len(session_state["messages"]) == 3, "Should have accumulated 3 messages (user, assistant, user)"
        assert session_state["query_result"] is not None, "Query results should persist"
        assert len(session_state["query_result"]) == 3, "Should have 3 results"

        print("✓ State correctly persisted across conversation turns")
        print(f"✓ Conversation history: {len(session_state['messages'])} messages")
        print(f"✓ Available data: {len(session_state['query_result'])} results\n")

    finally:
        if str(agent_dir) in sys.path:
            sys.path.remove(str(agent_dir))
        # Cleanup
        for mod_name in ["master_agent_demo", "groq", "google", "google.genai", "langchain_core", "langchain_core.messages", "dotenv"]:
            if mod_name in sys.modules:
                del sys.modules[mod_name]


if __name__ == "__main__":
    test_multi_turn_conversation_with_state_persistence()
    print("All checks passed! Multi-turn conversation flow works correctly.")

