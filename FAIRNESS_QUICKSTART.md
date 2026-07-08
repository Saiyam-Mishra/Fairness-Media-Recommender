# Fairness Agent - Quick Start

## For Users

Ask about fairness using patterns like:
- "Why are all these American films?"
- "How come no female directors?"
- "Explain the diversity of these results"
- "Aren't there any international films?"

The system will analyze, detect bias, and optionally re-rank for fairness.

## For Developers

### Run Tests
```bash
cd agent
python test_fairness_metrics.py    # Test metrics
python test_graph.py              # Test routing
python test_e2e_flow.py           # Test end-to-end flow
```

### Adjust Bias Thresholds
Edit `agent/fairness_agent.py`:
```python
BIAS_THRESHOLD_SPD = -0.2   # Lower = stricter
BIAS_THRESHOLD_EOD = -0.15
BIAS_THRESHOLD_OAED = -0.1
```

### Understand Metrics
- **SPD**: Representation gap (negative = underrepresented)
- **EOD**: Quality/relevance gap (negative = quality gap)
- **OAED**: Position-weighted gap (negative = ranked lower)
- **Exposure@K**: Cumulative visibility

### Key Files
- `agent/fairness_metrics.py` - Pure metric computation
- `agent/fairness_agent.py` - Full assessment orchestration
- `agent/graph.py` - Routing logic with fairness keywords
- `FAIRNESS_IMPLEMENTATION.md` - Complete documentation

### Database Table
Create fairness_audit table for audit logging:
```sql
CREATE TABLE fairness_audit (
    id SERIAL PRIMARY KEY,
    session_id TEXT,
    created_at TIMESTAMPTZ,
    raw_recommendation_ids ARRAY,
    bias_type TEXT,
    bias_detail JSONB,
    correction_applied TEXT,
    adjusted_recommendation_ids ARRAY,
    explanation TEXT
);
```

If not present, audit logging is skipped gracefully.

### Performance
- LLM calls: 2-3 seconds typical
- Metric computation: O(n) very fast
- Re-ranking: adds database query if bias detected

### Customization
1. Edit thresholds in fairness_agent.py
2. Modify re-ranking strategy in _attempt_rerank()
3. Adjust LLM system prompts
4. Add new attributes to FAIRNESS_ATTRIBUTES dict

See FAIRNESS_IMPLEMENTATION.md for full details.

