-- ============================================================================
-- RoSense AI - Stage 2 Dense Vector Indexing (BGE-Large + pgvector)
-- Migration File: 006_stage2_vector_embeddings.sql
-- Architecture: 1024-dimension BGE embeddings, HNSW index, RLS isolation & RPC search
-- ============================================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS "vector";

-- 2. Stage 2 Transcript Embeddings Table
CREATE TABLE IF NOT EXISTS public.transcript_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    chunk_id UUID REFERENCES public.transcript_chunks(id) ON DELETE CASCADE,
    speaker_id UUID REFERENCES public.speakers(id) ON DELETE SET NULL,
    speaker_label VARCHAR(50) NOT NULL DEFAULT 'SPEAKER_00',
    sequence_index INTEGER NOT NULL DEFAULT 0,
    start_time FLOAT NOT NULL DEFAULT 0.0,
    end_time FLOAT NOT NULL DEFAULT 0.0,
    chunk_text TEXT NOT NULL,
    embedding vector(1024) NOT NULL, -- BAAI/bge-large-en-v1.5 1024-dim dense vector
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Standard Relational Indexes
CREATE INDEX IF NOT EXISTS idx_transcript_embeddings_meeting ON public.transcript_embeddings(meeting_id, sequence_index ASC);
CREATE INDEX IF NOT EXISTS idx_transcript_embeddings_org ON public.transcript_embeddings(org_id);
CREATE INDEX IF NOT EXISTS idx_transcript_embeddings_chunk ON public.transcript_embeddings(chunk_id);
CREATE INDEX IF NOT EXISTS idx_transcript_embeddings_speaker ON public.transcript_embeddings(speaker_id);

-- 4. HNSW Vector Index for High-Throughput Approximate Nearest Neighbor (ANN) Cosine Similarity
CREATE INDEX IF NOT EXISTS idx_transcript_embeddings_hnsw 
ON public.transcript_embeddings 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 5. Row Level Security (RLS) for Multi-Tenant Isolation
ALTER TABLE public.transcript_embeddings ENABLE ROW LEVEL SECURITY;

CREATE POLICY transcript_embeddings_tenant_isolation ON public.transcript_embeddings
    FOR ALL
    USING (
        is_superadmin() OR org_id = current_org_id()
    )
    WITH CHECK (
        is_superadmin() OR org_id = current_org_id()
    );

-- 6. Stored Function for Fast Vector Similarity Search (RPC Endpoint)
CREATE OR REPLACE FUNCTION public.match_transcript_embeddings(
    query_embedding vector(1024),
    match_threshold float DEFAULT 0.3,
    match_count int DEFAULT 10,
    filter_org_id uuid DEFAULT NULL,
    filter_meeting_id uuid DEFAULT NULL,
    filter_speaker_id uuid DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    meeting_id UUID,
    org_id UUID,
    chunk_id UUID,
    speaker_id UUID,
    speaker_label VARCHAR(50),
    sequence_index INTEGER,
    start_time FLOAT,
    end_time FLOAT,
    chunk_text TEXT,
    similarity FLOAT,
    metadata JSONB
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        te.id,
        te.meeting_id,
        te.org_id,
        te.chunk_id,
        te.speaker_id,
        te.speaker_label,
        te.sequence_index,
        te.start_time,
        te.end_time,
        te.chunk_text,
        ROUND((1 - (te.embedding <=> query_embedding))::numeric, 4)::float AS similarity,
        te.metadata
    FROM public.transcript_embeddings te
    WHERE 
        (filter_org_id IS NULL OR te.org_id = filter_org_id)
        AND (filter_meeting_id IS NULL OR te.meeting_id = filter_meeting_id)
        AND (filter_speaker_id IS NULL OR te.speaker_id = filter_speaker_id)
        AND (1 - (te.embedding <=> query_embedding)) >= match_threshold
    ORDER BY te.embedding <=> query_embedding ASC
    LIMIT match_count;
END;
$$;
