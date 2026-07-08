import os
import re

from groq import Groq
from dotenv import load_dotenv


from state import AgentState

load_dotenv()

# Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

schema = '''
fairness_audit (0 rows)
  id: integer [PK]
  session_id: text nullable
  created_at: timestamptz nullable
  input_movie_ids: ARRAY nullable
  raw_recommendation_ids: ARRAY nullable
  bias_type: text nullable
  bias_detail: jsonb nullable
  correction_applied: text nullable
  adjusted_recommendation_ids: ARRAY nullable
  explanation: text nullable

genres (19 rows)
  id: integer [PK]
  tmdb_id: integer nullable
  name: text

keywords (6098 rows)
  id: integer [PK]
  name: text

movie_cast (50175 rows)
  id: integer [PK]
  movie_id: integer -> movies.id
  person_id: integer -> people.id
  character_name: text nullable
  cast_order: smallint nullable
  credit_id: text nullable

movie_companies (3206 rows)
  movie_id: integer [PK] -> movies.id
  company_id: integer [PK] -> production_companies.id

movie_crew (151037 rows)
  id: integer [PK]
  movie_id: integer -> movies.id
  person_id: integer -> people.id
  job: text
  department: text nullable
  credit_id: text nullable

movie_genres (2792 rows)
  movie_id: integer [PK] -> movies.id
  genre_id: integer [PK] -> genres.id

movie_keywords (16664 rows)
  movie_id: integer [PK] -> movies.id
  keyword_id: integer [PK] -> keywords.id

movie_recommendations (0 rows)
  movie_id: integer [PK] -> movies.id
  recommended_id: integer [PK] -> movies.id

movie_similar (0 rows)
  movie_id: integer [PK] -> movies.id
  similar_id: integer [PK] -> movies.id

movie_summary (1000 rows)
  movie_id: integer [PK] -> movies.id
  tmdb_id: integer
  title: text
  original_title: text nullable
  release_year: smallint nullable
  original_language: text nullable
  overview: text nullable
  runtime_min: smallint nullable
  popularity: numeric nullable
  vote_average: numeric nullable
  vote_count: integer nullable
  poster_url: text nullable
  collection_name: text nullable
  adult: boolean nullable
  genres: ARRAY nullable
  keywords: ARRAY nullable
  origin_countries: ARRAY nullable
  spoken_languages: ARRAY nullable
  is_english: boolean nullable
  is_western: boolean nullable
  director_names: ARRAY nullable
  director_genders: ARRAY nullable
  director_birth_countries: ARRAY nullable
  director_tmdb_ids: ARRAY nullable
  top_cast_names: ARRAY nullable
  top_cast_genders: ARRAY nullable
  top_cast_tmdb_ids: ARRAY nullable
  writer_names: ARRAY nullable
  writer_genders: ARRAY nullable
  company_names: ARRAY nullable
  company_countries: ARRAY nullable
  crew_female_pct: numeric nullable
  crew_male_pct: numeric nullable
  cast_female_pct: numeric nullable
  cast_male_pct: numeric nullable
  crew_country_diversity: smallint nullable
  cert_us: text nullable
  cert_gb: text nullable
  cert_in: text nullable
  watch_providers_json: jsonb nullable
  updated_at: timestamptz nullable
  embedding: USER-DEFINED nullable

movies (1000 rows)
  id: integer [PK]
  tmdb_id: integer
  title: text
  original_title: text nullable
  original_language: character nullable
  tagline: text nullable
  overview: text nullable
  homepage: text nullable
  status: text nullable
  adult: boolean nullable
  release_date: date nullable
  release_year: smallint nullable
  runtime_min: smallint nullable
  budget_usd: bigint nullable
  revenue_usd: bigint nullable
  vote_average: numeric nullable
  vote_count: integer nullable
  popularity: numeric nullable
  collection_id: integer nullable
  collection_name: text nullable
  origin_countries: ARRAY nullable
  production_countries: ARRAY nullable
  spoken_languages: ARRAY nullable
  translation_count: smallint nullable
  translated_languages: ARRAY nullable
  review_count: smallint nullable
  avg_review_rating: numeric nullable
  crew_size: smallint nullable
  crew_female_count: smallint nullable
  crew_male_count: smallint nullable
  crew_nonbinary_count: smallint nullable
  crew_unknown_gender_count: smallint nullable
  cast_size: smallint nullable
  cast_female_count: smallint nullable
  cast_male_count: smallint nullable
  cast_unknown_gender_count: smallint nullable
  watch_providers_json: jsonb nullable
  release_dates_json: jsonb nullable
  translations_json: jsonb nullable
  reviews_json: jsonb nullable
  similar_movie_ids: ARRAY nullable
  recommended_movie_ids: ARRAY nullable

people (112274 rows)
  id: integer [PK]
  tmdb_id: integer
  name: text
  also_known_as: ARRAY nullable
  gender: smallint nullable
  birthday: date nullable
  deathday: date nullable
  place_of_birth: text nullable
  birth_country: character nullable
  birth_city: text nullable
  known_for_department: text nullable
  biography: text nullable
  popularity: numeric nullable
  adult: boolean nullable


production_companies (3586 rows)
  id: integer [PK]
  name: text
  origin_country: character nullable
'''

