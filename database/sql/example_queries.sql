-- =============================================================================
-- Example Fairness Queries
-- Run these against your tmdb database after loading data.
-- =============================================================================


-- ── 1. Director gender breakdown across the whole catalogue ──────────────────
SELECT
    gender_label,
    count,
    pct || '%' AS percentage
FROM v_gender_summary
WHERE job = 'Director'
ORDER BY count DESC;


-- ── 2. Female director % by decade ──────────────────────────────────────────
SELECT
    (release_year / 10) * 10            AS decade,
    COUNT(*)                            AS total_movies,
    SUM(CASE WHEN p.gender = 1 THEN 1 ELSE 0 END) AS female_directed,
    ROUND(
        SUM(CASE WHEN p.gender = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2
    )                                   AS female_pct
FROM movies m
JOIN movie_crew mc ON mc.movie_id = m.id AND mc.job = 'Director'
JOIN people p      ON p.id = mc.person_id
WHERE m.release_year IS NOT NULL
GROUP BY decade
ORDER BY decade;


-- ── 3. Language diversity — what % of movies are non-English ────────────────
SELECT
    CASE WHEN original_language = 'en' THEN 'English' ELSE 'Non-English' END AS lang_group,
    COUNT(*)            AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM movies
GROUP BY lang_group
ORDER BY count DESC;


-- ── 4. Origin country distribution (top 20) ──────────────────────────────────
SELECT
    country,
    movie_count,
    ROUND(movie_count * 100.0 / SUM(movie_count) OVER (), 2) AS pct
FROM v_origin_country_distribution
LIMIT 20;


-- ── 5. Directors by birth country (top 20) ───────────────────────────────────
SELECT
    COALESCE(p.birth_country, 'Unknown') AS birth_country,
    COUNT(DISTINCT m.id)                  AS movies_directed
FROM movies m
JOIN movie_crew mc ON mc.movie_id = m.id AND mc.job = 'Director'
JOIN people p      ON p.id = mc.person_id
GROUP BY birth_country
ORDER BY movies_directed DESC
LIMIT 20;


-- ── 6. Genre monoculture — is any single genre dominating? ───────────────────
SELECT
    g.name              AS genre,
    COUNT(*)            AS movie_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM movie_genres mg
JOIN genres g ON g.id = mg.genre_id
GROUP BY g.name
ORDER BY movie_count DESC;


-- ── 7. Studio dominance — top 10 production companies by output ──────────────
SELECT
    pc.name             AS company,
    pc.origin_country,
    COUNT(*)            AS movies_produced
FROM movie_companies mc2
JOIN production_companies pc ON pc.id = mc2.company_id
GROUP BY pc.name, pc.origin_country
ORDER BY movies_produced DESC
LIMIT 10;


-- ── 8. Popularity bias — do female-directed films get lower popularity? ───────
SELECT
    CASE p.gender
        WHEN 1 THEN 'Female'
        WHEN 2 THEN 'Male'
        WHEN 3 THEN 'Non-binary'
        ELSE 'Unknown'
    END                         AS director_gender,
    COUNT(*)                    AS movie_count,
    ROUND(AVG(m.popularity), 2) AS avg_popularity,
    ROUND(AVG(m.vote_average), 2) AS avg_rating,
    ROUND(AVG(m.vote_count), 0)   AS avg_vote_count
FROM movies m
JOIN movie_crew mc ON mc.movie_id = m.id AND mc.job = 'Director'
JOIN people p      ON p.id = mc.person_id
GROUP BY director_gender
ORDER BY avg_popularity DESC;


-- ── 9. Recommendation bias — do recommendations stay in same language? ────────
-- (Requires movies to exist for similar_movie_ids to resolve)
SELECT
    m.original_language         AS source_language,
    r.original_language         AS recommended_language,
    COUNT(*)                    AS count
FROM movies m
JOIN movies r ON r.tmdb_id = ANY(m.recommended_movie_ids)
GROUP BY source_language, recommended_language
ORDER BY source_language, count DESC;


-- ── 10. Cast gender balance by genre ─────────────────────────────────────────
SELECT
    g.name                      AS genre,
    COUNT(*)                    AS total_cast_credits,
    SUM(CASE WHEN p.gender = 1 THEN 1 ELSE 0 END) AS female_count,
    SUM(CASE WHEN p.gender = 2 THEN 1 ELSE 0 END) AS male_count,
    ROUND(SUM(CASE WHEN p.gender = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS female_pct
FROM movie_cast mc2
JOIN people p      ON p.id = mc2.person_id
JOIN movie_genres mg ON mg.movie_id = mc2.movie_id
JOIN genres g      ON g.id = mg.genre_id
GROUP BY g.name
ORDER BY female_pct ASC;


-- ── 11. Streaming availability by country (via JSONB) ────────────────────────
-- Which movies are available for streaming in India?
SELECT
    title,
    watch_providers_json -> 'IN' -> 'flatrate' AS india_streaming
FROM movies
WHERE watch_providers_json -> 'IN' -> 'flatrate' IS NOT NULL
ORDER BY popularity DESC;


-- ── 12. Age certification breakdown ──────────────────────────────────────────
SELECT
    cert_us,
    COUNT(*)            AS count,
    ROUND(AVG(vote_average), 2) AS avg_rating
FROM movies
WHERE cert_us IS NOT NULL AND cert_us != ''
GROUP BY cert_us
ORDER BY count DESC;


-- ── 13. Missing demographic data audit ───────────────────────────────────────
-- How much of your data still needs enrichment?
SELECT
    'Directors with unknown gender'     AS metric,
    COUNT(*)                            AS count
FROM movie_crew mc
JOIN people p ON p.id = mc.person_id
WHERE mc.job = 'Director' AND p.gender = 0

UNION ALL

SELECT
    'Directors with unknown birth country',
    COUNT(*)
FROM movie_crew mc
JOIN people p ON p.id = mc.person_id
WHERE mc.job = 'Director' AND p.birth_country IS NULL

UNION ALL

SELECT
    'Movies with unknown origin country',
    COUNT(*)
FROM movies
WHERE origin_countries = '{}' OR origin_countries IS NULL

UNION ALL

SELECT
    'People needing Wikidata enrichment',
    COUNT(*)
FROM people
WHERE gender = 0 AND gender_source = 'tmdb';
