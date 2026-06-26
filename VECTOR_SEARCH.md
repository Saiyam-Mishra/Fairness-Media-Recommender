# Vector Search Integration

## Overview

The fairness_recommender system now integrates **semantic vector search** with traditional SQL queries. This allows natural language queries with mood/theme/atmosphere descriptions to be matched against movie embeddings (created via Sentence Transformers).

## How It Works

### 1. Query Analysis (`agent/analyze_query.py`)

When a user submits a query, the **analyze_query agent** runs first to determine if the query contains semantic/thematic components.

**Detected as semantic (suitable for vector search):**
- "heartwarming comedies"
- "dark and suspenseful thrillers"
- "feel-good family movies"
- "philosophical science fiction"
- "romantic coming-of-age stories"

**Detected as structured (SQL-only):**
- "movies released in 2020" (temporal filter)
- "directed by Spielberg" (specific person)
- "top 10 by rating" (ranking/count)
- "PG-13 rated" (certification filter)

### 2. Embedding Encoding

If semantic components are detected:
1. The analyzer extracts the semantic portion (e.g., "heartwarming comedies" from "Show me heartwarming comedies from 2015")
2. Uses **SentenceTransformer** (all-MiniLM-L6-v2, 384-dim) to encode it into a vector
3. Stores the vector and semantic query in state for the SQL agent

### 3. SQL Agent Enhancement (`agent/english_to_sql.py`)

The SQL agent receives:
- Original user query
- Flag: `use_vector_search`
- Semantic query portion
- Vector embeddings (list of 384 floats)

If vector search is indicated, the SQL agent:
- Generates SQL with a placeholder: `{{EMBEDDINGS_VECTOR}}`
- Uses pgvector's `<->` (distance) operator to rank by semantic similarity
- Includes embedding distance in results

Example generated SQL:
```sql
SELECT 
    ms.movie_id, 
    ms.title, 
    ms.overview,
    ms.embedding <-> %s::vector AS semantic_distance
FROM movie_summary ms
WHERE ms.embedding IS NOT NULL
ORDER BY ms.embedding <-> %s::vector
LIMIT 5;
```

### 4. SQL Execution with Embeddings (`agent/execute_sql.py`)

When executing the SQL:
1. Detects the `{{EMBEDDINGS_VECTOR}}` placeholder
2. Replaces it with the actual vector embeddings as a parameter
3. Passes the vector to PostgreSQL's pgvector
4. Returns results ordered by semantic similarity to the query

## Flow Diagram

```
User Query
    ↓
[master_agent] → Routes to SQL
    ↓
[analyze_query] 
    ├─ Detects semantic components
    ├─ Encodes vector embeddings
    └─ Sets vector_search_query & vector_embeddings in state
    ↓
[english_to_sql]
    ├─ Receives vector info
    ├─ Generates SQL with {{EMBEDDINGS_VECTOR}} placeholder
    └─ Returns SQL
    ↓
[execute_sql]
    ├─ Replaces {{EMBEDDINGS_VECTOR}} with actual vector
    ├─ Executes SQL with pgvector distance operator
    └─ Returns ranked results
    ↓
[conversation_llm]
    └─ Summarizes results for user
```

## State Additions

State now includes:
```python
{
    "vector_search_query": Optional[str],      # e.g., "heartwarming comedies"
    "vector_embeddings": Optional[list[float]], # 384-dim vector or None
    "use_vector_search": bool,                  # True if semantic detected
}
```

## Examples

### Example 1: Semantic Query

**User:** "Show me some heartwarming comedies"

**Analyze Phase:**
- Detects: "heartwarming comedies" is semantic
- Encodes to 384-dim vector
- Sets `use_vector_search=True`

**SQL Phase (generated):**
```sql
SELECT movie_id, title, overview, genres, vote_average,
       embedding <-> %s::vector AS semantic_distance
FROM movie_summary
WHERE embedding IS NOT NULL
ORDER BY embedding <-> %s::vector
LIMIT 5;
```

**Execution:**
- Vector is passed as parameter to replace `%s::vector`
- Results ordered by distance to "heartwarming comedies" embedding
- Conversation summarizes: "I found these heartwarming comedies that match your vibe..."

### Example 2: Mixed Query

**User:** "PG-13 rated movies with heist plots from 2015"

**Analyze Phase:**
- Detects: "heist plots" is semantic
- "PG-13 rated" and "from 2015" are structured filters
- Encodes "heist plots" to vector

**SQL Phase:**
```sql
SELECT movie_id, title, overview, genres, cert_us, release_year,
       embedding <-> %s::vector AS semantic_distance
FROM movie_summary
WHERE cert_us = 'PG-13'
  AND release_year = 2015
  AND embedding IS NOT NULL
ORDER BY embedding <-> %s::vector
LIMIT 10;
```

**Result:** Heist movies from 2015 that are PG-13, ranked by semantic similarity

### Example 3: Structured Query (No Vector Search)

**User:** "Movies directed by Christopher Nolan"

**Analyze Phase:**
- Detects: No semantic components
- Sets `use_vector_search=False`

**SQL Phase:**
```sql
SELECT movie_id, title, overview, genres, director_names, vote_average
FROM movie_summary
WHERE 'Christopher Nolan' = ANY(director_names)
LIMIT 10;
```

**Execution:** Standard SQL, no embeddings involved

## Database Requirements

The system assumes:
1. `movie_summary` table has an `embedding` column (vector type, pgvector extension)
2. Embeddings were generated via `database/embed_movies.py` using all-MiniLM-L6-v2
3. PostgreSQL pgvector extension is installed and `<->` operator is available

## Configuration

To enable:
1. Ensure `sentence-transformers` is installed: `pip install sentence-transformers`
2. Run `database/embed_movies.py` to generate embeddings for movies
3. Ensure DB connection env vars are set

No code changes needed — the system detects semantic queries automatically.

## Testing

Run vector search tests:
```bash
python -m pytest -xvs tests/test_groq_client.py::test_analyze_query_detects_semantic_search
python -m pytest -xvs tests/test_groq_client.py::test_analyze_query_no_semantic
```

Test full vector search pipeline:
```bash
python -m pytest -xvs tests/test_groq_client.py
```

## Performance Notes

- **Vector encoding:** ~100ms per query (one-time per user query)
- **Vector search (pgvector):** O(n) with approximate index support for large tables
- **Hybrid queries:** Combine semantic ranking with SQL filters for best results

## Future Enhancements

1. Cache embeddings for common queries
2. Add IVFFlat or HNSW index on embeddings for faster search
3. Combine with fairness filters (gender, country diversity)
4. Multi-modal search (query + reference movie)
5. Learned reranking (combine distance + other factors)

