import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
)
cur = conn.cursor(cursor_factory=RealDictCursor)

# ── 1. Top 5 movies by popularity ─────────────────────────────────────────────
print("\n── Top 5 movies by popularity")
cur.execute("""
    SELECT title, release_year, vote_average, popularity, genres
    FROM movie_summary
    ORDER BY popularity DESC
    LIMIT 5;
""")
for row in cur.fetchall():
    print(" ", dict(row))

# ── 2. Action movies with a female director ────────────────────────────────────
print("\n── Action movies with a female director")
cur.execute("""
    SELECT title, director_names, director_genders, vote_average
    FROM movie_summary
    WHERE 'Action' = ANY(genres)
      AND 1 = ANY(director_genders)
    ORDER BY vote_average DESC
    LIMIT 5;
""")
for row in cur.fetchall():
    print(" ", dict(row))

# ── 3. Non-English movies with high ratings ───────────────────────────────────
print("\n── Non-English, vote_average > 7.5")
cur.execute("""
    SELECT title, original_language, origin_countries, vote_average, director_names
    FROM movie_summary
    WHERE is_english = FALSE
      AND vote_average > 7.5
    ORDER BY vote_average DESC
    LIMIT 5;
""")
for row in cur.fetchall():
    print(" ", dict(row))

# ── 4. Fairness overview ──────────────────────────────────────────────────────
print("\n── Fairness overview across catalogue")
cur.execute("""
    SELECT
        COUNT(*)                                        AS total_movies,
        ROUND(AVG(crew_female_pct) * 100, 1)           AS avg_crew_female_pct,
        ROUND(AVG(cast_female_pct) * 100, 1)           AS avg_cast_female_pct,
        COUNT(*) FILTER (WHERE is_english = FALSE)     AS non_english_movies,
        COUNT(*) FILTER (WHERE 1 = ANY(director_genders)) AS female_directed
    FROM movie_summary;
""")
for row in cur.fetchall():
    print(" ", dict(row))


print("\n── ")
cur.execute("""
    SELECT *
    FROM movie_summary
    LIMIT 5;
""")
for row in cur.fetchall():
    print(" ", dict(row))

cur.close()
conn.close()