_SYSTEM_PROMPT = f"""You are an expert SQL assistant for a movie database.
Given a database schema and a natural-language question, produce ONLY a complete and valid SQL query.
The query should be efficient and use the appropriate tables and columns to answer the question.
To avoid unnecessary complexity, only use JOINs when needed to get the correct answer. When possible, 
use the movie_summary table to get the results.
If the user does not mention a number, only give the top 5 results. If the user mentions a number, use that as the limit for the number of results.
Include appropriate columns in the SELECT statement. Always include the movie id, movie title, genres, release year, ratings, and overview in the results.
The user query that you receive maybe contain a command to include embeddings. If this is the case, you should make use of the 'embeddings' column in the 'movie_summary' table to find the most relevant results.
If the query tells you to use embeddings, include the following SQL syntax in your SQL query:
        <regular SQL query>...
        WHERE embedding IS NOT NULL
        ORDER BY embedding <-> EMBEDDINGS_VECTOR;
        
Ensure that you compare embedding with 'EMBEDDINGS_VECTOR', which is a
placeholder and will be replaced later. The rest of your query must be valid and complete.


Rules:
- Output ONLY the SQL query — no explanation, no markdown fences.
- Use standard ANSI SQL unless the schema implies a specific dialect.
- Always qualify column names with their table name when there is any ambiguity.
- Use meaningful aliases.
- Do not use SELECT * — list columns explicitly.

Database schema:
{schema}
"""



_MODEL = "llama-3.3-70b-versatile"

def run(state: AgentState) -> AgentState:
    """LangGraph node: translate the latest user message into SQL.
    
    If vector_embeddings are available (from analyze_query), modifies the 
    prompt to include vector distance ordering in the results.
    """
    messages = state.get("messages", [])
    use_vector_search = state.get("use_vector_search", False)
    vector_search_query = state.get("vector_search_query")

    # Extract the latest user question
    user_question = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_question = msg["content"]
            break

    if not user_question:
        return {**state, "error": "No user message found.", "agent_output": None}

    # Build the user prompt with vector search instructions if applicable
    if use_vector_search and vector_search_query:
        # Tell the LLM that vector search should be used
        user_prompt = (
            f"{user_question}\n\n"
            f"[VECTOR SEARCH HINT] This query has semantic components that will be matched using embeddings. "
            f"Ensure the SQL query includes the embeddings comparison mentioned."
        )
        print(f"[english_to_sql] using vector search for: '{vector_search_query}'")
    else:
        user_prompt = user_question
        print(f"[english_to_sql] standard SQL query (no vector search)")

    try:
        response = client.chat.completions.create(
            model=_MODEL,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT.format(schema=schema)},
                {"role": "user", "content": user_prompt},
            ],
        )
        output = response.choices[0].message.content.strip()
        sql = _clean_sql(output)
        
        # Store metadata about vector search usage
        return {
            **state, 
            "agent_output": sql, 
            "error": None,
            "sql_has_vector": use_vector_search,
        }

    except Exception as exc:
        return {**state, "agent_output": None, "error": f"SQL agent error: {exc}"}




# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_sql(text: str) -> str:
    """Strip markdown fences if the model accidentally includes them."""
    text = text.strip()
    # Remove ```sql … ``` or ``` … ```
    text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()
