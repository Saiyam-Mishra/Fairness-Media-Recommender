"""Fairness assessment agent for movie recommendations.

Analyzes recommendation fairness when users question attribute representation,
computes parody/equal opportunity/exposure metrics, and optionally re-ranks
results for improved fairness with an audit trail.
"""

import os
import json
import math
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
from groq import Groq
from dotenv import load_dotenv

from state import AgentState
from fairness_metrics import compute_fairness_metrics

from sentence_transformers import SentenceTransformer
_embed_model = SentenceTransformer("all-MiniLM-L6-v2")

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

# Bias detection thresholds (lower = more stringent)
BIAS_THRESHOLD_SPD = -0.2  # Disparate impact threshold
BIAS_THRESHOLD_EOD = -0.15  # Equal opportunity threshold
BIAS_THRESHOLD_OAED = -0.1  # Exposure-weighted bias threshold

_MODEL = "llama-3.3-70b-versatile"

# Available fairness assessment attributes
FAIRNESS_ATTRIBUTES = {
    "director_genders": "array of integers (0=unknown, 1=female, 2=male, 3=non-binary)",
    "origin_countries": "array of ISO country codes e.g. ['US'], ['IN','GB']",
    "is_english": "boolean",
    "is_western": "boolean (origin in US/GB/AU/CA/NZ/IE)",
    "genres": "array of strings e.g. ['Action', 'Drama']",
    "release_year": "integer",
    "company_countries": "array of ISO country codes of production companies",
    "top_cast_genders": "array of integers (0=unknown, 1=female, 2=male, 3=non-binary)",
    "spoken_languages": "array of ISO language codes",
}

_ARRAY_ATTRIBUTES = {
    "director_genders",
    "origin_countries",
    "genres",
    "company_countries",
    "top_cast_genders",
    "spoken_languages",
}

_FAIRNESS_SYSTEM_PROMPT = f"""You are a fairness analyst for a movie recommendation system.
The user has questioned the fairness of a set of movie recommendations.

Your job:
1. Identify which attribute of the recommendations the user is concerned about.
2. Define the protected group (G+) — the underrepresented group the user is asking about.
3. Define the unprotected group (G-) — the overrepresented group.

Available attributes in movie_summary:
{json.dumps(FAIRNESS_ATTRIBUTES, indent=2)}

Rules:
- Respond ONLY in valid JSON matching the schema provided. No explanation, no markdown.
- protected_values must be the exact values that identify G+ (the UNDERREPRESENTED group) in the attribute.
  For origin_countries: if the user says "why all American?", protected_values = non-US country codes (e.g. ["IN","JP","KR","FR","DE","GB"]) NOT ["US"].
  For director_genders: if the user says "why all male directors?", protected_values = [1, 3] (female, non-binary) NOT [2].
  The values you provide will be used in a SQL WHERE clause to FETCH MORE of the underrepresented group.
  If protected_values contains the dominant group's values, the system will fetch more of the dominant group — the opposite of what is needed.
  For cases where the protected group is defined by exclusion (e.g. "non-US"), 
  you may use: "protected_values": {{"not": ["US"]}} to mean "everything except US".
- For regional queries like "Asian cinema", "Bollywood", "European films", return explicit 
  country codes for that region rather than using the "not" pattern.
  e.g. "Asian cinema" -> ["CN", "JP", "KR", "IN", "TH", "TW", "HK", "VN", "ID", "PH"]
  Reserve the "not" pattern only for simple binary splits like "non-US" or "non-English".
- For array columns, protected_values are the values you check membership for.
- For boolean columns, protected_values will be [true] or [false].
- For release_year, protected_values will be a range expressed as
  {{"min": int, "max": int}} — this signals a year range.

Expected JSON schema:
{{
  "attribute": "string (one of the attributes listed above)",
  "protected_values": "list or dict with 'min'/'max' keys",
  "protected_label": "string describing the protected group (e.g. 'non-US films')",
  "unprotected_label": "string describing the unprotected group (e.g. 'US films')",
  "explanation_of_grouping": "string explaining why you chose this attribute and groups"
}}"""

