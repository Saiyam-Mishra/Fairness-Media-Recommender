-- =============================================================================
-- Refresh movie_summary from normalized tables
-- Run this any time in Supabase SQL editor to rebuild the summary table.
-- Useful if you loaded data before the summary table existed, or want to
-- recompute all fairness ratios after a Wikidata enrichment run.
-- =============================================================================

TRUNCATE TABLE movie_summary;

INSERT INTO movie_summary (
    movie_id,
    tmdb_id,
    title,
    original_title,
    release_year,
    original_language,
    overview,
    runtime_min,
    popularity,
    vote_average,
    vote_count,
    poster_url,
    collection_name,
    adult,
    genres,
    keywords,
    origin_countries,
    spoken_languages,
    is_english,
    is_western,
    director_names,
    director_genders,
    director_birth_countries,
    director_tmdb_ids,
    top_cast_names,
    top_cast_genders,
    top_cast_tmdb_ids,
    writer_names,
    writer_genders,
    company_names,
    company_countries,
    crew_female_pct,
    crew_male_pct,
    cast_female_pct,
    cast_male_pct,
    crew_country_diversity,
    cert_us,
    cert_gb,
    cert_in,
    watch_providers_json,
    updated_at
)
SELECT
    m.id                                                AS movie_id,
    m.tmdb_id,
    m.title,
    m.original_title,
    m.release_year,
    m.original_language,
    m.overview,
    m.runtime_min,
    m.popularity,
    m.vote_average,
    m.vote_count,
    m.poster_url,
    m.collection_name,
    m.adult,

    -- Genres as array
    COALESCE(ARRAY(
        SELECT g.name FROM movie_genres mg
        JOIN genres g ON g.id = mg.genre_id
        WHERE mg.movie_id = m.id
        ORDER BY g.name
    ), '{}'),

    -- Keywords as array
    COALESCE(ARRAY(
        SELECT k.name FROM movie_keywords mk
        JOIN keywords k ON k.id = mk.keyword_id
        WHERE mk.movie_id = m.id
        ORDER BY k.name
    ), '{}'),

    m.origin_countries,
    m.spoken_languages,
    m.original_language = 'en',
    (m.origin_countries && ARRAY['US','GB','AU','CA','NZ','IE']),

    -- Directors
    COALESCE(ARRAY(
        SELECT p.name FROM movie_crew mc JOIN people p ON p.id = mc.person_id
        WHERE mc.movie_id = m.id AND mc.job = 'Director'
    ), '{}'),
    COALESCE(ARRAY(
        SELECT p.gender FROM movie_crew mc JOIN people p ON p.id = mc.person_id
        WHERE mc.movie_id = m.id AND mc.job = 'Director'
    ), '{}'),
    COALESCE(ARRAY(
        SELECT COALESCE(p.birth_country, '') FROM movie_crew mc JOIN people p ON p.id = mc.person_id
        WHERE mc.movie_id = m.id AND mc.job = 'Director'
    ), '{}'),
    COALESCE(ARRAY(
        SELECT p.tmdb_id FROM movie_crew mc JOIN people p ON p.id = mc.person_id
        WHERE mc.movie_id = m.id AND mc.job = 'Director'
    ), '{}'),

    -- Top 10 cast by billing order
    COALESCE(ARRAY(
        SELECT p.name FROM movie_cast mc JOIN people p ON p.id = mc.person_id
        WHERE mc.movie_id = m.id ORDER BY mc.cast_order LIMIT 10
    ), '{}'),
    COALESCE(ARRAY(
        SELECT p.gender FROM movie_cast mc JOIN people p ON p.id = mc.person_id
        WHERE mc.movie_id = m.id ORDER BY mc.cast_order LIMIT 10
    ), '{}'),
    COALESCE(ARRAY(
        SELECT p.tmdb_id FROM movie_cast mc JOIN people p ON p.id = mc.person_id
        WHERE mc.movie_id = m.id ORDER BY mc.cast_order LIMIT 10
    ), '{}'),

    -- Writers
    COALESCE(ARRAY(
        SELECT p.name FROM movie_crew mc JOIN people p ON p.id = mc.person_id
        WHERE mc.movie_id = m.id AND mc.job IN ('Screenplay','Writer','Story','Author')
    ), '{}'),
    COALESCE(ARRAY(
        SELECT p.gender FROM movie_crew mc JOIN people p ON p.id = mc.person_id
        WHERE mc.movie_id = m.id AND mc.job IN ('Screenplay','Writer','Story','Author')
    ), '{}'),

    -- Companies
    COALESCE(ARRAY(
        SELECT pc.name FROM movie_companies mco
        JOIN production_companies pc ON pc.id = mco.company_id
        WHERE mco.movie_id = m.id
    ), '{}'),
    COALESCE(ARRAY(
        SELECT COALESCE(pc.origin_country,'') FROM movie_companies mco
        JOIN production_companies pc ON pc.id = mco.company_id
        WHERE mco.movie_id = m.id
    ), '{}'),

    -- Crew fairness ratios
    ROUND(
        (SELECT COUNT(*) FROM movie_crew mc JOIN people p ON p.id = mc.person_id
         WHERE mc.movie_id = m.id AND p.gender = 1)::NUMERIC
        / NULLIF((SELECT COUNT(*) FROM movie_crew WHERE movie_id = m.id), 0), 4
    ),
    ROUND(
        (SELECT COUNT(*) FROM movie_crew mc JOIN people p ON p.id = mc.person_id
         WHERE mc.movie_id = m.id AND p.gender = 2)::NUMERIC
        / NULLIF((SELECT COUNT(*) FROM movie_crew WHERE movie_id = m.id), 0), 4
    ),

    -- Cast fairness ratios
    ROUND(
        (SELECT COUNT(*) FROM movie_cast mc JOIN people p ON p.id = mc.person_id
         WHERE mc.movie_id = m.id AND p.gender = 1)::NUMERIC
        / NULLIF((SELECT COUNT(*) FROM movie_cast WHERE movie_id = m.id), 0), 4
    ),
    ROUND(
        (SELECT COUNT(*) FROM movie_cast mc JOIN people p ON p.id = mc.person_id
         WHERE mc.movie_id = m.id AND p.gender = 2)::NUMERIC
        / NULLIF((SELECT COUNT(*) FROM movie_cast WHERE movie_id = m.id), 0), 4
    ),

    -- Crew country diversity
    (SELECT COUNT(DISTINCT p.birth_country) FROM movie_crew mc
     JOIN people p ON p.id = mc.person_id
     WHERE mc.movie_id = m.id AND p.birth_country IS NOT NULL),

    m.cert_us,
    m.cert_gb,
    m.cert_in,
    m.watch_providers_json,
    NOW()

FROM movies m;

-- Verify
SELECT
    COUNT(*)                            AS total_rows,
    COUNT(*) FILTER (WHERE genres  != '{}') AS with_genres,
    COUNT(*) FILTER (WHERE director_names != '{}') AS with_directors,
    ROUND(AVG(crew_female_pct) * 100, 1) AS avg_crew_female_pct
FROM movie_summary;
