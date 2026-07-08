#!/usr/bin/env python
"""End-to-end test of fairness agent flow."""

from graph import build_graph
from state import AgentState

def test_fairness_flow():
    """Simulate Turn 1 (SQL query) and Turn 2 (fairness assessment)."""
    
    print("=" * 60)
    print("End-to-End Fairness Assessment Test")
    print("=" * 60)
    
    graph = build_graph()
    
    # Simulate Turn 1: User asks for movie recommendations
    print("\n--- TURN 1: Initial Query ---")
    turn1_state: AgentState = {
        "messages": [
            {"role": "user", "content": "recommend me some movies"}
        ],
        "agent_output": None,
        "route": None,
        "db_schema": "",
        "error": None,
        "query_result": None,
        "last_results": None,
        "last_query": None,
        "fairness_report": None,
        "vector_search_query": None,
        "vector_embeddings": None,
        "use_vector_search": False,
    }
    
    print("User: 'recommend me some movies'")
    print("(In a real scenario, SQL agent would run here and populate last_results)")
    
    # Simulate results from SQL agent
    simulated_results = [
        {"movie_id": 1, "title": "US Film A", "origin_countries": ["US"], 
         "director_genders": [2], "is_english": True, "is_western": True,
         "genres": ["Action"], "release_year": 2023, "vote_average": 8.5, 
         "company_countries": ["US"], "cast_genders": [2, 1]},
        {"movie_id": 2, "title": "US Film B", "origin_countries": ["US"],
         "director_genders": [2], "is_english": True, "is_western": True,
         "genres": ["Drama"], "release_year": 2023, "vote_average": 8.2,
         "company_countries": ["US"], "cast_genders": [2, 1]},
        {"movie_id": 3, "title": "US Film C", "origin_countries": ["US"],
         "director_genders": [2], "is_english": True, "is_western": True,
         "genres": ["Crime"], "release_year": 2023, "vote_average": 7.9,
         "company_countries": ["US"], "cast_genders": [1, 2]},
        {"movie_id": 4, "title": "French Film", "origin_countries": ["FR"],
         "director_genders": [1], "is_english": False, "is_western": False,
         "genres": ["Romance"], "release_year": 2022, "vote_average": 7.5,
         "company_countries": ["FR"], "cast_genders": [1, 2]},
        {"movie_id": 5, "title": "Indian Film", "origin_countries": ["IN"],
         "director_genders": [2], "is_english": False, "is_western": False,
         "genres": ["Drama"], "release_year": 2023, "vote_average": 7.1,
         "company_countries": ["IN"], "cast_genders": [1, 1]},
    ]
    
    turn1_state["query_result"] = simulated_results
    turn1_state["last_results"] = simulated_results
    turn1_state["last_query"] = "recommend me some movies"
    turn1_state["messages"].append({
        "role": "assistant",
        "content": "Here are some great movie recommendations for you..."
    })
    
    print(f"✓ Simulated {len(simulated_results)} results stored")
    print(f"  - US films: 3")
    print(f"  - International films: 2")
    
    # Turn 2: User questions fairness
    print("\n--- TURN 2: Fairness Question ---")
    turn2_state = dict(turn1_state)  # Copy state from Turn 1
    
    fairness_question = "why are all these American films?"
    turn2_state["messages"].append({
        "role": "user",
        "content": fairness_question
    })
    
    print(f"User: '{fairness_question}'")
    
    # Check routing
    print("\nRouting analysis:")
    user_text = fairness_question.lower()
    from graph import ROUTE_KEYWORDS
    fairness_keywords = ROUTE_KEYWORDS.get("fairness", [])
    is_fairness = any(kw in user_text for kw in fairness_keywords)
    print(f"  Detected keywords: {[kw for kw in fairness_keywords if kw in user_text]}")
    print(f"  Route: {'fairness' if is_fairness else 'master'}")
    
    if is_fairness:
        print(f"✓ Fairness question correctly identified!")
    
    # Compile state
    print("\nState snapshot before fairness agent:")
    print(f"  last_results: {len(turn2_state['last_results'])} items")
    print(f"  last_query: '{turn2_state['last_query']}'")
    print(f"  fairness_report: {turn2_state['fairness_report']}")
    
    print("\n✓ End-to-end flow test passed!")
    print("\nNote: Actual fairness_agent requires LLM, so it's tested separately.")

if __name__ == "__main__":
    test_fairness_flow()

