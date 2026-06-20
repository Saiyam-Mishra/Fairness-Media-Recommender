"""
TMDb Movie Fetcher — Maximum Field Extraction
Fetches every available field for the top 1000 movies by popularity, including separate /person/{id}
calls for director/writer/cast profiles (birthplace, biography, filmography).

Outputs:
  - movies.csv         : flat, analysis-ready CSV (70+ columns)
  - movies_raw.json    : complete raw API responses
  - persons_cache.json : cached person profiles (avoids re-fetching)

Requirements:
    pip install requests python-dotenv

Usage:
    1. Go to https://www.themoviedb.org/settings/api
    2. Copy your "API Read Access Token" (long JWT token, NOT the short API key)
    3. export TMDB_ACCESS_TOKEN="your_token_here"
       (or add it to a .env file)
    4. python tmdb_movies.py
"""

import os, csv, json, time, requests
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
ACCESS_TOKEN = os.getenv("TMDB_ACCESS_TOKEN", "YOUR_ACCESS_TOKEN_HERE")
BASE_URL     = "https://api.themoviedb.org/3"
IMAGE_BASE   = "https://image.tmdb.org/t/p/original"
CSV_FILE     = "movies.csv"
JSON_FILE    = "movies_raw.json"
PERSON_CACHE = "persons_cache.json"

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Accept":        "application/json",
}

# All sub-endpoints fetched in a single movie API call
APPEND = ",".join([
    "credits",          # cast + crew with gender codes
    "keywords",         # thematic tags
    "release_dates",    # age certifications + release types per country
    "videos",           # trailers, teasers, featurettes, BTS
    "images",           # all posters, backdrops, logos
    "external_ids",     # imdb_id, wikidata_id, social handles
    "watch/providers",  # streaming availability per country
    "reviews",          # user reviews with author + rating
    "translations",     # title + overview in every language
    "recommendations",  # TMDb recommended movies
    "similar",          # similar movies
    "alternative_titles", # all known alternative titles by country
])

# How many top movies to fetch (TMDb returns 20 per page, so 1000 = 50 pages)
TARGET_COUNT = 1000

# ── CSV columns ────────────────────────────────────────────────────────────────
CSV_FIELDS = [
    # Core identity
    "tmdb_id", "imdb_id", "wikidata_id",
    "title", "original_title", "original_language",
    "tagline", "overview", "homepage", "status", "adult", "video",

    # Release
    "release_date", "release_year",

    # Metrics
    "runtime_min", "budget_usd", "revenue_usd",
    "vote_average", "vote_count", "popularity",

    # Classification
    "genres", "keywords", "collection_name", "collection_id",

    # Geography & language
    "origin_countries", "production_countries", "spoken_languages",

    # Companies
    "production_companies", "production_company_countries",

    # Alternative titles
    "alternative_titles",           # pipe-sep "title (country)" strings

    # Release types per country (JSON: {country: {type_int: date}})
    "release_types_json",

    # Age certifications — major territories
    "cert_us", "cert_gb", "cert_de", "cert_fr",
    "cert_au", "cert_ca", "cert_in", "cert_jp",
    "all_certs_json",               # every cert as JSON {country: cert}

    # ── Directors ──────────────────────────────────────────────────────────────
    "directors", "director_ids", "director_genders",
    "director_popularities",
    # from /person/{id}:
    "director_birthplaces",         # pipe-sep place_of_birth
    "director_birthdays",
    "director_nationalities",       # derived from place_of_birth country part
    "director_biographies",         # pipe-sep (truncated to 300 chars each)
    "director_known_for_depts",

    # ── Writers ────────────────────────────────────────────────────────────────
    "writers", "writer_ids", "writer_genders",
    "writer_popularities",
    "writer_birthplaces",
    "writer_birthdays",

    # ── Producers ──────────────────────────────────────────────────────────────
    "producers", "producer_ids", "producer_genders",

    # ── Other key crew ─────────────────────────────────────────────────────────
    "cinematographers", "editors", "composers",
    "production_designers", "costume_designers",

    # ── Cast ───────────────────────────────────────────────────────────────────
    "cast_size",
    "top5_cast", "top5_cast_ids", "top5_cast_genders",
    "top5_cast_popularities",
    "top5_cast_known_for_depts",
    # from /person/{id} for top 5 cast:
    "top5_cast_birthplaces",
    "top5_cast_birthdays",

    # ── Crew diversity (fairness signals) ──────────────────────────────────────
    "crew_size",
    "crew_female_count",            # gender == 1
    "crew_male_count",              # gender == 2
    "crew_nonbinary_count",         # gender == 3
    "crew_unknown_gender_count",    # gender == 0
    "cast_female_count",
    "cast_male_count",
    "cast_nonbinary_count",
    "cast_unknown_gender_count",

    # ── Videos ─────────────────────────────────────────────────────────────────
    "trailer_youtube_key",          # first YouTube trailer
    "all_videos_json",              # [{type, site, key, language, published_at}]

    # ── Images ─────────────────────────────────────────────────────────────────
    "poster_url", "backdrop_url",
    "poster_count", "backdrop_count", "logo_count",
    "poster_languages",             # pipe-sep ISO language codes of available posters

    # ── Streaming (watch providers) ────────────────────────────────────────────
    "watch_providers_json",         # {country: {flatrate/rent/buy: [names]}}

    # ── Social & external IDs ──────────────────────────────────────────────────
    "facebook_id", "instagram_id", "twitter_id",

    # ── Translations ───────────────────────────────────────────────────────────
    "translation_count", "translated_languages",
    "translated_titles_json",       # {lang_code: translated_title}
    "translated_overviews_json",    # {lang_code: translated_overview}

    # ── Reviews ────────────────────────────────────────────────────────────────
    "review_count", "avg_review_rating",
    "reviews_json",                 # [{author, rating, content_preview, url, created_at}]

    # ── Related content ────────────────────────────────────────────────────────
    "recommended_ids",              # pipe-sep TMDb IDs
    "recommended_titles",           # pipe-sep titles
    "recommended_genres",           # pipe-sep genre lists per recommendation
    "similar_ids",
    "similar_titles",
    "similar_genres",
]
# ───────────────────────────────────────────────────────────────────────────────


