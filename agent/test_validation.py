#!/usr/bin/env python
"""Final comprehensive validation test."""

from state import AgentState
from graph import build_graph, ROUTE_KEYWORDS
from fairness_agent import run as fairness_agent
from fairness_metrics import compute_fairness_metrics

print('✓ All imports successful')

# Test state
state: AgentState = {
    'messages': [],
    'agent_output': None,
    'route': None,
    'db_schema': '',
    'error': None,
    'query_result': None,
    'last_results': None,
    'last_query': None,
    'fairness_report': None,
    'vector_search_query': None,
    'vector_embeddings': None,
    'use_vector_search': False,
}
print('✓ AgentState TypedDict works')

# Test graph
graph = build_graph()
print('✓ Graph builds successfully')

# Test metrics
results = [
    {'movie_id': 1, 'title': 'US Film', 'origin_countries': ['US'], 'vote_average': 8.0},
    {'movie_id': 2, 'title': 'FR Film', 'origin_countries': ['FR'], 'vote_average': 7.0},
]
metrics = compute_fairness_metrics(results, 'origin_countries', ['US'])
assert 'spd' in metrics
assert 'eod' in metrics
assert 'oaed' in metrics
print('✓ Fairness metrics computation works')

# Test routing
fairness_kws = ROUTE_KEYWORDS['fairness']
assert any(kw in 'why are all these american films' for kw in fairness_kws)
print('✓ Fairness routing keywords work')

print('')
print('=' * 60)
print('ALL VALIDATION CHECKS PASSED!')
print('=' * 60)
print('')
print('System is ready for fairness assessment!')

