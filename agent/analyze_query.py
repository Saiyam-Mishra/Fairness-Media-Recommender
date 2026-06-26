"""Query analyzer agent.

Analyzes user queries to determine if semantic/vector search would be beneficial.
If so, captures the semantic portion of the query, encodes it to embeddings,
and passes it to the SQL agent for use in vector-based filtering/ranking.

This allows natural language semantic search (e.g., "heartwarming comedies") to
work alongside structured SQL filters.
"""
import os
from dotenv import load_dotenv
from groq import Groq
from sentence_transformers import SentenceTransformer

from state import AgentState

load_dotenv()

# Groq client for analyzer
client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

# Embedding model (same as embed_movies.py)
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

_SYSTEM_PROMPT = """You are a query analyzer for a movie recommendation system.

Analyze the user's query and determine if it contains semantic/semantic-search-friendly aspects.
Semantic search is useful for queries that ask about:
- Mood/tone: "heartwarming", "suspenseful", "romantic", "dark", "uplifting"
- Themes: "coming of age", "redemption", "time travel", "revolution", "love story"
- Plot concepts: "heist", "undercover", "revenge", "parallel universes"
- Vibe/feeling: "cozy", "thrilling", "emotional", "funny", "philosophical"

Structured (non-semantic) filters are better for:
- Specific attributes: "released in 2020", "rated PG-13", "directed by X", "starring Y"
- Counts/rankings: "top 10", "highest rated", "most popular"

Your response format (EXACTLY):
If the query HAS semantic elements, respond with:
SEMANTIC_QUERY: <the semantic/thematic part of the query>

If the query is ONLY structured/filtered (no semantic elements), respond with:
NO_SEMANTIC

Do not output anything else. One line only."""

_MODEL = "llama-3.3-70b-versatile"


def run(state: AgentState) -> AgentState:
    """Analyze the user query for semantic search potential.

    Returns state with:
    - vector_search_query: the semantic portion if detected (or None)
    - vector_embeddings: encoded embedding vector (or None)
    - use_vector_search: boolean flag
    """
    messages = state.get("messages", [])
    
    # Extract the latest user message
    user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_text = msg.get("content", "")
            break

    if not user_text:
        # No user text, no semantic search needed
        return {
            **state,
            "vector_search_query": None,
            "vector_embeddings": None,
            "use_vector_search": False,
        }

    try:
        # Ask LLM to analyze the query
        response = client.chat.completions.create(
            model=_MODEL,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
        )
        analysis = response.choices[0].message.content.strip()
        
        # Debug: show analysis result
        print(f"[analyze_query] analysis='{analysis}'")
        
        # Check if semantic search was identified
        if analysis.startswith("SEMANTIC_QUERY:"):
            semantic_part = analysis.replace("SEMANTIC_QUERY:", "").strip()
            
            # Encode the semantic portion
            print(f"[analyze_query] encoding semantic query: '{semantic_part}'")
            embeddings = embedding_model.encode(semantic_part, normalize_embeddings=True).tolist()
            
            print(f"[analyze_query] embedding generated (dim={len(embeddings)})")
            return {
                **state,
                "vector_search_query": semantic_part,
                "vector_embeddings": embeddings,
                "use_vector_search": True,
            }
        else:
            # No semantic component detected
            print(f"[analyze_query] no semantic component detected, using SQL only")
            return {
                **state,
                "vector_search_query": None,
                "vector_embeddings": None,
                "use_vector_search": False,
            }
            
    except Exception as exc:
        # If analysis fails, fall back to SQL-only (no vector search)
        print(f"[analyze_query] analysis failed: {exc}, using SQL only")
        return {
            **state,
            "vector_search_query": None,
            "vector_embeddings": None,
            "use_vector_search": False,
        }

