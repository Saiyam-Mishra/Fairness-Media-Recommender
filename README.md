# Fairness-Based Media Recommender

## Structure

```
fairness_recommender/
├── ingestion/
│   └── fetch_movies.py        # Pulls top N movies from TMDb -> movies_raw.json
│
├── database/
│   ├── sql/
│   │   ├── schema.sql           # CREATE TABLE statements (run once)
│   │   ├── refresh_summary.sql  # Rebuilds movie_summary from normalized tables
│   │   └── example_queries.sql  # Sample fairness queries
│   ├── load.py                  # Loads movies_raw.json + persons_cache.json into Postgres
│   ├── extract_schema.py        # Dumps schema in a compact form for LLM context
│   └── test_connection.py       # Quick sanity-check queries against movie_summary
│
├── agent/
│   └── system_prompt.py         # System prompt for an LLM SQL agent (uses schema + examples)
│
├── data/                        # Generated at runtime — not committed
│   ├── movies_raw.json
│   ├── persons_cache.json
│   ├── discovered_ids.json
│   └── schema_for_llm.txt
│
├── .env.example                 # Copy to .env and fill in real values
└── requirements.txt
```

## Pipeline order

```
1. cd ingestion  && python fetch_movies.py        # -> data/movies_raw.json, persons_cache.json
2. cd database   && python load.py                # loads into Postgres/Supabase
3. Run database/sql/refresh_summary.sql in Supabase SQL editor
4. cd database   && python test_connection.py      # verify
5. cd database   && python extract_schema.py       # -> data/schema_for_llm.txt, for the agent
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in TMDB_ACCESS_TOKEN and DB_* values
```
