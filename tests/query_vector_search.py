"""Quick test: encode a user query to an embedding and run a vector nearest-
neighbor SQL against the `movie_summary` table.

Usage:
    python tests/query_vector_search.py

The script will prompt for a short text query, encode it with the same
SentenceTransformer model used for embeddings, and run a PostgreSQL query
ordering by embedding distance (using the <-> operator). It prints the top
matches with distances and short overviews.

Requirements (same as `embed_movies.py`):
    pip install sentence-transformers psycopg2-binary python-dotenv

Set DB connection environment variables in your shell or a .env file:
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

from __future__ import annotations

import os
import textwrap
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer

load_dotenv()

MODEL_NAME = "all-MiniLM-L6-v2"  # same model used by embed_movies.py
DEFAULT_TOP = 10


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def main():
    print("Load embedding model...")
    model = SentenceTransformer(MODEL_NAME)

    q = input("Enter a short query to search (e.g. 'action movies with Tom Cruise'): ").strip()
    if not q:
        print("No query provided, exiting.")
        return

    print("Encoding query...")
    vec = model.encode(q, normalize_embeddings=True).tolist()

    try:
        conn = get_conn()
    except Exception as exc:
        print(f"Could not connect to DB: {exc}")
        return

    cur = conn.cursor(cursor_factory=RealDictCursor)

    top = DEFAULT_TOP
    sql = (
        "SELECT movie_id, title, overview, "
        "embedding <-> %s::vector AS distance "
        "FROM movie_summary "
        "WHERE embedding IS NOT NULL "
        "ORDER BY embedding <-> %s::vector "
        "LIMIT %s;"
    )

    try:
        cur.execute(sql, (vec, vec, top))
        rows = cur.fetchall()
        if not rows:
            print("No matches returned. Make sure movie_summary.embedding contains vectors.")
            return

        print(f"\nTop {len(rows)} matches for: '{q}'\n")
        for i, r in enumerate(rows, start=1):
            title = r.get("title") or "(no title)"
            movie_id = r.get("movie_id")
            dist = r.get("distance")
            overview = r.get("overview") or ""
            overview_short = textwrap.shorten(overview, width=220, placeholder="...")
            print(f"{i}. [{movie_id}] {title}  (distance={dist:.6f})")
            if overview_short:
                print(f"    {overview_short}\n")

    except Exception as exc:
        print(f"Query failed: {exc}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