# ── API helpers ────────────────────────────────────────────────────────────────

def discover_top_movies(target: int = 1000) -> list[int]:
    """
    Fetch the top N movie IDs from TMDb sorted by popularity descending.
    Uses /discover/movie which returns 20 results per page.
    Saves progress to a local file so you can resume if interrupted.
    """
    PROGRESS_FILE = "discovered_ids.json"

    # Resume from a previous run if available
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            existing = json.load(f)
        if len(existing) >= target:
            print(f"  ↩ Resuming from cache: {len(existing)} IDs already discovered.")
            return existing[:target]
    else:
        existing = []

    ids = list(existing)
    seen = set(ids)
    page = (len(ids) // 20) + 1          # resume at correct page
    total_pages = None

    print(f"  Discovering top {target} movies by popularity...")

    while len(ids) < target:
        r = requests.get(
            f"{BASE_URL}/discover/movie",
            headers=HEADERS,
            params={
                "sort_by":            "popularity.desc",
                "include_adult":      "false",
                "include_video":      "false",
                "page":               page,
                "vote_count.gte":     50,   # filter out obscure entries
            },
            timeout=15,
        )
        if r.status_code != 200:
            print(f"  ⚠ Discover page {page} failed: HTTP {r.status_code}")
            break

        data = r.json()
        if total_pages is None:
            total_pages = data.get("total_pages", 500)

        results = data.get("results", [])
        if not results:
            break

        for movie in results:
            mid = movie.get("id")
            if mid and mid not in seen:
                ids.append(mid)
                seen.add(mid)

        print(f"    page {page}/{min(total_pages, (target//20)+1)} — {len(ids)} IDs collected")

        # Save progress after every page
        with open(PROGRESS_FILE, "w") as f:
            json.dump(ids, f)

        page += 1
        time.sleep(0.25)

        if page > total_pages:
            break

    print(f"  ✓ Discovered {len(ids)} movie IDs.")
    return ids[:target]


def get_movie_details(movie_id: int) -> dict | None:
    """Fetch all available movie fields in one API call."""
    url = f"{BASE_URL}/movie/{movie_id}"
    r = requests.get(url, headers=HEADERS, params={"append_to_response": APPEND}, timeout=15)
    if r.status_code == 200:
        return r.json()
    print(f"  ⚠ Movie {movie_id} failed: HTTP {r.status_code}")
    return None


def get_person_details(person_id: int, cache: dict) -> dict:
    """
    Fetch full person profile from /person/{id}.
    Uses an in-memory cache to avoid duplicate calls across movies.
    """
    if person_id in cache:
        return cache[person_id]
    url = f"{BASE_URL}/person/{person_id}"
    params = {"append_to_response": "combined_credits,external_ids"}
    r = requests.get(url, headers=HEADERS, params=params, timeout=15)
    time.sleep(0.25)  # rate-limit politeness
    if r.status_code == 200:
        data = r.json()
        cache[person_id] = data
        return data
    return {}


# ── Extraction helpers ─────────────────────────────────────────────────────────

def _pipe(values) -> str:
    """Pipe-join a list, skipping None / empty values."""
    return " | ".join(str(v) for v in values if v not in (None, ""))


def _cert(release_dates: dict, iso: str) -> str:
    """Extract age certification for a country (prefers theatrical release type 3)."""
    cert_any = ""
    for entry in release_dates.get("results", []):
        if entry.get("iso_3166_1") == iso:
            for rd in entry.get("release_dates", []):
                c = rd.get("certification", "")
                if c:
                    if rd.get("type") == 3:   # theatrical
                        return c
                    cert_any = cert_any or c
    return cert_any


def _all_certs(release_dates: dict) -> dict:
    """Return {country: first_non-empty_cert} for every country."""
    out = {}
    for entry in release_dates.get("results", []):
        iso = entry.get("iso_3166_1", "")
        for rd in entry.get("release_dates", []):
            c = rd.get("certification", "")
            if c and iso not in out:
                out[iso] = c
    return out


def _release_types(release_dates: dict) -> dict:
    """
    Return {country: {release_type_int: date}} mapping.
    Types: 1=Premiere 2=Limited 3=Theatrical 4=Digital 5=Physical 6=TV
    """
    out = {}
    for entry in release_dates.get("results", []):
        iso = entry.get("iso_3166_1", "")
        out[iso] = {
            rd["type"]: rd.get("release_date", "")[:10]
            for rd in entry.get("release_dates", [])
            if rd.get("type")
        }
    return out


def _person_field(person_data: dict, field: str, truncate: int = 0) -> str:
    val = person_data.get(field) or ""
    if truncate and len(str(val)) > truncate:
        val = str(val)[:truncate] + "…"
    return str(val) if val else ""


def _nationality_from_birthplace(birthplace: str) -> str:
    """Best-effort: extract last comma-separated token as country."""
    if not birthplace:
        return ""
    parts = [p.strip() for p in birthplace.split(",")]
    return parts[-1] if parts else ""


# ── Main extraction ────────────────────────────────────────────────────────────

def extract_row(data: dict, person_cache: dict) -> dict:
    """Flatten the full TMDb API response into one CSV row."""

    # Sub-sections
    credits        = data.get("credits", {})
    crew           = credits.get("crew", [])
    cast           = credits.get("cast", [])
    keywords       = data.get("keywords", {}).get("keywords", [])
    release_dates  = data.get("release_dates", {})
    videos         = data.get("videos", {}).get("results", [])
    images         = data.get("images", {})
    ext_ids        = data.get("external_ids", {})
    providers_raw  = data.get("watch/providers", {}).get("results", {})
    reviews_raw    = data.get("reviews", {}).get("results", [])
    translations   = data.get("translations", {}).get("translations", [])
    recs           = data.get("recommendations", {}).get("results", [])
    similar        = data.get("similar", {}).get("results", [])
    collection     = data.get("belongs_to_collection") or {}
    alt_titles     = data.get("alternative_titles", {}).get("titles", [])

    # ── Crew by role ──────────────────────────────────────────────────────────
    def by_job(*jobs):
        return [p for p in crew if p.get("job") in jobs]

    directors  = by_job("Director")
    writers    = by_job("Screenplay", "Writer", "Story", "Author", "Novel")
    producers  = by_job("Producer", "Executive Producer")
    dps        = by_job("Director of Photography", "Cinematography")
    editors_c  = by_job("Editor")
    composers  = by_job("Original Music Composer", "Music", "Original Score")
    prod_des   = by_job("Production Design", "Production Designer")
    cost_des   = by_job("Costume Design", "Costume Designer")

    # ── Person profiles (directors, writers, top 5 cast) ─────────────────────
    def fetch_profiles(people: list) -> list[dict]:
        return [get_person_details(p["id"], person_cache) for p in people]

    dir_profiles    = fetch_profiles(directors)
    writer_profiles = fetch_profiles(writers)
    top5            = cast[:5]
    top5_profiles   = fetch_profiles(top5)

    # ── Diversity counts ──────────────────────────────────────────────────────
    def gender_counts(people):
        return {
            "female":   sum(1 for p in people if p.get("gender") == 1),
            "male":     sum(1 for p in people if p.get("gender") == 2),
            "nonbinary":sum(1 for p in people if p.get("gender") == 3),
            "unknown":  sum(1 for p in people if p.get("gender") == 0),
        }

    crew_g = gender_counts(crew)
    cast_g = gender_counts(cast)

    # ── Trailer + all videos ──────────────────────────────────────────────────
    trailer = next(
        (v for v in videos if v.get("type") == "Trailer" and v.get("site") == "YouTube"),
        None
    )
    all_videos = [
        {
            "type":         v.get("type"),
            "site":         v.get("site"),
            "key":          v.get("key"),
            "name":         v.get("name"),
            "language":     v.get("iso_639_1"),
            "published_at": v.get("published_at", "")[:10],
        }
        for v in videos
    ]

    # ── Watch providers ───────────────────────────────────────────────────────
    providers_compact = {
        country: {
            ptype: [p["provider_name"] for p in plist]
            for ptype, plist in info.items()
            if ptype in ("flatrate", "rent", "buy") and isinstance(plist, list)
        }
        for country, info in providers_raw.items()
    }

    # ── Translations ──────────────────────────────────────────────────────────
    trans_titles    = {t["iso_639_1"]: t["data"].get("title","")   for t in translations if t.get("data",{}).get("title")}
    trans_overviews = {t["iso_639_1"]: t["data"].get("overview","") for t in translations if t.get("data",{}).get("overview")}

    # ── Reviews ───────────────────────────────────────────────────────────────
    rated = [r["author_details"]["rating"] for r in reviews_raw
             if r.get("author_details", {}).get("rating") is not None]
    avg_review = round(sum(rated) / len(rated), 2) if rated else None
    reviews_summary = [
        {
            "author":          r.get("author"),
            "rating":          r.get("author_details", {}).get("rating"),
            "content_preview": (r.get("content") or "")[:200].replace("\n"," ") + "…",
            "url":             r.get("url"),
            "created_at":      r.get("created_at", "")[:10],
        }
        for r in reviews_raw
    ]

    # ── Poster languages ──────────────────────────────────────────────────────
    poster_langs = list({
        p.get("iso_639_1") for p in images.get("posters", [])
        if p.get("iso_639_1")
    })

    # ── Release ───────────────────────────────────────────────────────────────
    release_date = data.get("release_date", "")
    release_year = release_date[:4] if release_date else None

    return {
        # Core identity
        "tmdb_id":                   data.get("id"),
        "imdb_id":                   ext_ids.get("imdb_id") or data.get("imdb_id"),
        "wikidata_id":               ext_ids.get("wikidata_id"),
        "title":                     data.get("title"),
        "original_title":            data.get("original_title"),
        "original_language":         data.get("original_language"),
        "tagline":                   data.get("tagline"),
        "overview":                  (data.get("overview") or "").replace("\n"," "),
        "homepage":                  data.get("homepage"),
        "status":                    data.get("status"),
        "adult":                     data.get("adult"),
        "video":                     data.get("video"),

        # Release
        "release_date":              release_date,
        "release_year":              release_year,

        # Metrics
        "runtime_min":               data.get("runtime"),
        "budget_usd":                data.get("budget"),
        "revenue_usd":               data.get("revenue"),
        "vote_average":              data.get("vote_average"),
        "vote_count":                data.get("vote_count"),
        "popularity":                data.get("popularity"),

        # Classification
        "genres":                    _pipe(g["name"] for g in data.get("genres", [])),
        "keywords":                  _pipe(k["name"] for k in keywords),
        "collection_name":           collection.get("name"),
        "collection_id":             collection.get("id"),

        # Geography & language
        "origin_countries":          _pipe(
                                         c.get("name", c) if isinstance(c, dict) else c
                                         for c in data.get("origin_country", [])
                                     ),
        "production_countries":      _pipe(c["name"] for c in data.get("production_countries", [])),
        "spoken_languages":          _pipe(l.get("english_name") for l in data.get("spoken_languages", [])),

        # Companies
        "production_companies":      _pipe(c["name"] for c in data.get("production_companies", [])),
        "production_company_countries": _pipe(c.get("origin_country") for c in data.get("production_companies", [])),

        # Alternative titles
        "alternative_titles":        _pipe(f"{t['title']} ({t['iso_3166_1']})" for t in alt_titles),

        # Release types
        "release_types_json":        json.dumps(_release_types(release_dates)),

        # Certifications
        "cert_us":                   _cert(release_dates, "US"),
        "cert_gb":                   _cert(release_dates, "GB"),
        "cert_de":                   _cert(release_dates, "DE"),
        "cert_fr":                   _cert(release_dates, "FR"),
        "cert_au":                   _cert(release_dates, "AU"),
        "cert_ca":                   _cert(release_dates, "CA"),
        "cert_in":                   _cert(release_dates, "IN"),
        "cert_jp":                   _cert(release_dates, "JP"),
        "all_certs_json":            json.dumps(_all_certs(release_dates)),

        # Directors
        "directors":                 _pipe(d["name"] for d in directors),
        "director_ids":              _pipe(d["id"] for d in directors),
        "director_genders":          _pipe(d.get("gender", 0) for d in directors),
        "director_popularities":     _pipe(round(d.get("popularity", 0), 2) for d in directors),
        "director_birthplaces":      _pipe(_person_field(p, "place_of_birth") for p in dir_profiles),
        "director_birthdays":        _pipe(_person_field(p, "birthday") for p in dir_profiles),
        "director_nationalities":    _pipe(_nationality_from_birthplace(_person_field(p, "place_of_birth")) for p in dir_profiles),
        "director_biographies":      _pipe(_person_field(p, "biography", truncate=300) for p in dir_profiles),
        "director_known_for_depts":  _pipe(_person_field(p, "known_for_department") for p in dir_profiles),

        # Writers
        "writers":                   _pipe(w["name"] for w in writers),
        "writer_ids":                _pipe(w["id"] for w in writers),
        "writer_genders":            _pipe(w.get("gender", 0) for w in writers),
        "writer_popularities":       _pipe(round(w.get("popularity", 0), 2) for w in writers),
        "writer_birthplaces":        _pipe(_person_field(p, "place_of_birth") for p in writer_profiles),
        "writer_birthdays":          _pipe(_person_field(p, "birthday") for p in writer_profiles),

        # Producers
        "producers":                 _pipe(p["name"] for p in producers),
        "producer_ids":              _pipe(p["id"] for p in producers),
        "producer_genders":          _pipe(p.get("gender", 0) for p in producers),

        # Other key crew
        "cinematographers":          _pipe(p["name"] for p in dps),
        "editors":                   _pipe(p["name"] for p in editors_c),
        "composers":                 _pipe(p["name"] for p in composers),
        "production_designers":      _pipe(p["name"] for p in prod_des),
        "costume_designers":         _pipe(p["name"] for p in cost_des),

        # Cast
        "cast_size":                 len(cast),
        "top5_cast":                 _pipe(f"{c['name']} as {c.get('character','?')}" for c in top5),
        "top5_cast_ids":             _pipe(c["id"] for c in top5),
        "top5_cast_genders":         _pipe(c.get("gender", 0) for c in top5),
        "top5_cast_popularities":    _pipe(round(c.get("popularity", 0), 2) for c in top5),
        "top5_cast_known_for_depts": _pipe(c.get("known_for_department","") for c in top5),
        "top5_cast_birthplaces":     _pipe(_person_field(p, "place_of_birth") for p in top5_profiles),
        "top5_cast_birthdays":       _pipe(_person_field(p, "birthday") for p in top5_profiles),

        # Diversity signals
        "crew_size":                 len(crew),
        "crew_female_count":         crew_g["female"],
        "crew_male_count":           crew_g["male"],
        "crew_nonbinary_count":      crew_g["nonbinary"],
        "crew_unknown_gender_count": crew_g["unknown"],
        "cast_female_count":         cast_g["female"],
        "cast_male_count":           cast_g["male"],
        "cast_nonbinary_count":      cast_g["nonbinary"],
        "cast_unknown_gender_count": cast_g["unknown"],

        # Videos
        "trailer_youtube_key":       trailer["key"] if trailer else None,
        "all_videos_json":           json.dumps(all_videos),

        # Images
        "poster_url":                IMAGE_BASE + data["poster_path"] if data.get("poster_path") else None,
        "backdrop_url":              IMAGE_BASE + data["backdrop_path"] if data.get("backdrop_path") else None,
        "poster_count":              len(images.get("posters", [])),
        "backdrop_count":            len(images.get("backdrops", [])),
        "logo_count":                len(images.get("logos", [])),
        "poster_languages":          _pipe(poster_langs),

        # Streaming
        "watch_providers_json":      json.dumps(providers_compact, ensure_ascii=False),

        # Social
        "facebook_id":               ext_ids.get("facebook_id"),
        "instagram_id":              ext_ids.get("instagram_id"),
        "twitter_id":                ext_ids.get("twitter_id"),

        # Translations
        "translation_count":         len(translations),
        "translated_languages":      _pipe(t.get("iso_639_1") for t in translations),
        "translated_titles_json":    json.dumps(trans_titles, ensure_ascii=False),
        "translated_overviews_json": json.dumps(trans_overviews, ensure_ascii=False),

        # Reviews
        "review_count":              len(reviews_raw),
        "avg_review_rating":         avg_review,
        "reviews_json":              json.dumps(reviews_summary, ensure_ascii=False),

        # Related
        "recommended_ids":           _pipe(m.get("id") for m in recs[:10]),
        "recommended_titles":        _pipe(m.get("title") for m in recs[:10]),
        "recommended_genres":        _pipe(
                                         " & ".join(g["name"] for g in m.get("genre_ids", []))
                                         if isinstance(m.get("genre_ids", [{}])[0], dict)
                                         else str(m.get("genre_ids", []))
                                         for m in recs[:10]
                                     ),
        "similar_ids":               _pipe(m.get("id") for m in similar[:10]),
        "similar_titles":            _pipe(m.get("title") for m in similar[:10]),
        "similar_genres":            _pipe(str(m.get("genre_ids", [])) for m in similar[:10]),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if ACCESS_TOKEN == "YOUR_ACCESS_TOKEN_HERE":
        print("❌ Please set your TMDb Read Access Token before running.")
        print("   Get one free at: https://www.themoviedb.org/settings/api")
        print("   Use the 'API Read Access Token', not the short API Key.")
        return

    person_cache: dict = {}
    rows, raw_data = [], []

    # Discover top movies dynamically
    movie_ids = discover_top_movies(TARGET_COUNT)
    total = len(movie_ids)
    print(f"Fetching full details for {total} movies...\n")

    for i, movie_id in enumerate(movie_ids, 1):
        print(f"  [{i}/{total}] Movie {movie_id}...")
        data = get_movie_details(movie_id)
        if not data:
            continue

        title = data.get("title", "?")
        year  = (data.get("release_date") or "")[:4] or "N/A"
        print(f"    ✓ {title} ({year}) — fetching person profiles...")

        row = extract_row(data, person_cache)
        rows.append(row)
        raw_data.append(data)

        n_persons = len([d for d in directors_in(data) + writers_in(data) + cast_in(data)])
        print(f"      persons fetched/cached: {len(person_cache)} total")
        time.sleep(0.3)

    # ── Write CSV ─────────────────────────────────────────────────────────────
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n✅ CSV  → '{CSV_FILE}'  ({len(rows)} movies, {len(CSV_FIELDS)} columns)")

    # ── Write raw movie JSON ──────────────────────────────────────────────────
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)
    print(f"✅ Raw JSON  → '{JSON_FILE}'")

    # ── Write person cache ────────────────────────────────────────────────────
    with open(PERSON_CACHE, "w", encoding="utf-8") as f:
        json.dump(person_cache, f, ensure_ascii=False, indent=2)
    print(f"✅ Person cache  → '{PERSON_CACHE}'  ({len(person_cache)} profiles)")


def directors_in(data):
    return [p for p in data.get("credits",{}).get("crew",[]) if p.get("job")=="Director"]

def writers_in(data):
    return [p for p in data.get("credits",{}).get("crew",[])
            if p.get("job") in ("Screenplay","Writer","Story","Author","Novel")]

def cast_in(data):
    return data.get("credits",{}).get("cast",[])[:5]


if __name__ == "__main__":
    main()