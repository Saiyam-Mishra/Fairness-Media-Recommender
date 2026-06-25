import importlib
import importlib.util
import sys
import types
from pathlib import Path


def _make_fake_groq_module(response_content: str):
    """Create a fake 'groq' module with a Groq class that returns a deterministic response."""
    mod = types.ModuleType("groq")

    class FakeResponse:
        def __init__(self, content: str):
            # emulate response.choices[0].message.content
            self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=content))]

    class FakeCompletions:
        def __init__(self, content: str):
            self._content = content

        def create(self, *args, **kwargs):
            return FakeResponse(self._content)

    class FakeGroq:
        def __init__(self, api_key: str, content=response_content):
            # provide client.chat.completions.create(...)
            self.chat = types.SimpleNamespace(completions=FakeCompletions(content))

    mod.Groq = FakeGroq
    return mod


def _inject_minimal_deps(groq_content: str, tmp_path=None):
    """Insert minimal fake modules into sys.modules so the agent modules can import them.

    Returns a list of module names inserted (so caller can pop them later).
    """
    inserted = []

    # groq
    sys.modules["groq"] = _make_fake_groq_module(groq_content)
    inserted.append("groq")

    # google and google.genai (minimal)
    google = types.ModuleType("google")
    genai = types.ModuleType("google.genai")
    # provide a dummy 'types' attribute used in some files
    genai.types = types.SimpleNamespace()
    google.genai = genai
    sys.modules["google"] = google
    sys.modules["google.genai"] = genai
    inserted.extend(["google", "google.genai"])

    # langchain_core.messages (provide HumanMessage/SystemMessage so imports succeed)
    lc = types.ModuleType("langchain_core")
    lc_msgs = types.ModuleType("langchain_core.messages")
    lc_msgs.HumanMessage = lambda content: content
    lc_msgs.SystemMessage = lambda content: content
    sys.modules["langchain_core"] = lc
    sys.modules["langchain_core.messages"] = lc_msgs
    inserted.extend(["langchain_core", "langchain_core.messages"])

    # dotenv (provide load_dotenv noop)
    dot = types.ModuleType("dotenv")
    dot.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dot
    inserted.append("dotenv")

    return inserted


def _cleanup_modules(names):
    for n in names:
        if n in sys.modules:
            del sys.modules[n]


def _load_module_from_path(file_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    loader = spec.loader
    assert loader is not None
    loader.exec_module(mod)
    return mod


def test_english_to_sql_uses_groq(tmp_path):
    # Arrange: inject fake groq that returns SQL
    inserted = _inject_minimal_deps("SELECT 1;")

    # Ensure 'state' and other agent modules can be imported: add agent dir to sys.path
    repo_root = Path(__file__).resolve().parents[1]
    agent_dir = repo_root / "agent"
    sys.path.insert(0, str(agent_dir))

    try:
        # Load english_to_sql from the agent directory as a fresh module
        mod = _load_module_from_path(agent_dir / "english_to_sql.py", "english_to_sql_test_module")

        # Act: call run()
        state = {"messages": [{"role": "user", "content": "Top movie"}], "error": None}
        result = mod.run(state)

        # Assert
        assert result.get("agent_output") == "SELECT 1;"
        assert result.get("error") is None
    finally:
        # Cleanup
        _cleanup_modules(inserted)
        if str(agent_dir) in sys.path:
            sys.path.remove(str(agent_dir))


def test_conversation_llm_with_rows_uses_groq(tmp_path):
    inserted = _inject_minimal_deps("Friendly summary.")
    repo_root = Path(__file__).resolve().parents[1]
    agent_dir = repo_root / "agent"
    sys.path.insert(0, str(agent_dir))

    try:
        mod = _load_module_from_path(agent_dir / "conversation_llm.py", "conversation_llm_test_module")

        # Provide a simple query_result and messages
        state = {
            "messages": [{"role": "user", "content": "Give me a summary"}],
            "query_result": [{"title": "A", "release_year": 2020}],
            "error": None,
        }
        result = mod.run(state)

        assert result.get("agent_output") == "Friendly summary."
        assert result.get("error") is None
    finally:
        _cleanup_modules(inserted)
        if str(agent_dir) in sys.path:
            sys.path.remove(str(agent_dir))


def test_master_agent_context_aware_routing(tmp_path):
    """Test that master agent routes based on conversation context and existing data."""
    inserted = _inject_minimal_deps("SQL")
    repo_root = Path(__file__).resolve().parents[1]
    agent_dir = repo_root / "agent"
    sys.path.insert(0, str(agent_dir))

    try:
        mod = _load_module_from_path(agent_dir / "master_agent.py", "master_agent_test_module")

        # Scenario 1: First message with no data -> should route to SQL
        state = {
            "messages": [{"role": "user", "content": "Show me top movies"}],
            "query_result": None,
            "error": None,
        }
        result = mod.run(state)
        assert result.get("route") == "english_to_sql"

        # Scenario 2: Follow-up message WITH existing data, asking about it -> should route to CONVERSATION
        # Set up fake response that returns "CONVERSATION"
        inserted.pop()  # remove groq from inserted
        sys.modules["groq"] = _make_fake_groq_module("CONVERSATION")
        inserted.append("groq")
        
        # Re-import to get fresh module with new mock
        if "master_agent_test_module" in sys.modules:
            del sys.modules["master_agent_test_module"]
        mod = _load_module_from_path(agent_dir / "master_agent.py", "master_agent_test_module")
        
        state = {
            "messages": [
                {"role": "user", "content": "Show me top movies"},
                {"role": "assistant", "content": "Here are the top movies: ..."},
                {"role": "user", "content": "Tell me more about the first one"},
            ],
            "query_result": [{"title": "Movie A", "year": 2020}, {"title": "Movie B", "year": 2021}],
            "error": None,
        }
        result = mod.run(state)
        assert result.get("route") == "conversation"
    finally:
        _cleanup_modules(inserted)
        if str(agent_dir) in sys.path:
            sys.path.remove(str(agent_dir))