_EXPLANATION_SYSTEM_PROMPT = """You are a fairness analyst explaining movie recommendation metrics to users.

You are given:
- Metric values (SPD, EOD, OAED, Exposure@K) before and optionally after re-ranking
- The attribute assessed (e.g., director gender, origin country)
- A ranked list of movie results
- Protected/unprotected labels (e.g., "female directors" vs "male directors")

Write a concise, natural-language explanation that:
1. States what attribute was analyzed
2. Cites the specific metric values and what they mean
3. If no bias was detected, confirm fairness
4. If bias was detected:
   - Describe the bias (e.g., "only 15% of top 10 were female directors")
   - Show the before/after metrics if re-ranking was applied
   - Explain what changed and why
5. SPD of 0 indicates perfect parity. Both strongly negative (protected underrepresented) 
  and strongly positive (protected overrepresented) values indicate imbalance.
  Do not describe a positive SPD as "more balanced" — it means over-correction.
6. Keep the explanation under 300 words
7. Use plain language, not jargon

Do NOT make up numbers — use only the metrics provided."""


def _get_db_connection():
    """Connect to PostgreSQL database."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT") or 5432),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def _audit_fairness_assessment(
    session_id: str | None,
    bias_type: str,
    bias_detail: dict,
    explanation: str,
    original_movie_ids: list[int],
    reranked_movie_ids: list[int] | None,
) -> None:
    """Log fairness assessment to the fairness_audit table."""
    try:
        conn = _get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO fairness_audit 
            (session_id, created_at, raw_recommendation_ids, bias_type, bias_detail, 
             correction_applied, adjusted_recommendation_ids, explanation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                datetime.utcnow().isoformat(),
                original_movie_ids,
                bias_type,
                json.dumps(bias_detail),
                "re_ranking" if reranked_movie_ids else None,
                reranked_movie_ids,
                explanation,
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        # Gracefully skip audit if the table doesn't exist or there's a DB error
        print(f"[fairness_agent] Warning: could not audit assessment: {e}")


def _call_fairness_classifier_llm(user_question: str, results_sample: str) -> dict | None:
    user_prompt = f"""User's fairness question: "{user_question}"

Sample of current recommendations (title + key attributes):
{results_sample}

