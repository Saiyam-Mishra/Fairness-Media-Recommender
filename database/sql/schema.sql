-- =============================================================================
-- TMDb PostgreSQL Schema
-- Fairness-based media recommender
-- =============================================================================
-- Run this first to set up the database:
--   psql -U postgres -d tmdb -f schema.sql
-- =============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS unaccent;   -- accent-insensitive text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- fuzzy string matching

-- =============================================================================
-- LOOKUP TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS genres (
    id          SERIAL PRIMARY KEY,
    tmdb_id     INTEGER UNIQUE,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS keywords (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS production_companies (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    origin_country  CHAR(2)
);

-- =============================================================================
-- PEOPLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS people (
    id                      SERIAL PRIMARY KEY,
    tmdb_id                 INTEGER UNIQUE NOT NULL,

    -- Identity
    name                    TEXT NOT NULL,
    also_known_as           TEXT[],

    -- Demographics (fairness-critical)
    gender                  SMALLINT,           -- 0=unknown 1=female 2=male 3=non-binary
    birthday                DATE,
    deathday                DATE,
    place_of_birth          TEXT,
    birth_country           CHAR(2),            -- ISO code, enriched separately
    birth_city              TEXT,

    -- Career
    known_for_department    TEXT,
    biography               TEXT,
    popularity              NUMERIC(10,4),
    adult                   BOOLEAN DEFAULT FALSE,

    -- External IDs
    imdb_id                 TEXT,
    wikidata_id             TEXT,
    facebook_id             TEXT,
    instagram_id            TEXT,
    twitter_id              TEXT,

    -- Enrichment tracking: which source gave us this demographic data
    gender_source           TEXT,               -- 'tmdb','wikidata','genderize','inferred'
    nationality_source      TEXT,               -- 'tmdb','wikidata','openlibrary'

    -- Media
    profile_path            TEXT,

    fetched_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_people_gender        ON people (gender);
CREATE INDEX IF NOT EXISTS idx_people_birth_country ON people (birth_country);
CREATE INDEX IF NOT EXISTS idx_people_known_for     ON people (known_for_department);
CREATE INDEX IF NOT EXISTS idx_people_tmdb_id       ON people (tmdb_id);

-- =============================================================================
-- MOVIES
-- =============================================================================

CREATE TABLE IF NOT EXISTS movies (
    id                          SERIAL PRIMARY KEY,
    tmdb_id                     INTEGER UNIQUE NOT NULL,

    -- Identity
    title                       TEXT NOT NULL,
    original_title              TEXT,
    original_language           CHAR(10),
    tagline                     TEXT,
    overview                    TEXT,
    homepage                    TEXT,
    status                      TEXT,
    adult                       BOOLEAN DEFAULT FALSE,

    -- Release
    release_date                DATE,
    release_year                SMALLINT GENERATED ALWAYS AS (EXTRACT(YEAR FROM release_date)::SMALLINT) STORED,

    -- Metrics
    runtime_min                 SMALLINT,
    budget_usd                  BIGINT,
    revenue_usd                 BIGINT,
    vote_average                NUMERIC(4,2),
    vote_count                  INTEGER,
    popularity                  NUMERIC(10,4),

    -- Collection / franchise
    collection_id               INTEGER,
    collection_name             TEXT,

    -- Geography
    origin_countries            TEXT[],
    production_countries        TEXT[],
    spoken_languages            TEXT[],

    -- Age certifications
    cert_us                     TEXT,
    cert_gb                     TEXT,
    cert_de                     TEXT,
    cert_fr                     TEXT,
    cert_au                     TEXT,
    cert_ca                     TEXT,
    cert_in                     TEXT,

    -- External IDs
    imdb_id                     TEXT,
    wikidata_id                 TEXT,
    facebook_id                 TEXT,
    instagram_id                TEXT,
    twitter_id                  TEXT,

    -- Media
    poster_url                  TEXT,
    backdrop_url                TEXT,
    trailer_youtube_key         TEXT,
    poster_count                SMALLINT,
    backdrop_count              SMALLINT,

    -- Translations
    translation_count           SMALLINT,
    translated_languages        TEXT[],

    -- Reviews
    review_count                SMALLINT,
    avg_review_rating           NUMERIC(4,2),

    -- Pre-computed diversity counts (updated via trigger)
    crew_size                   SMALLINT,
    crew_female_count           SMALLINT,
    crew_male_count             SMALLINT,
    crew_nonbinary_count        SMALLINT,
    crew_unknown_gender_count   SMALLINT,
    cast_size                   SMALLINT,
    cast_female_count           SMALLINT,
    cast_male_count             SMALLINT,
    cast_unknown_gender_count   SMALLINT,

    -- JSONB for deeply nested data
    watch_providers_json        JSONB,
    all_certifications_json     JSONB,
    all_videos_json             JSONB,
    release_dates_json          JSONB,
    translations_json           JSONB,
    reviews_json                JSONB,
    similar_movie_ids           INTEGER[],
    recommended_movie_ids       INTEGER[],

    fetched_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_movies_tmdb_id           ON movies (tmdb_id);
CREATE INDEX IF NOT EXISTS idx_movies_release_year      ON movies (release_year);
CREATE INDEX IF NOT EXISTS idx_movies_original_language ON movies (original_language);
CREATE INDEX IF NOT EXISTS idx_movies_vote_average      ON movies (vote_average);
CREATE INDEX IF NOT EXISTS idx_movies_popularity        ON movies (popularity DESC);
CREATE INDEX IF NOT EXISTS idx_movies_origin_countries  ON movies USING GIN (origin_countries);
CREATE INDEX IF NOT EXISTS idx_movies_spoken_languages  ON movies USING GIN (spoken_languages);
CREATE INDEX IF NOT EXISTS idx_movies_watch_providers   ON movies USING GIN (watch_providers_json);
CREATE INDEX IF NOT EXISTS idx_movies_fts               ON movies
    USING GIN (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(overview,'')));

-- =============================================================================
-- MOVIE <-> CREW
-- =============================================================================

CREATE TABLE IF NOT EXISTS movie_crew (
    id          SERIAL PRIMARY KEY,
    movie_id    INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    person_id   INTEGER NOT NULL REFERENCES people (id) ON DELETE CASCADE,
    job         TEXT NOT NULL,
    department  TEXT,
    credit_id   TEXT,
    UNIQUE (movie_id, person_id, job)
);

CREATE INDEX IF NOT EXISTS idx_movie_crew_movie  ON movie_crew (movie_id);
CREATE INDEX IF NOT EXISTS idx_movie_crew_person ON movie_crew (person_id);
CREATE INDEX IF NOT EXISTS idx_movie_crew_job    ON movie_crew (job);

-- =============================================================================
-- MOVIE <-> CAST
-- =============================================================================

CREATE TABLE IF NOT EXISTS movie_cast (
    id              SERIAL PRIMARY KEY,
    movie_id        INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    person_id       INTEGER NOT NULL REFERENCES people (id) ON DELETE CASCADE,
    character_name  TEXT,
    cast_order      SMALLINT,
    credit_id       TEXT,
    UNIQUE (movie_id, person_id, character_name)
);

CREATE INDEX IF NOT EXISTS idx_movie_cast_movie  ON movie_cast (movie_id);
CREATE INDEX IF NOT EXISTS idx_movie_cast_person ON movie_cast (person_id);
CREATE INDEX IF NOT EXISTS idx_movie_cast_order  ON movie_cast (cast_order);

-- =============================================================================
-- MOVIE <-> GENRES
-- =============================================================================

CREATE TABLE IF NOT EXISTS movie_genres (
    movie_id    INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    genre_id    INTEGER NOT NULL REFERENCES genres (id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, genre_id)
);

CREATE INDEX IF NOT EXISTS idx_movie_genres_genre ON movie_genres (genre_id);

-- =============================================================================
-- MOVIE <-> KEYWORDS
-- =============================================================================

CREATE TABLE IF NOT EXISTS movie_keywords (
    movie_id    INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    keyword_id  INTEGER NOT NULL REFERENCES keywords (id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, keyword_id)
);

CREATE INDEX IF NOT EXISTS idx_movie_keywords_keyword ON movie_keywords (keyword_id);

-- =============================================================================
-- MOVIE <-> COMPANIES
-- =============================================================================

CREATE TABLE IF NOT EXISTS movie_companies (
    movie_id    INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    company_id  INTEGER NOT NULL REFERENCES production_companies (id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, company_id)
);

-- =============================================================================
-- RECOMMENDATIONS & SIMILAR (as proper join tables for reverse lookups)
-- =============================================================================

CREATE TABLE IF NOT EXISTS movie_similar (
    movie_id    INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    similar_id  INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, similar_id)
);

CREATE TABLE IF NOT EXISTS movie_recommendations (
    movie_id            INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    recommended_id      INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, recommended_id)
);

-- =============================================================================
-- FAIRNESS AUDIT LOG
-- =============================================================================

CREATE TABLE IF NOT EXISTS fairness_audit (
    id                          SERIAL PRIMARY KEY,
    session_id                  TEXT,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    input_movie_ids             INTEGER[],
    raw_recommendation_ids      INTEGER[],
    bias_type                   TEXT,
    bias_detail                 JSONB,
    correction_applied          TEXT,
    adjusted_recommendation_ids INTEGER[],
    explanation                 TEXT
);


-- =============================================================================
-- MOVIE SUMMARY  (denormalized, join-free, for recommender queries)
-- Populated by load.py after each movie is inserted.
-- All the fields the recommender needs in a single row — no joins required.
-- =============================================================================

CREATE TABLE IF NOT EXISTS movie_summary (
    movie_id                INTEGER PRIMARY KEY REFERENCES movies (id) ON DELETE CASCADE,
    tmdb_id                 INTEGER NOT NULL,

    -- Core fields
    title                   TEXT NOT NULL,
    original_title          TEXT,
    release_year            SMALLINT,
    original_language       TEXT,
    overview                TEXT,
    runtime_min             SMALLINT,
    popularity              NUMERIC(10,4),
    vote_average            NUMERIC(4,2),
    vote_count              INTEGER,
    poster_url              TEXT,
    collection_name         TEXT,
    adult                   BOOLEAN,

    -- Classification arrays — filter with = ANY() or @>
    genres                  TEXT[],
    keywords                TEXT[],

    -- Geography
    origin_countries        TEXT[],
    spoken_languages        TEXT[],
    is_english              BOOLEAN,
    is_western              BOOLEAN,        -- US/GB/AU/CA/NZ/IE

    -- Directors (denormalized)
    director_names          TEXT[],
    director_genders        SMALLINT[],
    director_birth_countries TEXT[],
    director_tmdb_ids       INTEGER[],

    -- Top 10 cast by billing order
    top_cast_names          TEXT[],
    top_cast_genders        SMALLINT[],
    top_cast_tmdb_ids       INTEGER[],

    -- Writers
    writer_names            TEXT[],
    writer_genders          SMALLINT[],

    -- Production companies
    company_names           TEXT[],
    company_countries       TEXT[],

    -- Pre-computed fairness ratios (0.0 to 1.0)
    crew_female_pct         NUMERIC(5,4),
    crew_male_pct           NUMERIC(5,4),
    cast_female_pct         NUMERIC(5,4),
    cast_male_pct           NUMERIC(5,4),
    crew_country_diversity  SMALLINT,       -- distinct birth countries in crew

    -- Certifications
    cert_us                 TEXT,
    cert_gb                 TEXT,
    cert_in                 TEXT,

    -- Streaming
    watch_providers_json    JSONB,

    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ms_genres          ON movie_summary USING GIN (genres);
CREATE INDEX IF NOT EXISTS idx_ms_keywords        ON movie_summary USING GIN (keywords);
CREATE INDEX IF NOT EXISTS idx_ms_origin          ON movie_summary USING GIN (origin_countries);
CREATE INDEX IF NOT EXISTS idx_ms_languages       ON movie_summary USING GIN (spoken_languages);
CREATE INDEX IF NOT EXISTS idx_ms_director_gender ON movie_summary USING GIN (director_genders);
CREATE INDEX IF NOT EXISTS idx_ms_cast_gender     ON movie_summary USING GIN (top_cast_genders);
CREATE INDEX IF NOT EXISTS idx_ms_popularity      ON movie_summary (popularity DESC);
CREATE INDEX IF NOT EXISTS idx_ms_vote_average    ON movie_summary (vote_average DESC);
CREATE INDEX IF NOT EXISTS idx_ms_release_year    ON movie_summary (release_year);
CREATE INDEX IF NOT EXISTS idx_ms_is_english      ON movie_summary (is_english);
CREATE INDEX IF NOT EXISTS idx_ms_is_western      ON movie_summary (is_western);
CREATE INDEX IF NOT EXISTS idx_ms_providers       ON movie_summary USING GIN (watch_providers_json);

-- =============================================================================
-- VIEWS
-- =============================================================================

CREATE OR REPLACE VIEW v_movie_director_gender AS
SELECT
    m.id                AS movie_id,
    m.title,
    m.release_year,
    m.original_language,
    p.id                AS director_id,
    p.name              AS director_name,
    p.gender            AS director_gender,
    p.birth_country     AS director_birth_country,
    p.place_of_birth    AS director_place_of_birth,
    p.gender_source
FROM movies m
JOIN movie_crew mc ON mc.movie_id = m.id
JOIN people p      ON p.id = mc.person_id
WHERE mc.job = 'Director';

CREATE OR REPLACE VIEW v_gender_summary AS
SELECT
    mc.job,
    p.gender,
    CASE p.gender
        WHEN 0 THEN 'Unknown'
        WHEN 1 THEN 'Female'
        WHEN 2 THEN 'Male'
        WHEN 3 THEN 'Non-binary'
        ELSE 'Other'
    END                 AS gender_label,
    COUNT(*)            AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY mc.job), 2) AS pct
