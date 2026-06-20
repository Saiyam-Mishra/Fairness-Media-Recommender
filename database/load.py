"""
TMDb → PostgreSQL Loader
Reads movies_raw.json and persons_cache.json produced by tmdb_movies.py
and loads everything into the PostgreSQL schema defined in schema.sql.

Requirements:
    pip install psycopg2-binary python-dotenv

Usage:
    # Set connection details as env vars or in a .env file:
    #   DB_HOST=localhost
    #   DB_PORT=5432
    #   DB_NAME=tmdb
    #   DB_USER=postgres
    #   DB_PASSWORD=yourpassword

    python load.py

    # Optional flags:
    python load.py --movies movies_raw.json --persons persons_cache.json
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values, Json

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Database connection ────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(
        host     = os.getenv("DB_HOST",     "localhost"),
        port     = int(os.getenv("DB_PORT", "5432")),
        dbname   = os.getenv("DB_NAME",     "tmdb"),
        user     = os.getenv("DB_USER",     "postgres"),
        password = os.getenv("DB_PASSWORD", ""),
    )

# ── Helpers ────────────────────────────────────────────────────────────────────

def safe_date(s):
    """Parse a YYYY-MM-DD string to a date, returning None on failure."""
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

def safe_int(v):
    try:
        return int(v) if v not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None

def safe_float(v):
    try:
        return float(v) if v not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None

def upsert_genre(cur, name: str, tmdb_id: int = None) -> int:
    cur.execute("""
        INSERT INTO genres (name, tmdb_id)
        VALUES (%s, %s)
        ON CONFLICT (name) DO UPDATE SET tmdb_id = EXCLUDED.tmdb_id
        RETURNING id
    """, (name, tmdb_id))
    return cur.fetchone()[0]

def upsert_keyword(cur, name: str) -> int:
    cur.execute("""
        INSERT INTO keywords (name)
        VALUES (%s)
        ON CONFLICT (name) DO NOTHING
        RETURNING id
    """, (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("SELECT id FROM keywords WHERE name = %s", (name,))
    return cur.fetchone()[0]

def upsert_company(cur, name: str, country: str = None) -> int:
    cur.execute("""
        INSERT INTO production_companies (name, origin_country)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id
    """, (name, country or None))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("SELECT id FROM production_companies WHERE name = %s", (name,))
    return cur.fetchone()[0]

def get_cert(release_dates: dict, iso: str) -> str:
    for entry in release_dates.get("results", []):
        if entry.get("iso_3166_1") == iso:
            for rd in entry.get("release_dates", []):
                if rd.get("certification"):
                    return rd["certification"]
    return None

# ── Person loader ──────────────────────────────────────────────────────────────

def load_person(cur, person_data: dict) -> int:
    """Upsert a person record and return the internal DB id."""
    ext = person_data.get("external_ids") or {}
    aka = person_data.get("also_known_as") or []

    cur.execute("""
        INSERT INTO people (
            tmdb_id, name, also_known_as,
            gender, birthday, deathday,
            place_of_birth, known_for_department,
            biography, popularity, adult,
            imdb_id, wikidata_id, facebook_id, instagram_id, twitter_id,
            profile_path, gender_source
        ) VALUES (
            %(tmdb_id)s, %(name)s, %(aka)s,
            %(gender)s, %(birthday)s, %(deathday)s,
            %(place_of_birth)s, %(known_for_department)s,
            %(biography)s, %(popularity)s, %(adult)s,
            %(imdb_id)s, %(wikidata_id)s, %(facebook_id)s,
            %(instagram_id)s, %(twitter_id)s,
            %(profile_path)s, 'tmdb'
        )
        ON CONFLICT (tmdb_id) DO UPDATE SET
            name                 = EXCLUDED.name,
            also_known_as        = EXCLUDED.also_known_as,
            gender               = EXCLUDED.gender,
            birthday             = EXCLUDED.birthday,
            place_of_birth       = EXCLUDED.place_of_birth,
            known_for_department = EXCLUDED.known_for_department,
            biography            = EXCLUDED.biography,
            popularity           = EXCLUDED.popularity,
            profile_path         = EXCLUDED.profile_path,
            updated_at           = NOW()
        RETURNING id
    """, {
        "tmdb_id":               person_data.get("id"),
        "name":                  person_data.get("name"),
        "aka":                   aka or None,
        "gender":                person_data.get("gender", 0),
        "birthday":              safe_date(person_data.get("birthday")),
        "deathday":              safe_date(person_data.get("deathday")),
        "place_of_birth":        person_data.get("place_of_birth"),
        "known_for_department":  person_data.get("known_for_department"),
        "biography":             person_data.get("biography"),
        "popularity":            safe_float(person_data.get("popularity")),
        "adult":                 bool(person_data.get("adult", False)),
        "imdb_id":               person_data.get("imdb_id") or ext.get("imdb_id"),
        "wikidata_id":           ext.get("wikidata_id"),
        "facebook_id":           ext.get("facebook_id"),
        "instagram_id":          ext.get("instagram_id"),
        "twitter_id":            ext.get("twitter_id"),
        "profile_path":          person_data.get("profile_path"),
    })
    return cur.fetchone()[0]

# ── Movie loader ───────────────────────────────────────────────────────────────

def load_movie(cur, data: dict, persons: dict) -> int:
    """Upsert a full movie record including all relations. Returns internal DB id."""

    tmdb_id = data["id"]
    credits       = data.get("credits", {})
    crew_raw      = credits.get("crew", [])
    cast_raw      = credits.get("cast", [])
    keywords_raw  = data.get("keywords", {}).get("keywords", [])
    release_dates = data.get("release_dates", {})
    videos        = data.get("videos", {}).get("results", [])
    images        = data.get("images", {})
    ext_ids       = data.get("external_ids", {})
    providers     = data.get("watch/providers", {}).get("results", {})
    reviews       = data.get("reviews", {}).get("results", [])
    translations  = data.get("translations", {}).get("translations", [])
    recs          = data.get("recommendations", {}).get("results", [])
    similar       = data.get("similar", {}).get("results", [])
    collection    = data.get("belongs_to_collection") or {}

    # First trailer
    trailer = next(
        (v for v in videos if v.get("type") == "Trailer" and v.get("site") == "YouTube"),
        None
    )

    # Compact watch providers
    providers_compact = {
        country: {
            ptype: [p["provider_name"] for p in plist]
            for ptype, plist in info.items()
            if ptype in ("flatrate", "rent", "buy") and isinstance(plist, list)
        }
        for country, info in providers.items()
    }

    # ── Upsert core movie row ──────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO movies (
            tmdb_id, title, original_title, original_language,
            tagline, overview, homepage, status, adult,
            release_date,
            runtime_min, budget_usd, revenue_usd,
            vote_average, vote_count, popularity,
            collection_id, collection_name,
            origin_countries, production_countries, spoken_languages,
            cert_us, cert_gb, cert_de, cert_fr, cert_au, cert_ca, cert_in,
            imdb_id, wikidata_id, facebook_id, instagram_id, twitter_id,
            poster_url, backdrop_url, trailer_youtube_key,
            poster_count, backdrop_count,
            translation_count, translated_languages,
            review_count,
            watch_providers_json, all_videos_json,
            all_certifications_json, release_dates_json,
            translations_json, reviews_json,
            similar_movie_ids, recommended_movie_ids
        ) VALUES (
            %(tmdb_id)s, %(title)s, %(orig_title)s, %(orig_lang)s,
            %(tagline)s, %(overview)s, %(homepage)s, %(status)s, %(adult)s,
            %(release_date)s,
            %(runtime)s, %(budget)s, %(revenue)s,
            %(vote_avg)s, %(vote_cnt)s, %(popularity)s,
            %(coll_id)s, %(coll_name)s,
            %(origin_countries)s, %(prod_countries)s, %(spoken_langs)s,
            %(cert_us)s, %(cert_gb)s, %(cert_de)s, %(cert_fr)s,
            %(cert_au)s, %(cert_ca)s, %(cert_in)s,
            %(imdb_id)s, %(wikidata_id)s, %(facebook_id)s,
            %(instagram_id)s, %(twitter_id)s,
            %(poster_url)s, %(backdrop_url)s, %(trailer_key)s,
            %(poster_count)s, %(backdrop_count)s,
            %(translation_count)s, %(translated_langs)s,
            %(review_count)s,
            %(watch_providers)s, %(all_videos)s,
            %(all_certs)s, %(release_dates)s,
            %(translations)s, %(reviews)s,
            %(similar_ids)s, %(rec_ids)s
        )
        ON CONFLICT (tmdb_id) DO UPDATE SET
            title               = EXCLUDED.title,
            vote_average        = EXCLUDED.vote_average,
            vote_count          = EXCLUDED.vote_count,
            popularity          = EXCLUDED.popularity,
            watch_providers_json = EXCLUDED.watch_providers_json,
            updated_at          = NOW()
        RETURNING id
    """, {
        "tmdb_id":          tmdb_id,
        "title":            data.get("title"),
        "orig_title":       data.get("original_title"),
        "orig_lang":        data.get("original_language"),
        "tagline":          data.get("tagline"),
        "overview":         (data.get("overview") or "").replace("\n", " "),
        "homepage":         data.get("homepage"),
        "status":           data.get("status"),
        "adult":            bool(data.get("adult", False)),
        "release_date":     safe_date(data.get("release_date")),
        "runtime":          safe_int(data.get("runtime")),
        "budget":           safe_int(data.get("budget")),
        "revenue":          safe_int(data.get("revenue")),
        "vote_avg":         safe_float(data.get("vote_average")),
        "vote_cnt":         safe_int(data.get("vote_count")),
        "popularity":       safe_float(data.get("popularity")),
        "coll_id":          safe_int(collection.get("id")),
        "coll_name":        collection.get("name"),
        "origin_countries": data.get("origin_country") or [],
        "prod_countries":   [c.get("iso_3166_1") for c in data.get("production_countries", [])],
        "spoken_langs":     [l.get("iso_639_1") for l in data.get("spoken_languages", [])],
        "cert_us":          get_cert(release_dates, "US"),
        "cert_gb":          get_cert(release_dates, "GB"),
        "cert_de":          get_cert(release_dates, "DE"),
        "cert_fr":          get_cert(release_dates, "FR"),
        "cert_au":          get_cert(release_dates, "AU"),
        "cert_ca":          get_cert(release_dates, "CA"),
        "cert_in":          get_cert(release_dates, "IN"),
        "imdb_id":          ext_ids.get("imdb_id") or data.get("imdb_id"),
        "wikidata_id":      ext_ids.get("wikidata_id"),
        "facebook_id":      ext_ids.get("facebook_id"),
        "instagram_id":     ext_ids.get("instagram_id"),
        "twitter_id":       ext_ids.get("twitter_id"),
        "poster_url":       ("https://image.tmdb.org/t/p/original" + data["poster_path"]) if data.get("poster_path") else None,
        "backdrop_url":     ("https://image.tmdb.org/t/p/original" + data["backdrop_path"]) if data.get("backdrop_path") else None,
        "trailer_key":      trailer["key"] if trailer else None,
        "poster_count":     len(images.get("posters", [])),
        "backdrop_count":   len(images.get("backdrops", [])),
        "translation_count": len(translations),
        "translated_langs": [t.get("iso_639_1") for t in translations],
        "review_count":     len(reviews),
        "watch_providers":  Json(providers_compact),
        "all_videos":       Json(videos),
        "all_certs":        Json(release_dates),
        "release_dates":    Json(release_dates),
        "translations":     Json(translations),
        "reviews":          Json(reviews),
        "similar_ids":      [r.get("id") for r in similar if r.get("id")],
        "rec_ids":          [r.get("id") for r in recs if r.get("id")],
    })
    movie_db_id = cur.fetchone()[0]

    # ── Genres ─────────────────────────────────────────────────────────────────
    cur.execute("DELETE FROM movie_genres WHERE movie_id = %s", (movie_db_id,))
    for g in data.get("genres", []):
        gid = upsert_genre(cur, g["name"], g.get("id"))
        cur.execute("""
            INSERT INTO movie_genres (movie_id, genre_id)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
        """, (movie_db_id, gid))

    # ── Keywords ───────────────────────────────────────────────────────────────
    cur.execute("DELETE FROM movie_keywords WHERE movie_id = %s", (movie_db_id,))
    for k in keywords_raw:
        kid = upsert_keyword(cur, k["name"])
        cur.execute("""
            INSERT INTO movie_keywords (movie_id, keyword_id)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
        """, (movie_db_id, kid))

    # ── Production companies ───────────────────────────────────────────────────
    cur.execute("DELETE FROM movie_companies WHERE movie_id = %s", (movie_db_id,))
    for c in data.get("production_companies", []):
        cid = upsert_company(cur, c["name"], c.get("origin_country"))
        cur.execute("""
            INSERT INTO movie_companies (movie_id, company_id)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
        """, (movie_db_id, cid))

    # ── Crew ───────────────────────────────────────────────────────────────────
    cur.execute("DELETE FROM movie_crew WHERE movie_id = %s", (movie_db_id,))
    for member in crew_raw:
        pid = _ensure_person(cur, member, persons)
        if pid:
            cur.execute("""
                INSERT INTO movie_crew (movie_id, person_id, job, department, credit_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (movie_id, person_id, job) DO NOTHING
            """, (movie_db_id, pid,
                  member.get("job"), member.get("department"),
                  member.get("credit_id")))

    # ── Cast ───────────────────────────────────────────────────────────────────
    cur.execute("DELETE FROM movie_cast WHERE movie_id = %s", (movie_db_id,))
    for member in cast_raw:
        pid = _ensure_person(cur, member, persons)
        if pid:
            char = (member.get("character") or "")[:200]
            cur.execute("""
                INSERT INTO movie_cast
                    (movie_id, person_id, character_name, cast_order, credit_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (movie_id, person_id, character_name) DO NOTHING
            """, (movie_db_id, pid, char,
                  member.get("order"), member.get("credit_id")))

    return movie_db_id


