# Fairness Assessment Agent - Implementation Summary

## Overview

A reactive fairness assessment agent has been added to the movie recommendation system. When users question the fairness of recommendations, this agent automatically activates to analyze and explain demographic biases in the results.

## Implementation Details

### 1. Updated Files

#### `agent/state.py`
Added three new fields to `AgentState`:
- `last_results: Optional[list[dict]]` - Stores ranked movie results from the previous turn
- `last_query: Optional[str]` - Stores the original user query for context
- `fairness_report: Optional[dict]` - Contains the fairness assessment results

#### `agent/graph.py`
- Added fairness route detection with 26 keywords (why, all, only, bias, unfair, diverse, etc.)
- Register fairness_agent as a new node
- Added pre-router entry point that checks for fairness keywords before delegating to master agent
- Routes fairness questions directly to fairness_agent, bypassing the SQL pipeline

#### `agent/execute_sql.py`
Modified to persist query results and user query:
- Saves `state['query_result']` to `state['last_results']` for fairness assessment
- Saves the original user question to `state['last_query']`

#### `agent/main.py`
Initialized new state fields in session state

#### `requirements.txt`
Updated to include groq (the LLM API being used)

### 2. New Files Created

#### `agent/fairness_metrics.py`
Pure Python module (no LLM calls) that computes four fairness metrics:

**Metrics:**
- **SPD (Statistical Parity Disparity)**: Representation gap
  - `SPD = P(recommended | G+) - P(recommended | G-)`
  - Negative values indicate underrepresentation of protected group

- **EOD (Equal Opportunity Disparity)**: Relevance gap among high-quality items
  - `EOD = P(recommended | relevant, G+) - P(recommended | relevant, G-)`
  - Measures fairness in promoting relevant content

- **OAED (Exposure-Adjusted Equal Opportunity Disparity)**: Position-weighted fairness
  - `OAED = (1/|G+|) * sum(e_k * y_i) - (1/|G-|) * sum(e_k * y_j)`
  - Where `e_k = 1 / log2(k + 1)` (position discount)
  - Weighs better results more heavily

- **Exposure@K**: Total discounted visibility
  - Separately computed for protected and unprotected groups
  - Shows cumulative advantage/disadvantage

**Functions:**
- `compute_fairness_metrics(results, attribute, protected_values, relevance_threshold=7.0)`
- `_matches_protected(value, attribute, protected_values)` - Handles arrays, scalars, booleans, and year ranges
- `_is_relevant(row, relevance_threshold)` - Checks if vote_average >= threshold

#### `agent/fairness_agent.py`
Complete fairness assessment orchestrator with error handling and audit logging.

**Flow:**
1. **Validation**: Check that previous recommendations exist
2. **LLM Classification**: Identify which attribute and groups to assess
   - Calls LLM with system prompt to classify fairness concern
   - LLM returns JSON with attribute, protected_values, labels, and explanation
3. **Metric Computation**: Calculate fairness metrics on original results
4. **Bias Detection**: Check against thresholds:
   - SPD < -0.2: Meaningful parity gap
   - EOD < -0.15: Equal opportunity violation
   - OAED < -0.1: Exposure-weighted bias
5. **Re-ranking (if bias detected)**:
   - Query for additional protected-group movies
   - Insert them at strategic positions
   - Recalculate metrics
6. **Explanation Generation**: LLM writes user-facing explanation with specific numbers
7. **Audit Trail**: Log to `fairness_audit` table with:
   - Original movie IDs
   - Bias metrics (before and after)
   - Re-ranking details if applied
   - Plain-English explanation

**Constants (easily adjustable):**
```python
BIAS_THRESHOLD_SPD = -0.2
BIAS_THRESHOLD_EOD = -0.15
BIAS_THRESHOLD_OAED = -0.1
```

## Usage

### Enable Fairness Assessment
Users can trigger fairness assessment with keywords:
- "Why are all these American films?"
- "How come no female directors?"
- "Aren't there any foreign films?"
- "Explain the bias in these results"
- And 26 other related keywords

### System Prompt for Classification
The agent uses a detailed system prompt to classify:
- Available attributes (director_genders, origin_countries, is_english, etc.)
- Expected JSON response format
- Special handling for year ranges

### System Prompt for Explanation
Second LLM call generates plain-language explanation that:
- Cites specific metric values
- Compares before/after if re-ranking was applied
- Uses accessible language (not jargon)
- Stays under 300 words

## Architecture Flow

```
User Turn 1: "Recommend sci-fi movies"
    ↓
[Router] → Not fairness keywords → Master Agent → SQL Pipeline
    ↓
SQL Agent generates query → Execute → Results stored in last_results
    ↓
Conversation Agent formats response
    
User Turn 2: "Why are all these American films?"
    ↓
[Router] → Detects fairness keywords → Fairness Agent
    ↓
Fairness Agent:
  1. Validates last_results exists
  2. Calls LLM to identify attribute (e.g., origin_countries)
  3. Computes metrics (SPD, EOD, OAED)
  4. Checks if bias > thresholds
  5. If biased: fetches protected items, re-ranks, recalculates metrics
  6. Calls LLM to generate explanation
  7. Returns fairness report + explanation
```

## Error Handling

- If no previous recommendations: Returns helpful message
- If LLM classification fails: Returns gracefully with generic error
- If metric calculation fails: Returns None for that metric
- If re-ranking fails: Returns original results unchanged
- If audit logging fails: Logs warning but doesn't crash
- All errors include context for debugging

## Testing

Three test files included:
1. `test_fairness_metrics.py` - Validates metric computation
2. `test_graph.py` - Verifies graph building and routing
3. `test_e2e_flow.py` - Simulates Turn 1 → Turn 2 flow

Run with:
```bash
cd agent
python test_fairness_metrics.py
python test_graph.py
python test_e2e_flow.py
```

## Backward Compatibility

- All existing tests pass (verified with test_conversation_flow.py)
- Router pre-check only triggers on fairness keywords
- Non-fairness queries follow original SQL/conversation path unchanged
- SQL pipeline unchanged (only persistence layer added)
- Master agent logic untouched

## Database Requirements

Assumes `fairness_audit` table exists with schema:
```sql
CREATE TABLE fairness_audit (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    created_at TIMESTAMPTZ,
    input_movie_ids ARRAY,
    raw_recommendation_ids ARRAY,
    bias_type TEXT,
    bias_detail JSONB,
    correction_applied TEXT,
    adjusted_recommendation_ids ARRAY,
    explanation TEXT
);
```

If table doesn't exist, audit logging is skipped gracefully.

## Future Enhancements

1. **More attributes**: Gender, age, disability representation in cast/crew
2. **Dynamic thresholds**: Configure bias thresholds per deployment
3. **Intersectionality**: Assess multiple attributes simultaneously
4. **Historical trends**: Track fairness improvements over time
5. **User preferences**: Let users set acceptable fairness thresholds
6. **Recommendation justification**: Extended explanations with specific remedies