FROM movie_crew mc
JOIN people p ON p.id = mc.person_id
GROUP BY mc.job, p.gender
ORDER BY mc.job, p.gender;

CREATE OR REPLACE VIEW v_language_distribution AS
SELECT
    original_language,
    COUNT(*)                    AS movie_count,
    ROUND(AVG(vote_average), 2) AS avg_rating,
    ROUND(AVG(popularity), 2)   AS avg_popularity
FROM movies
GROUP BY original_language
ORDER BY movie_count DESC;

CREATE OR REPLACE VIEW v_origin_country_distribution AS
SELECT
    UNNEST(origin_countries)    AS country,
    COUNT(*)                    AS movie_count
FROM movies
GROUP BY country
ORDER BY movie_count DESC;

-- =============================================================================
-- TRIGGER: auto-update crew diversity counts on movies
-- =============================================================================

CREATE OR REPLACE FUNCTION update_crew_diversity_counts()
RETURNS TRIGGER AS $$
DECLARE
    mid INTEGER := COALESCE(NEW.movie_id, OLD.movie_id);
BEGIN
    UPDATE movies SET
        crew_female_count = (
            SELECT COUNT(*) FROM movie_crew mc
            JOIN people p ON p.id = mc.person_id
            WHERE mc.movie_id = mid AND p.gender = 1
        ),
        crew_male_count = (
            SELECT COUNT(*) FROM movie_crew mc
            JOIN people p ON p.id = mc.person_id
            WHERE mc.movie_id = mid AND p.gender = 2
        ),
        crew_nonbinary_count = (
            SELECT COUNT(*) FROM movie_crew mc
            JOIN people p ON p.id = mc.person_id
            WHERE mc.movie_id = mid AND p.gender = 3
        ),
        crew_unknown_gender_count = (
            SELECT COUNT(*) FROM movie_crew mc
            JOIN people p ON p.id = mc.person_id
            WHERE mc.movie_id = mid AND p.gender = 0
        ),
        crew_size = (
            SELECT COUNT(*) FROM movie_crew
            WHERE movie_id = mid
        ),
        updated_at = NOW()
    WHERE id = mid;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_crew_diversity
AFTER INSERT OR UPDATE OR DELETE ON movie_crew
FOR EACH ROW EXECUTE FUNCTION update_crew_diversity_counts();
