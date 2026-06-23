-- =============================================================================
-- Add vector embedding support to movie_summary
-- Run this once in the Supabase SQL editor before running embed_movies.py
-- =============================================================================

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Add the embedding column
-- 384 dimensions matches the all-MiniLM-L6-v2 model output size.
-- If you switch models later, this number must match that model's output size.
ALTER TABLE movie_summary
    ADD COLUMN IF NOT EXISTS embedding vector(384);

-- Track what text actually went into each embedding, for debugging/audit
-- and so re-runs can detect if source fields changed since last embed.
ALTER TABLE movie_summary
    ADD COLUMN IF NOT EXISTS embedding_source_text TEXT;

ALTER TABLE movie_summary
    ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ;

-- HNSW index for fast similarity search at scale.
-- Uses cosine distance to match how embed_movies.py will query later.
-- Safe to run even with few rows; only matters for performance once you scale up.
CREATE INDEX IF NOT EXISTS idx_movie_summary_embedding
    ON movie_summary
    USING hnsw (embedding vector_cosine_ops);