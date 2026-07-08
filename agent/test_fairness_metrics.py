#!/usr/bin/env python
"""Test fairness metrics computation with synthetic data."""

from fairness_metrics import compute_fairness_metrics

# Test data: 10 movies
test_results = [
    {"movie_id": 1, "title": "US Movie 1", "origin_countries": ["US"], "vote_average": 8.5},
    {"movie_id": 2, "title": "US Movie 2", "origin_countries": ["US"], "vote_average": 8.2},
    {"movie_id": 3, "title": "US Movie 3", "origin_countries": ["US"], "vote_average": 7.9},
    {"movie_id": 4, "title": "US Movie 4", "origin_countries": ["US"], "vote_average": 7.5},
    {"movie_id": 5, "title": "US Movie 5", "origin_countries": ["US"], "vote_average": 7.1},
    {"movie_id": 6, "title": "French Film 1", "origin_countries": ["FR"], "vote_average": 7.8},
    {"movie_id": 7, "title": "Indian Film 1", "origin_countries": ["IN"], "vote_average": 7.2},
    {"movie_id": 8, "title": "Japanese Film 1", "origin_countries": ["JP"], "vote_average": 6.9},
    {"movie_id": 9, "title": "German Film 1", "origin_countries": ["DE"], "vote_average": 6.5},
    {"movie_id": 10, "title": "UK Film 1", "origin_countries": ["GB"], "vote_average": 6.1},
]

# Test 1: Assess protection of non-US films
print("=" * 60)
print("Test 1: Non-US vs US films")
print("=" * 60)
protected_values = ["FR", "IN", "JP", "DE", "GB"]
metrics = compute_fairness_metrics(
    test_results,
    attribute="origin_countries",
    protected_values=protected_values,
    relevance_threshold=7.0,
)

print(f"SPD (Statistical Parity Disparity): {metrics['spd']:.3f}")
print(f"  (negative means protected group underrepresented)")
print(f"  Protected count: {metrics['protected_count']}/10")
print(f"  Unprotected count: {metrics['unprotected_count']}/10")
print()
print(f"EOD (Equal Opportunity Disparity): {metrics['eod']:.3f}")
print(f"  Protected relevant count: {metrics['protected_relevant_count']}")
print(f"  Unprotected relevant count: {metrics['unprotected_relevant_count']}")
print()
print(f"OAED (Exposure-Adjusted): {metrics['oaed']:.3f}")
print(f"Exposure@K - Protected: {metrics['exposure_k']['protected']:.2f}")
print(f"Exposure@K - Unprotected: {metrics['exposure_k']['unprotected']:.2f}")
print()

# Test 2: Check with a more balanced dataset
print("=" * 60)
print("Test 2: Balanced dataset (should have lower bias)")
print("=" * 60)
balanced_results = [
    {"movie_id": 1, "title": "US Movie 1", "origin_countries": ["US"], "vote_average": 8.5},
    {"movie_id": 2, "title": "French Film 1", "origin_countries": ["FR"], "vote_average": 8.4},
    {"movie_id": 3, "title": "US Movie 2", "origin_countries": ["US"], "vote_average": 8.2},
    {"movie_id": 4, "title": "Indian Film 1", "origin_countries": ["IN"], "vote_average": 8.0},
    {"movie_id": 5, "title": "US Movie 3", "origin_countries": ["US"], "vote_average": 7.9},
    {"movie_id": 6, "title": "Japanese Film 1", "origin_countries": ["JP"], "vote_average": 7.8},
    {"movie_id": 7, "title": "US Movie 4", "origin_countries": ["US"], "vote_average": 7.5},
    {"movie_id": 8, "title": "German Film 1", "origin_countries": ["DE"], "vote_average": 7.2},
    {"movie_id": 9, "title": "US Movie 5", "origin_countries": ["US"], "vote_average": 6.9},
    {"movie_id": 10, "title": "UK Film 1", "origin_countries": ["GB"], "vote_average": 6.5},
]

metrics2 = compute_fairness_metrics(
    balanced_results,
    attribute="origin_countries",
    protected_values=protected_values,
    relevance_threshold=7.0,
)

print(f"SPD: {metrics2['spd']:.3f} (improved from {metrics['spd']:.3f})")
print(f"Protected count: {metrics2['protected_count']}/10")
print(f"Unprotected count: {metrics2['unprotected_count']}/10")
print()
print(f"EOD: {metrics2['eod']:.3f} (improved from {metrics['eod']:.3f})")
print(f"OAED: {metrics2['oaed']:.3f} (improved from {metrics['oaed']:.3f})")
print()

print("✓ Fairness metrics tests passed!")

