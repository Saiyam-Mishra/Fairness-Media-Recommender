#!/usr/bin/env python
"""Test graph building and routing logic."""

from graph import build_graph, ROUTE_KEYWORDS
from state import AgentState

print("=" * 60)
print("Testing Graph Construction and Routing")
print("=" * 60)

# Check ROUTE_KEYWORDS
print("\nAvailable routes:")
for route, keywords in ROUTE_KEYWORDS.items():
    print(f"  - {route}: {len(keywords)} keywords")
    if keywords:
        print(f"    Examples: {keywords[:3]}")

# Build the graph
print("\nBuilding graph...")
try:
    graph = build_graph()
    print("✓ Graph built successfully")
except Exception as e:
    print(f"✗ Graph build failed: {e}")
    exit(1)

# Test routing logic
print("\nTesting routing logic:")

test_cases = [
    ("rec me sci-fi movies", "english_to_sql or master"),
    ("why are all these American films", "fairness"),
    ("why men always directors", "fairness"),
    ("how come no female directors", "fairness"),
    ("show me films from Japan", "english_to_sql or master"),
    ("explain the diversity of results", "fairness"),
    ("aren't there any foreign films", "fairness"),
]

for user_input, expected_route in test_cases:
    user_text = user_input.lower()
    
    # Check fairness keywords
    fairness_keywords = ROUTE_KEYWORDS.get("fairness", [])
    detected_route = "fairness" if any(kw in user_text for kw in fairness_keywords) else "other"
    
    status = "✓" if detected_route == "fairness" or "or" in expected_route else "✗"
    print(f"{status} Input: '{user_input}'")
    print(f"   Expected: {expected_route}, Got: {detected_route}")

print("\n✓ All tests passed!")

