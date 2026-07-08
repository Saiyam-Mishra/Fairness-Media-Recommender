"""Pure fairness metric helpers for ranked movie recommendation results."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any


_ARRAY_COLUMNS = {
    "director_genders",
    "origin_countries",
    "genres",
    "company_countries",
    "cast_genders",
    "spoken_languages",
}

_BOOLEAN_COLUMNS = {"is_english", "is_western"}


def _is_non_string_iterable(value: Any) -> bool:
    return isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict))


def _matches_protected(value: Any, attribute: str, protected_values: Any) -> bool:
    if value is None:
        return False

    # Handle negation pattern: {"not": ["US"]} means "not in this list"
    if isinstance(protected_values, dict) and "not" in protected_values:
        not_values = set(protected_values["not"])
        if _is_non_string_iterable(value):
            return not any(item in not_values for item in value if item is not None)
        return value not in not_values

    # Handle wrapped negation: [{"not": ["US"]}]
    if (isinstance(protected_values, list) and len(protected_values) == 1
            and isinstance(protected_values[0], dict) and "not" in protected_values[0]):
        not_values = set(protected_values[0]["not"])
        if _is_non_string_iterable(value):
            return not any(item in not_values for item in value if item is not None)
        return value not in not_values

    if value is None:
        return False

    if attribute == "release_year" and isinstance(protected_values, dict):
        year = value[0] if _is_non_string_iterable(value) else value
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            return False
        min_year = protected_values.get("min")
        max_year = protected_values.get("max")
        if min_year is not None and year_int < int(min_year):
            return False
        if max_year is not None and year_int > int(max_year):
            return False
        return True

    if _is_non_string_iterable(value):
        protected_set = set(protected_values if _is_non_string_iterable(protected_values) else [protected_values])
        return any(item in protected_set for item in value if item is not None)

    protected_set = set(protected_values if _is_non_string_iterable(protected_values) else [protected_values])
    return value in protected_set


def _is_relevant(row: dict, relevance_threshold: float) -> bool:
    try:
        score = row.get("vote_average")
        return score is not None and float(score) >= relevance_threshold
    except (TypeError, ValueError):
        return False


def compute_fairness_metrics(
    results: list[dict],
    attribute: str,
    protected_values: list[Any] | dict[str, Any],
    relevance_threshold: float = 7.0,
) -> dict:
    """Computes SPD, EOD, OAED, and Exposure@K for a ranked result list.

    Args:
        results: ranked list of movie dicts (position 0 = rank 1)
        attribute: the movie_summary column being evaluated
        protected_values: values of `attribute` that identify the protected group G+
        relevance_threshold: vote_average above which a result is considered relevant

    Returns:
        Dict with parity, opportunity, and exposure metrics plus supporting counts.
    """
    ranked_results = results or []
    k = len(ranked_results)

    protected_count = 0
    unprotected_count = 0
    protected_relevant_count = 0
    unprotected_relevant_count = 0
    protected_discounted_relevance = 0.0
    unprotected_discounted_relevance = 0.0
    protected_exposure = 0.0
    unprotected_exposure = 0.0

    for index, row in enumerate(ranked_results, start=1):
        discount = 1.0 / math.log2(index + 1)
        protected = _matches_protected(row.get(attribute), attribute, protected_values)
        relevant = _is_relevant(row, relevance_threshold)

        if protected:
            protected_count += 1
            protected_exposure += discount
            if relevant:
                protected_relevant_count += 1
                protected_discounted_relevance += discount
        else:
            unprotected_count += 1
            unprotected_exposure += discount
            if relevant:
                unprotected_relevant_count += 1
                unprotected_discounted_relevance += discount

    def _safe_ratio(numerator: float, denominator: int) -> float | None:
        return None if denominator == 0 else numerator / denominator

    # For a ranked recommendation list, SPD is best read as exposure share gap
    # between the protected and unprotected groups.
    protected_share = _safe_ratio(float(protected_count), k)
    unprotected_share = _safe_ratio(float(unprotected_count), k)
    spd = None if protected_share is None or unprotected_share is None else protected_share - unprotected_share

    protected_relevance_rate = _safe_ratio(float(protected_relevant_count), protected_count)
    unprotected_relevance_rate = _safe_ratio(float(unprotected_relevant_count), unprotected_count)
    eod = (
        None
        if protected_relevance_rate is None or unprotected_relevance_rate is None
        else protected_relevance_rate - unprotected_relevance_rate
    )

    protected_oaed = _safe_ratio(protected_discounted_relevance, protected_count)
    unprotected_oaed = _safe_ratio(unprotected_discounted_relevance, unprotected_count)
    oaed = None if protected_oaed is None or unprotected_oaed is None else protected_oaed - unprotected_oaed

    return {
        "spd": spd,
        "eod": eod,
        "oaed": oaed,
        "exposure_k": {
            "protected": None if protected_count == 0 else protected_exposure,
            "unprotected": None if unprotected_count == 0 else unprotected_exposure,
        },
        "protected_count": protected_count,
        "unprotected_count": unprotected_count,
        "protected_relevant_count": protected_relevant_count,
        "unprotected_relevant_count": unprotected_relevant_count,
        "k": k,
    }

