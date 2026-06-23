"""
Generates vector embeddings for movie_summary rows and stores them in Postgres.

Embedding input = title + tagline + overview + collection_name + genres + keywords
Deliberately EXCLUDES director/cast/company/country — those stay SQL-only so
fairness filtering is never fuzzy. See project README for the reasoning.

Requirements:
    pip install sentence-transformers psycopg2-binary python-dotenv

Usage:
    python embed_movies.py                # embed all rows missing an embedding
    python embed_movies.py --force         # re-embed every row, even if already done
    python embed_movies.py --limit 50      # only process the first 50 (for testing)
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"   # 384-dim — must match the column in add_embeddings.sql
EXPECTED_DIM = 384


def get_conn():
    return psycopg2.connect(
        host     = os.getenv("DB_HOST"),
        port     = int(os.getenv("DB_PORT", "5432")),
        dbname   = os.getenv("DB_NAME", "postgres"),
        user     = os.getenv("DB_USER", "postgres"),
        password = os.getenv("DB_PASSWORD"),
    )


def build_embedding_text(row: dict) -> str:
    """
    Deterministically build the text fed into the embedding model.
    Same row + same fields -> always the same string. This determinism is what
    makes it safe to detect "did the source data change since last embed?".

    Order matters for reproducibility — do not reorder without re-embedding
    everything, since changing order changes the resulting text/embedding.
    """
    title          = (row.get("title") or "").strip()
    tagline        = (row.get("tagline") or "").strip()
    overview       = (row.get("overview") or "").strip()
    collection     = (row.get("collection_name") or "").strip()
    genres         = row.get("genres") or []
    keywords       = row.get("keywords") or []

    parts = []
    if title:
        parts.append(title)
    if tagline:
        parts.append(tagline)
    if overview:
        parts.append(overview)
    if collection:
        parts.append(f"Part of the {collection}.")
    if genres:
        parts.append(f"Genres: {', '.join(sorted(genres))}.")
    if keywords:
        parts.append(f"Keywords: {', '.join(sorted(keywords))}.")

    return " ".join(parts)


def validate_embedding(vec, expected_dim: int = EXPECTED_DIM) -> None:
    """Hard fail rather than silently store a malformed vector."""
    if vec is None:
        raise ValueError("Embedding is None")
    if len(vec) != expected_dim:
        raise ValueError(f"Embedding has {len(vec)} dims, expected {expected_dim}")
    if any(v is None for v in vec):
        raise ValueError("Embedding contains None values")


def fetch_rows(cur, force: bool, limit: int | None):
    """
    Pull only the columns that feed the embedding, plus identifiers.
    Selecting exactly these columns (not SELECT *) is itself an accuracy
    safeguard — it guarantees build_embedding_text() can never accidentally
    see a column it isn't supposed to use.
    """
    where = "" if force else "WHERE embedding IS NULL"
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    cur.execute(f"""
        SELECT movie_id, tmdb_id, title, tagline, overview,
               collection_name, genres, keywords,
               embedding_source_text
        FROM movie_summary
        {where}
        ORDER BY movie_id
        {limit_clause};
    """)
    return cur.fetchall()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Re-embed every row, even if embedding already exists")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process the first N rows (testing)")
    args = parser.parse_args()

    log.info(f"Loading model '{MODEL_NAME}'...")
    model = SentenceTransformer(MODEL_NAME)

    # Confirm the model's actual output size matches what the DB column expects,
    # BEFORE writing anything — catches a model/schema mismatch immediately.
    probe_dim = len(model.encode("probe").tolist())
    if probe_dim != EXPECTED_DIM:
        log.error(
            f"Model output dim ({probe_dim}) != DB column dim ({EXPECTED_DIM}). "
            f"Update EXPECTED_DIM or the vector(...) column size to match, then retry."
        )
        sys.exit(1)

    try:
        conn = get_conn()
    except Exception as e:
        log.error(f"Could not connect to database: {e}")
        sys.exit(1)

    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    rows = fetch_rows(cur, args.force, args.limit)
    log.info(f"{len(rows)} rows to embed (force={args.force})")

    updated, skipped, failed = 0, 0, 0

    for row in rows:
        movie_id = row["movie_id"]
        title    = row.get("title") or f"tmdb:{row.get('tmdb_id')}"

        try:
            source_text = build_embedding_text(row)

            if not source_text.strip():
                log.warning(f"  ⚠ [{movie_id}] {title}: no text fields populated, skipping")
                skipped += 1
                continue

            # Skip re-embedding if the source text hasn't actually changed
            # (only relevant in --force mode, where we re-check every row)
            if args.force and row.get("embedding_source_text") == source_text:
                skipped += 1
                continue

            vec = model.encode(source_text, normalize_embeddings=True).tolist()
            validate_embedding(vec)

            cur.execute("""
                UPDATE movie_summary
                SET embedding = %s::vector,
                    embedding_source_text = %s,
                    embedding_updated_at = %s
                WHERE movie_id = %s
            """, (vec, source_text, datetime.now(timezone.utc), movie_id))

            # Per-row commit: one bad row never rolls back previously
            # successful embeddings, and you can safely re-run after any crash.
            conn.commit()

            log.info(f"  ✓ [{movie_id}] {title}")
            updated += 1

        except Exception as e:
            conn.rollback()
            log.error(f"  ✗ [{movie_id}] {title}: {e}")
            failed += 1

    # ── Post-run verification ────────────────────────────────────────────────
    cur.execute("""
        SELECT COUNT(*) AS total,
               COUNT(embedding) AS with_embedding,
               COUNT(*) FILTER (WHERE embedding IS NOT NULL
                                 AND array_length(embedding::float[], 1) != %s) AS wrong_dim
        FROM movie_summary;
    """, (EXPECTED_DIM,))
    check = cur.fetchone()

    cur.close()
    conn.close()

    log.info(f"\nDone — {updated} embedded, {skipped} skipped, {failed} failed.")
    log.info(
        f"DB check: {check['with_embedding']}/{check['total']} rows have an embedding, "
        f"{check['wrong_dim']} have wrong dimensionality."
    )
    if check["wrong_dim"] > 0:
        log.error("⚠ Some rows have malformed embeddings — investigate before using vector search.")


if __name__ == "__main__":
    main()