def _ensure_person(cur, credit_member: dict, persons: dict) -> int | None:
    """
    Resolve a crew/cast member to a DB people.id.
    Uses the persons cache (from /person/{id} calls) if available,
    otherwise inserts a minimal stub from the credit data.
    """
    tmdb_pid = credit_member.get("id")
    if not tmdb_pid:
        return None

    # Full person record available from cache?
    full = persons.get(str(tmdb_pid)) or persons.get(tmdb_pid)
    if full:
        return load_person(cur, full)

    # Minimal stub from credit data
    stub = {
        "id":                   tmdb_pid,
        "name":                 credit_member.get("name", "Unknown"),
        "gender":               credit_member.get("gender", 0),
        "known_for_department": credit_member.get("known_for_department"),
        "popularity":           credit_member.get("popularity"),
        "profile_path":         credit_member.get("profile_path"),
    }
    return load_person(cur, stub)



def populate_summary(cur, movie_db_id: int, data: dict, persons: dict):
    """
    Build and upsert a movie_summary row for the given movie.
    All the data the recommender needs — no joins at query time.
    """
    credits      = data.get("credits", {})
    crew_raw     = credits.get("crew", [])
    cast_raw     = credits.get("cast", [])
    keywords_raw = data.get("keywords", {}).get("keywords", [])
    release_dates = data.get("release_dates", {})
    providers    = data.get("watch/providers", {}).get("results", {})
    collection   = data.get("belongs_to_collection") or {}

    # ── Directors ──────────────────────────────────────────────────────────────
    directors = [p for p in crew_raw if p.get("job") == "Director"]
    dir_names, dir_genders, dir_countries, dir_ids = [], [], [], []
    for d in directors:
        dir_names.append(d.get("name", ""))
        dir_genders.append(d.get("gender", 0))
        dir_ids.append(d.get("id"))
        # Look up birth country from persons cache
        pid = str(d.get("id", ""))
        full = persons.get(pid) or {}
        pob = full.get("place_of_birth") or ""
        # Very rough country extraction — last comma-separated token
        country = pob.split(",")[-1].strip()[:2].upper() if pob else ""
        dir_countries.append(country or None)

    # ── Writers ────────────────────────────────────────────────────────────────
    writers = [p for p in crew_raw if p.get("job") in ("Screenplay", "Writer", "Story", "Author")]
    wri_names   = [w.get("name", "") for w in writers]
    wri_genders = [w.get("gender", 0) for w in writers]

    # ── Top 10 cast ────────────────────────────────────────────────────────────
    top_cast = cast_raw[:10]
    cast_names   = [c.get("name", "") for c in top_cast]
    cast_genders = [c.get("gender", 0) for c in top_cast]
    cast_ids     = [c.get("id") for c in top_cast]

    # ── Companies ──────────────────────────────────────────────────────────────
    companies = data.get("production_companies", [])
    co_names     = [c.get("name", "") for c in companies]
    co_countries = [c.get("origin_country", "") for c in companies]

    # ── Fairness ratios ────────────────────────────────────────────────────────
    def gender_pct(members, g):
        if not members:
            return None
        n = sum(1 for m in members if m.get("gender") == g)
        return round(n / len(members), 4)

    crew_female_pct = gender_pct(crew_raw, 1)
    crew_male_pct   = gender_pct(crew_raw, 2)
    cast_female_pct = gender_pct(cast_raw, 1)
    cast_male_pct   = gender_pct(cast_raw, 2)

    # Crew country diversity — count distinct non-empty birth countries
    crew_countries = set()
    for member in crew_raw:
        pid = str(member.get("id", ""))
        full = persons.get(pid) or {}
        pob = full.get("place_of_birth") or ""
        if pob:
            c = pob.split(",")[-1].strip()[:2].upper()
            if c:
                crew_countries.add(c)
    crew_country_diversity = len(crew_countries) or None

    # ── Geography flags ────────────────────────────────────────────────────────
    orig_lang      = data.get("original_language", "")
    origin_countries = data.get("origin_country") or []
    western_codes  = {"US", "GB", "AU", "CA", "NZ", "IE"}
    is_english     = orig_lang == "en"
    is_western     = bool(set(origin_countries) & western_codes)

    # ── Compact watch providers ────────────────────────────────────────────────
    providers_compact = {
        country: {
            ptype: [p["provider_name"] for p in plist]
            for ptype, plist in info.items()
            if ptype in ("flatrate", "rent", "buy") and isinstance(plist, list)
        }
        for country, info in providers.items()
    }

    # ── Release year ───────────────────────────────────────────────────────────
    rd = data.get("release_date", "") or ""
    release_year = int(rd[:4]) if len(rd) >= 4 and rd[:4].isdigit() else None

    cur.execute("""
        INSERT INTO movie_summary (
            movie_id, tmdb_id,
            title, original_title, release_year, original_language,
            overview, runtime_min, popularity, vote_average, vote_count,
            poster_url, collection_name, adult,
            genres, keywords,
            origin_countries, spoken_languages, is_english, is_western,
            director_names, director_genders, director_birth_countries, director_tmdb_ids,
            top_cast_names, top_cast_genders, top_cast_tmdb_ids,
            writer_names, writer_genders,
            company_names, company_countries,
            crew_female_pct, crew_male_pct, cast_female_pct, cast_male_pct,
            crew_country_diversity,
            cert_us, cert_gb, cert_in,
            watch_providers_json,
            updated_at
        ) VALUES (
            %(movie_id)s, %(tmdb_id)s,
            %(title)s, %(original_title)s, %(release_year)s, %(original_language)s,
            %(overview)s, %(runtime_min)s, %(popularity)s, %(vote_average)s, %(vote_count)s,
            %(poster_url)s, %(collection_name)s, %(adult)s,
            %(genres)s, %(keywords)s,
            %(origin_countries)s, %(spoken_languages)s, %(is_english)s, %(is_western)s,
            %(director_names)s, %(director_genders)s, %(director_birth_countries)s, %(director_tmdb_ids)s,
            %(top_cast_names)s, %(top_cast_genders)s, %(top_cast_tmdb_ids)s,
            %(writer_names)s, %(writer_genders)s,
            %(company_names)s, %(company_countries)s,
            %(crew_female_pct)s, %(crew_male_pct)s, %(cast_female_pct)s, %(cast_male_pct)s,
            %(crew_country_diversity)s,
            %(cert_us)s, %(cert_gb)s, %(cert_in)s,
            %(watch_providers_json)s,
            NOW()
        )
        ON CONFLICT (movie_id) DO UPDATE SET
            genres                  = EXCLUDED.genres,
            keywords                = EXCLUDED.keywords,
            director_names          = EXCLUDED.director_names,
            director_genders        = EXCLUDED.director_genders,
            director_birth_countries = EXCLUDED.director_birth_countries,
            top_cast_names          = EXCLUDED.top_cast_names,
            top_cast_genders        = EXCLUDED.top_cast_genders,
            crew_female_pct         = EXCLUDED.crew_female_pct,
            cast_female_pct         = EXCLUDED.cast_female_pct,
            crew_country_diversity  = EXCLUDED.crew_country_diversity,
            popularity              = EXCLUDED.popularity,
            vote_average            = EXCLUDED.vote_average,
            watch_providers_json    = EXCLUDED.watch_providers_json,
            updated_at              = NOW()
    """, {
        "movie_id":                 movie_db_id,
        "tmdb_id":                  data.get("id"),
        "title":                    data.get("title"),
        "original_title":           data.get("original_title"),
        "release_year":             release_year,
        "original_language":        orig_lang,
        "overview":                 (data.get("overview") or "").replace("\n", " "),
        "runtime_min":              safe_int(data.get("runtime")),
        "popularity":               safe_float(data.get("popularity")),
        "vote_average":             safe_float(data.get("vote_average")),
        "vote_count":               safe_int(data.get("vote_count")),
        "poster_url":               ("https://image.tmdb.org/t/p/original" + data["poster_path"]) if data.get("poster_path") else None,
        "collection_name":          collection.get("name"),
        "adult":                    bool(data.get("adult", False)),
        "genres":                   [g["name"] for g in data.get("genres", [])],
        "keywords":                 [k["name"] for k in keywords_raw],
        "origin_countries":         origin_countries,
        "spoken_languages":         [l.get("iso_639_1") for l in data.get("spoken_languages", [])],
        "is_english":               is_english,
        "is_western":               is_western,
        "director_names":           dir_names,
        "director_genders":         dir_genders,
        "director_birth_countries": dir_countries,
        "director_tmdb_ids":        dir_ids,
        "top_cast_names":           cast_names,
        "top_cast_genders":         cast_genders,
        "top_cast_tmdb_ids":        cast_ids,
        "writer_names":             wri_names,
        "writer_genders":           wri_genders,
        "company_names":            co_names,
        "company_countries":        co_countries,
        "crew_female_pct":          crew_female_pct,
        "crew_male_pct":            crew_male_pct,
        "cast_female_pct":          cast_female_pct,
        "cast_male_pct":            cast_male_pct,
        "crew_country_diversity":   crew_country_diversity,
        "cert_us":                  get_cert(release_dates, "US"),
        "cert_gb":                  get_cert(release_dates, "GB"),
        "cert_in":                  get_cert(release_dates, "IN"),
        "watch_providers_json":     Json(providers_compact),
    })


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Load TMDb JSON into PostgreSQL")
    parser.add_argument("--movies",  default="movies_raw.json",
                        help="Path to movies_raw.json (default: movies_raw.json)")
    parser.add_argument("--persons", default="persons_cache.json",
                        help="Path to persons_cache.json (default: persons_cache.json)")
    args = parser.parse_args()

    # Load input files
    if not os.path.exists(args.movies):
        log.error(f"Movies file not found: {args.movies}")
        sys.exit(1)

    with open(args.movies, encoding="utf-8") as f:
        movies = json.load(f)
    log.info(f"Loaded {len(movies)} movies from {args.movies}")

    persons = {}
    if os.path.exists(args.persons):
        with open(args.persons, encoding="utf-8") as f:
            persons = json.load(f)
        log.info(f"Loaded {len(persons)} person records from {args.persons}")
    else:
        log.warning(f"Persons cache not found ({args.persons}) — will use credit stubs only")

    # Connect
    try:
        conn = get_conn()
    except Exception as e:
        log.error(f"Could not connect to database: {e}")
        log.error("Check DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD env vars.")
        sys.exit(1)

    conn.autocommit = False
    cur = conn.cursor()

    loaded = 0
    failed = 0

    for data in movies:
        title = data.get("title", f"tmdb:{data.get('id')}")
        try:
            movie_db_id = load_movie(cur, data, persons)
            populate_summary(cur, movie_db_id, data, persons)
            conn.commit()
            log.info(f"  ✓  [{movie_db_id}] {title}")
            loaded += 1
        except Exception as e:
            conn.rollback()
            log.error(f"  ✗  {title}: {e}")
            failed += 1

    cur.close()
    conn.close()

    log.info(f"\nDone — {loaded} loaded, {failed} failed.")


if __name__ == "__main__":
    main()