Analyze the user's concern and respond in JSON with the schema specified in the system prompt."""

    for attempt in range(3):  # retry up to 3 times
        try:
            response = client.chat.completions.create(
                model=_MODEL,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": _FAIRNESS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = response.choices[0].message.content.strip()
            if not text:
                print(f"[fairness_agent] empty response on attempt {attempt + 1}, retrying...")
                continue
            result = json.loads(text)
            print(f"[fairness_agent] LLM classification: {result}")
            return result
        except json.JSONDecodeError as e:
            print(f"[fairness_agent] JSON parse failed on attempt {attempt + 1}: {e}, retrying...")
        except Exception as e:
            print(f"[fairness_agent] LLM classification failed on attempt {attempt + 1}: {e}")
            return None  # non-JSON errors (network, auth) won't be fixed by retrying

    print("[fairness_agent] all retries exhausted")
    return None


def _call_explanation_llm(
    metrics_before: dict,
    metrics_after: dict | None,
    attribute: str,
    protected_label: str,
    unprotected_label: str,
    results: list[dict],
) -> str:
    """Ask LLM to generate a user-facing explanation of the fairness findings."""
    results_text = "\n".join(
        f"  {i+1}. {r.get('title', 'Unknown')} (id={r.get('movie_id', '?')})"
        for i, r in enumerate(results[:10])
    )

    metrics_text = f"""METRICS BEFORE:
- SPD (Statistical Parity Disparity): {metrics_before.get("spd")}
- EOD (Equal Opportunity Disparity): {metrics_before.get("eod")}
- OAED (Exposure-Adjusted Equal Opportunity): {metrics_before.get("oaed")}
- Exposure@K: protected={metrics_before.get("exposure_k", {}).get("protected")}, 
              unprotected={metrics_before.get("exposure_k", {}).get("unprotected")}
- Representation: {metrics_before.get("protected_count")} {protected_label} out of {metrics_before.get("k")} results"""

    if metrics_after:
        metrics_text += f"""

METRICS AFTER RE-RANKING:
- SPD: {metrics_after.get("spd")}
- EOD: {metrics_after.get("eod")}
- OAED: {metrics_after.get("oaed")}
- Exposure@K: protected={metrics_after.get("exposure_k", {}).get("protected")}, 
              unprotected={metrics_after.get("exposure_k", {}).get("unprotected")}
- Representation: {metrics_after.get("protected_count")} {protected_label} out of {metrics_after.get("k")} results

RERANKED RESULTS:
{results_text}"""
    else:
        metrics_text += f"""

RESULTS:
{results_text}"""

    try:
        user_prompt = f"""Attribute analyzed: {attribute}
Protected group: {protected_label}
Unprotected group: {unprotected_label}

{metrics_text}

Write a concise, natural-language explanation following the guidelines in the system prompt."""

        response = client.chat.completions.create(
            model=_MODEL,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _EXPLANATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = response.choices[0].message.content.strip()
        print(f"[fairness_agent] Explanation generated (len={len(text)} chars)")
        return text
    except Exception as e:
        print(f"[fairness_agent] Explanation LLM failed: {e}")
        return f"Fairness assessment complete. SPD={metrics_before.get('spd')}, EOD={metrics_before.get('eod')}, OAED={metrics_before.get('oaed')}"


def _has_bias(metrics: dict) -> bool:
    """Check if the metrics indicate bias above configured thresholds."""
    spd = metrics.get("spd")
    eod = metrics.get("eod")
    oaed = metrics.get("oaed")

    if spd is not None and spd < BIAS_THRESHOLD_SPD:
        return True
    if eod is not None and eod < BIAS_THRESHOLD_EOD:
        return True
    if oaed is not None and oaed < BIAS_THRESHOLD_OAED:
        return True
    return False


def _build_protected_where_clause(attribute: str, protected_values: Any) -> tuple[str, list[Any]]:
    # Negation pattern — must be checked first, before any list wrapping
    if isinstance(protected_values, dict) and "not" in protected_values:
        not_values = protected_values["not"]
        if attribute in _ARRAY_ATTRIBUTES:
            return f"NOT ({attribute} && %s::text[])", [not_values]
        return f"{attribute} != ALL(%s)", [not_values]

    # Also handle if LLM wrapped it in a list: [{"not": [...]}]
    if (isinstance(protected_values, list) and len(protected_values) == 1
            and isinstance(protected_values[0], dict) and "not" in protected_values[0]):
        not_values = protected_values[0]["not"]
        if attribute in _ARRAY_ATTRIBUTES:
            return f"NOT ({attribute} && %s::text[])", [not_values]
        return f"{attribute} != ALL(%s)", [not_values]

    """Build a parameterized SQL predicate for protected-group membership."""
    if attribute == "release_year" and isinstance(protected_values, dict):
        min_year = protected_values.get("min")
        max_year = protected_values.get("max")
        if min_year is None or max_year is None:
            raise ValueError("release_year protected_values must include min and max")
        return f"{attribute} BETWEEN %s AND %s", [int(min_year), int(max_year)]

    values = protected_values if isinstance(protected_values, list) else [protected_values]

    if attribute in _ARRAY_ATTRIBUTES:
        integer_array_attributes = {"director_genders", "top_cast_genders"}
        cast_type = "smallint[]" if attribute in integer_array_attributes else "text[]"
        return f"{attribute} && %s::{cast_type}", [values]

    # Scalar columns: for booleans, use direct equality; for others use ANY.
    if attribute in ("is_english", "is_western", "adult"):
        # Boolean: if protected_values is [False], use `NOT is_english`; if [True], use `is_english`
        if len(values) == 1 and isinstance(values[0], bool):
            bool_val = values[0]
            if bool_val:
                return f"{attribute} = TRUE", []
            else:
                return f"{attribute} = FALSE", []
        # Fallback for mixed booleans
        return f"{attribute} = ANY(%s)", [values]

    # Scalar non-boolean: check membership via ANY.
    return f"{attribute} = ANY(%s)", [values]




def _fetch_supplementary_results(
    current_results: list[dict],
    attribute: str,
    protected_values: Any,
    original_query: str,
) -> tuple[list[dict], str]:
    """Fetch additional protected-group items using SQL against movie_summary."""
    excluded_ids = [r.get("movie_id") for r in current_results if r.get("movie_id") is not None]
    print(f"[fairness_agent] excluded_ids: {excluded_ids}")
    genre_hints: list[str] = []
    for row in current_results[:5]:
        genres = row.get("genres") or []
        if isinstance(genres, list):
            for g in genres:
                if g and g not in genre_hints:
                    genre_hints.append(g)
        if len(genre_hints) >= 4:
            break

    protected_clause, protected_params = _build_protected_where_clause(attribute, protected_values)

    # Build WHERE conditions
    where_parts = [protected_clause]
    params = list(protected_params)

    # Exclude already-recommended movies if any
    if excluded_ids:
        where_parts.insert(0, "movie_id != ALL(%s)")
        params.insert(0, excluded_ids)

    # Add vote_average check
    where_parts.append("vote_average IS NOT NULL")

    # Require dominant genre to be present
    if genre_hints:
        where_parts.append("%s = ANY(genres)")
        params.append(genre_hints[0])

    # Embed the original query for semantic ranking
    where_parts.append("embedding IS NOT NULL")
    query_embedding = _embed_model.encode(
        original_query, normalize_embeddings=True
    ).tolist()

    where_clause = " AND ".join(where_parts)
    sql = f"""
        SELECT movie_id, title, release_year, vote_average, overview, genres,
               director_genders, origin_countries, is_english, is_western,
               company_countries, spoken_languages
        FROM movie_summary
        WHERE {where_clause}
        ORDER BY embedding <=> %s::vector, vote_average DESC, popularity DESC NULLS LAST
        LIMIT 20
    """
    params.append(query_embedding)

    conn = _get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    print(f"[fairness_agent] Fetching supplementary results with SQL:\n{sql}\nparams={params}")
    cur.execute(sql, params)
    seen_ids = set()
    rows = []
    for r in cur.fetchall():
        row = dict(r)
        mid = row.get("movie_id")
        if mid not in seen_ids:
            seen_ids.add(mid)
            rows.append(row)
    cur.close()
    conn.close()
    return rows, sql


def _inject_improved_results(
    current_results: list[dict],
    supplementary_rows: list[dict],
    attribute: str,
    protected_values: Any,
) -> tuple[list[dict], int]:
    """Inject supplementary protected items near the top and drop lower-ranked items."""
    from fairness_metrics import _matches_protected

    if not supplementary_rows:
        return current_results, 0

    k = len(current_results)
    if k == 0:
        return current_results, 0

    existing_ids = {r.get("movie_id") for r in current_results}
    protected_now = sum(
        1 for r in current_results if _matches_protected(r.get(attribute), attribute, protected_values)
    )
    target_protected = max(protected_now + 1, math.ceil(0.4 * k))
    needed = max(0, target_protected - protected_now)
    if needed == 0:
        return current_results, 0

    candidates: list[dict] = []
    for row in supplementary_rows:
        movie_id = row.get("movie_id")
        if movie_id in existing_ids:
            continue
        if not _matches_protected(row.get(attribute), attribute, protected_values):
            continue
        candidates.append(row)
        if len(candidates) >= needed:
            break

    if not candidates:
        return current_results, 0

    updated = list(current_results)
    inserted = 0
    for candidate in candidates:
        insert_at = min(2 + inserted, max(0, len(updated) - 1))
        updated.insert(insert_at, candidate)
        existing_ids.add(candidate.get("movie_id"))  # track inserted IDs

        removed = False
        for idx in range(len(updated) - 1, insert_at, -1):
            if not _matches_protected(updated[idx].get(attribute), attribute, protected_values):
                updated.pop(idx)
                removed = True
                break
        if not removed and len(updated) > k:
            for idx in range(len(updated) - 1, -1, -1):
                if not _matches_protected(updated[idx].get(attribute), attribute, protected_values):
                    updated.pop(idx)
                    break
            else:
                updated.pop()
        inserted += 1

    return updated[:k], inserted


def run(state: AgentState) -> AgentState:
    """Assess fairness of previous recommendations.

    Reads user_question and last_results from state, identifies the fairness concern,
    computes metrics, optionally re-ranks for fairness, and returns explanation.
    """
    messages = state.get("messages", [])
    last_results = state.get("last_results")
    original_query = state.get("last_query") or ""

    print(f"[fairness_agent] last_results ids: {[r.get('movie_id') for r in last_results]}")

    # Extract the user's fairness question
    user_question = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_question = msg.get("content", "")
            break

    if not user_question:
        return {
            **state,
            "agent_output": "No fairness question detected.",
            "fairness_report": None,
        }

    if not last_results:
        return {
            **state,
            "agent_output": "No previous recommendations to assess for fairness. Please get movie recommendations first.",
            "fairness_report": None,
        }

    print(
        f"[fairness_agent] Assessing fairness for {len(last_results)} results in response to: {user_question}"
    )

    # Sample the results for display to LLM
    results_sample_lines = []
    for i, r in enumerate(last_results[:5], start=1):
        sample_row = {
            "title": r.get("title", "Unknown"),
            "origin_countries": r.get("origin_countries"),
            "director_genders": r.get("director_genders"),
            "is_english": r.get("is_english"),
            "genres": r.get("genres"),
            "release_year": r.get("release_year"),
        }
        results_sample_lines.append(f"{i}. {json.dumps(sample_row, default=str)}")
    results_sample = "\n".join(results_sample_lines)

    # Ask LLM to identify the fairness concern
    classification = _call_fairness_classifier_llm(user_question, results_sample)
    if not classification:
        return {
            **state,
            "agent_output": "Could not classify the fairness concern. Please rephrase your question.",
            "fairness_report": None,
        }

    attribute = classification.get("attribute")
    protected_values = classification.get("protected_values")
    print(f"[fairness_agent] protected_values type={type(protected_values)} value={protected_values}")
    protected_label = classification.get("protected_label", "protected group")
    unprotected_label = classification.get("unprotected_label", "unprotected group")

    if not attribute or protected_values is None:
        return {
            **state,
            "agent_output": "Could not identify a valid fairness attribute. Please be more specific.",
            "fairness_report": None,
        }

    # Compute fairness metrics on current results
    metrics_before = compute_fairness_metrics(
        last_results, attribute, protected_values, relevance_threshold=7.0
    )

    bias_detected = _has_bias(metrics_before)
    metrics_after = None
    reranked_results = list(last_results)
    supplementary_count = 0
    supplementary_sql = None

    print(
        f"[fairness_agent] Attribute={attribute}, SPD={metrics_before.get('spd')}, "
        f"EOD={metrics_before.get('eod')}, OAED={metrics_before.get('oaed')}, bias={bias_detected}"
    )

    if bias_detected:
        print("[fairness_agent] Bias detected — fetching supplementary SQL results")
        try:
            supplementary_rows, supplementary_sql = _fetch_supplementary_results(
                current_results=last_results,
                attribute=attribute,
                protected_values=protected_values,
                original_query=original_query or user_question,
            )
            reranked_results, supplementary_count = _inject_improved_results(
                current_results=last_results,
                supplementary_rows=supplementary_rows,
                attribute=attribute,
                protected_values=protected_values,
            )
        except Exception as exc:
            print(f"[fairness_agent] supplementary SQL flow failed: {exc}")
            reranked_results = list(last_results)

        if reranked_results != last_results:
            metrics_after = compute_fairness_metrics(
                reranked_results, attribute, protected_values, relevance_threshold=7.0
            )
            print(
                f"[fairness_agent] After SQL supplementation: SPD={metrics_after.get('spd')}, "
                f"EOD={metrics_after.get('eod')}, OAED={metrics_after.get('oaed')}, "
                f"supplemented={supplementary_count}"
            )
        else:
            print("[fairness_agent] No improved result set produced from SQL supplementation")

    # Generate explanation
    explanation = _call_explanation_llm(
        metrics_before,
        metrics_after or None,
        attribute,
        protected_label,
        unprotected_label,
        reranked_results,
    )

    # Build report
    fairness_report = {
        "attribute": attribute,
        "protected_label": protected_label,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after or metrics_before,
        "reranked_results": reranked_results,
        "supplementary_count": supplementary_count,
        "supplementary_sql": supplementary_sql,
        "explanation": explanation,
    }

    # Audit
    original_ids = [r.get("movie_id") for r in last_results]
    reranked_ids = [r.get("movie_id") for r in reranked_results] if reranked_results != last_results else None
    _audit_fairness_assessment(
        session_id=None,  # Could be passed from state if available
        bias_type=attribute if bias_detected else "no_bias",
        bias_detail={
            "spd": metrics_before.get("spd"),
            "eod": metrics_before.get("eod"),
            "oaed": metrics_before.get("oaed"),
        },
        explanation=explanation,
        original_movie_ids=original_ids,
        reranked_movie_ids=reranked_ids,
    )

    return {
        **state,
        "agent_output": {
            "explanation": explanation,
            "results": reranked_results,
        },
        "query_result": reranked_results,
        "last_results": reranked_results,
        "fairness_report": fairness_report,
    }





