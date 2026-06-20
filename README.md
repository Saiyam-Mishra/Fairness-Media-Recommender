# Fairness-Based Media Recommender

A movie recommender built around one core idea: recommendation systems quietly
encode bias — by director gender, by language, by country of origin, by studio
dominance — and most of the time the user never finds out why they're being
shown what they're shown.

This project pulls movie data from TMDb, stores it in PostgreSQL with explicit
demographic and fairness signals attached to every title (director gender,
cast gender balance, country of origin, etc.), and exposes that data through
a natural-language agent so a user can ask not just "recommend me a movie"
but "why is everything you're showing me directed by men?" and get a real,
queryable answer.

## Why this exists

Most recommender demos optimize purely for engagement or similarity. This one
treats fairness as a first-class, queryable dimension of the data rather than
an afterthought bolted on at the end. Every movie record carries:

- Director, writer, and cast gender breakdowns
- Country of origin and production company nationality
- Crew diversity ratios (precomputed, not just raw counts)
- Streaming availability and certification data per country

The goal is that a user — or an LLM agent acting on their behalf — can
interrogate the catalogue, not just consume whatever it's handed.

## How it works

```
TMDb API  →  ingestion/  →  database/  →  agent/
 (source)     (fetch)        (store)       (query in plain English)
```

**Ingestion** pulls the top N movies from TMDb, including full credits,
keywords, certifications, and watch providers, then resolves every credited
person's demographic details (gender, birthplace, nationality) via separate
person lookups.

**Database** loads everything into PostgreSQL using a two-layer schema:
normalized tables (`movies`, `people`, `movie_crew`, `movie_cast`, etc.) act
as the source of truth, while a single flattened `movie_summary` table is
rebuilt from them and used for all actual recommendation queries — so
filtering by genre, director gender, or origin country never requires a
five-table JOIN at query time.

**Agent** is a LangGraph-based router that takes a natural-language question,
turns it into SQL against `movie_summary`, runs it, and returns the answer —
so questions like *"show me action movies directed by women"* or *"how
diverse is my recommendation list by country"* are handled directly rather
than needing the user to write SQL themselves.

## Project layout

```
fairness_recommender/
├── ingestion/        TMDb → JSON
├── database/         JSON → Postgres, schema, fairness queries
├── agent/             Natural language → SQL → answer
├── data/              Generated files (gitignored)
├── .env.example
└── requirements.txt
```

See inline comments in each script for specifics — `ingestion/fetch_movies.py`,
`database/load.py`, and `agent/graph.py` are the three entry points worth
reading first if you want to understand the pipeline end to end.

## Getting started

```bash
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` with your TMDb access token and PostgreSQL/Supabase
credentials, then run the pipeline in order:

```bash
cd ingestion  && python fetch_movies.py     # fetch movies + people from TMDb
cd ../database && python load.py             # load into Postgres
#   run database/sql/refresh_summary.sql in your DB's SQL editor
cd ../database && python test_connection.py  # sanity check
cd ../database && python extract_schema.py   # generate schema reference for the agent
cd ../agent    && python main.py             # start asking questions
```

## A note on the data

Director/cast gender comes from TMDb directly where available, which skews
toward Western, well-documented filmographies. Country and nationality
fields are similarly incomplete for lesser-known crew. The fairness signals
in this project are a starting point for auditing bias, not a ground-truth
measurement — gaps in the data are themselves a form of bias worth surfacing,
not hiding.