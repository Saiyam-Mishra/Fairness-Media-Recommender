# Fairness-Aware Movie Recommender

A conversational movie recommender that lets users question the fairness of
their recommendations mid-dialogue and receive metric-grounded explanations
alongside improved results.

Most recommenders optimise purely for relevance and popularity, silently
producing lists that systematically under-represent films by female directors,
non-Western productions, non-English films, or non-dominant genres — without
the user ever being told. This project treats fairness as a property users can
raise during conversation, not a backend afterthought.

---

## What it does

A user asks for recommendations in plain English. The system retrieves results
using a hybrid SQL + semantic vector search pipeline. If the user then questions
the diversity of those results — *"why are all these directed by men?"* or
*"why is there no Asian cinema here?"* — a dedicated fairness agent:

1. Identifies which attribute is being questioned (director gender, origin
   country, language, genre, etc.)
2. Computes four deterministic fairness metrics over the current ranked list:
   **SPD**, **EOD**, **OAED**, and **Exposure@K**
3. Fetches additional under-represented films and injects them at
   high-visibility positions if bias exceeds configured thresholds
4. Returns a plain-language explanation grounded in the exact before/after
   metric values — the language model never computes the numbers, it only
   verbalises them

All metric computation is deterministic Python, completely independent of the
language model, directly addressing the risk of hallucinated statistics.

---

## Architecture

```
User message
      ↓
LLM router (llama-3.3-70b-versatile)
      ↓                    ↓
   MASTER               FAIRNESS
      ↓                    ↓
Master agent          Fairness agent
   ↓     ↓               ↓
  SQL  Conversation   LLM classifies attribute
pipeline   agent      compute_fairness_metrics (pure Python)
  ↓                   SPD · EOD · OAED · Exp@K
analyze_query         re-rank + supplement SQL
english_to_sql              ↓
execute_sql           PostgreSQL · Supabase
      ↓                     ↓
PostgreSQL · Supabase  Streamlit UI
(movie_summary + pgvector)
```

All LLM calls use `llama-3.3-70b-versatile` via Groq at temperature 0.0.
Semantic search uses `all-MiniLM-L6-v2` (384-dim) with pgvector cosine
distance over an HNSW index. Movie embeddings are computed from thematic
fields only (title, tagline, overview, genres, keywords) — deliberately
excluding demographic attributes so vector similarity reflects narrative
content, not demographic characteristics.

---

## Fairness attributes supported

| Dimension | Attribute | Encoding |
|---|---|---|
| Gender | `director_genders` | integer array (0=unknown, 1=female, 2=male, 3=non-binary) |
| Gender | `cast_genders` | integer array, same codes |
| Geography | `origin_countries` | array of ISO country codes |
| Geography | `company_countries` | array of ISO country codes |
| Language | `spoken_languages` | array of ISO language codes |
| Language | `is_english` | boolean |
| Language | `is_western` | boolean (US, GB, AU, CA, NZ, IE) |
| Genre | `genres` | string array |

---

## Project layout

```
fairness_recommender/
├── ingestion/
│   └── fetch_movies.py        # pulls top N movies from TMDb → data/
│
├── database/
│   ├── sql/
│   │   ├── schema.sql           # CREATE TABLE statements (run once)
│   │   ├── add_embeddings.sql   # adds vector column + HNSW index
│   │   ├── refresh_summary.sql  # rebuilds movie_summary from normalised tables
│   │   └── example_queries.sql  # sample fairness queries
│   ├── load.py                  # loads data/ JSON into Postgres
│   ├── embed_movies.py          # computes and stores embeddings
│   ├── extract_schema.py        # dumps schema for LLM context
│   └── test_connection.py       # sanity-check queries
│
├── agent/
│   ├── graph.py                 # LangGraph pipeline definition
│   ├── llm_router.py            # LLM-based MASTER / FAIRNESS router
│   ├── master_agent.py          # SQL vs conversation classifier
│   ├── analyze_query.py         # structured vs semantic query classifier
│   ├── english_to_sql.py        # NL → SQL
│   ├── execute_sql.py           # SQL execution + normalisation
│   ├── conversation_llm.py      # result summarisation
│   ├── fairness_agent.py        # fairness assessment + re-ranking
│   ├── fairness_metrics.py      # SPD, EOD, OAED, Exposure@K (pure Python)
│   ├── state.py                 # shared AgentState TypedDict
│   └── app.py                   # Streamlit web interface
│
├── tests/
│   └── run_tests.py             # automated multi-turn test runner → test_results.docx
│
├── data/                        # generated at runtime (gitignored)
├── .env.example
└── requirements.txt
```

---

## Getting started

### Prerequisites

- Python 3.11+
- A [TMDb API Read Access Token](https://www.themoviedb.org/settings/api)
- A PostgreSQL database — [Supabase](https://supabase.com) free tier works
- A [Groq API key](https://console.groq.com) (free tier)

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in TMDB_ACCESS_TOKEN, GROQ_API_KEY, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
```

### Pipeline

```bash
# 1. Fetch movies from TMDb (resumes automatically if interrupted)
cd ingestion && python fetch_movies.py

# 2. Set up the database schema
#    Paste database/sql/schema.sql into your Supabase SQL editor and run it

# 3. Load data into Postgres
cd ../database && python load.py

# 4. Rebuild the movie_summary table
#    Paste database/sql/refresh_summary.sql into Supabase SQL editor and run it

# 5. Add vector embeddings
#    Paste database/sql/add_embeddings.sql into Supabase SQL editor and run it
cd ../database && python embed_movies.py

# 6. Verify everything loaded correctly
cd ../database && python test_connection.py
```

### Running the app

```bash
# Streamlit web interface
cd agent && streamlit run app.py

# CLI (terminal chat)
cd agent && python main.py
```

### Running automated tests

```bash
python tests/run_tests.py
# produces test_results.docx in the project root
```

---

## Key findings

Across five evaluation scenarios covering director gender, origin country, and
genre diversity:

- The standard retrieval pipeline consistently returns lists with zero
  protected-group representation (SPD = −1.0) when optimising purely for
  popularity and relevance
- Improving representation count (SPD) does not guarantee fairness on other
  metrics — in the genre scenario, SPD improved while EOD worsened, which
  would have been invisible with single-metric reporting
- Catalogue-level scarcity of under-represented titles imposes a ceiling on
  what any re-ranking layer can achieve, independent of algorithmic design
- The fixed 40% injection target produces consistent SPD improvements but
  can over-correct at small result set sizes (k < 5)

---

## A note on the data

The dataset is the top 1,000 films by TMDb popularity — not a balanced sample
of world cinema. Director and cast gender codes are community-maintained on
TMDb and include a meaningful proportion of unknowns (code 0), which are
excluded from metric calculations. Country and nationality data is more
complete for Western filmmakers than non-Western ones. These gaps are treated
as first-class properties of the system, not bugs to hide — they set a natural
boundary on how precise fairness assessments can be, and are themselves a form
of bias worth surfacing.
