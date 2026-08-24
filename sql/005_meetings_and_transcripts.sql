-- ============================================================================
-- RoSense AI - Meetings & Stage 1 Transcripts Schema (005_meetings_and_transcripts.sql)
-- Architecture: Multi-tenant meetings, WhisperX diarized transcripts & pipeline jobs
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. MEETING PROCESSING STATUS ENUM
-- ============================================================================
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'meeting_status') THEN
        CREATE TYPE meeting_status AS ENUM (
            'uploading',
            'queued',
            'transcribing',
            'stage1_completed',
            'stage2_embedding',
            'stage3_mamba_extracting',
            'ready',
            'failed'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pipeline_stage') THEN
        CREATE TYPE pipeline_stage AS ENUM (
            'stage1_whisperx_stt',
            'stage2_bge_embedding',
            'stage3_mamba_extraction',
            'stage4_llm_synthesis'
        );
    END IF;
END $$;

-- ============================================================================
-- 2. MEETINGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.meetings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    department_id UUID REFERENCES public.departments(id) ON DELETE SET NULL,
    created_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    audio_file_path TEXT,
    audio_file_name VARCHAR(255),
    audio_mime_type VARCHAR(100),
    audio_size_bytes BIGINT DEFAULT 0,
    audio_duration_seconds FLOAT DEFAULT 0.0,
    status meeting_status NOT NULL DEFAULT 'queued',
    language VARCHAR(20) DEFAULT 'en',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_meetings_org_created ON public.meetings(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_meetings_dept ON public.meetings(department_id);
CREATE INDEX IF NOT EXISTS idx_meetings_status ON public.meetings(status);

-- ============================================================================
-- 3. SPEAKERS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.speakers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    speaker_label VARCHAR(50) NOT NULL, -- e.g., 'SPEAKER_00', 'SPEAKER_01'
    detected_name VARCHAR(255),          -- e.g., 'Rahul Sharma'
    user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    role VARCHAR(100),                  -- e.g., 'Partner', 'Engineering Lead'
    color_code VARCHAR(30) DEFAULT '#10B981',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(meeting_id, speaker_label)
);

CREATE INDEX IF NOT EXISTS idx_speakers_meeting ON public.speakers(meeting_id);
CREATE INDEX IF NOT EXISTS idx_speakers_org ON public.speakers(org_id);

-- ============================================================================
-- 4. TRANSCRIPT CHUNKS (Stage 1 Output)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.transcript_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    speaker_id UUID REFERENCES public.speakers(id) ON DELETE SET NULL,
    speaker_label VARCHAR(50) NOT NULL DEFAULT 'SPEAKER_00',
    sequence_index INTEGER NOT NULL DEFAULT 0,
    start_time FLOAT NOT NULL,           -- seconds from start of audio
    end_time FLOAT NOT NULL,             -- seconds from start of audio
    text TEXT NOT NULL,
    confidence FLOAT DEFAULT 0.95,
    words_json JSONB DEFAULT '[]'::jsonb, -- detailed word-level timings
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transcript_meeting_seq ON public.transcript_chunks(meeting_id, sequence_index ASC);
CREATE INDEX IF NOT EXISTS idx_transcript_speaker ON public.transcript_chunks(speaker_id);
CREATE INDEX IF NOT EXISTS idx_transcript_org ON public.transcript_chunks(org_id);

-- ============================================================================
-- 5. PIPELINE JOBS AUDIT / STATUS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.pipeline_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    stage pipeline_stage NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'running', -- 'running', 'completed', 'failed'
    progress_pct INTEGER DEFAULT 0,
    logs TEXT,
    error_details TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_meeting ON public.pipeline_jobs(meeting_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_org ON public.pipeline_jobs(org_id);

-- ============================================================================
-- 6. ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================
ALTER TABLE public.meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.speakers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transcript_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_jobs ENABLE ROW LEVEL SECURITY;

-- Meetings RLS
CREATE POLICY meetings_tenant_isolation ON public.meetings
    FOR ALL
    USING (
        is_superadmin() OR org_id = current_org_id()
    )
    WITH CHECK (
        is_superadmin() OR org_id = current_org_id()
    );

-- Speakers RLS
CREATE POLICY speakers_tenant_isolation ON public.speakers
    FOR ALL
    USING (
        is_superadmin() OR org_id = current_org_id()
    )
    WITH CHECK (
        is_superadmin() OR org_id = current_org_id()
    );

-- Transcript Chunks RLS
CREATE POLICY transcript_chunks_tenant_isolation ON public.transcript_chunks
    FOR ALL
    USING (
        is_superadmin() OR org_id = current_org_id()
    )
    WITH CHECK (
        is_superadmin() OR org_id = current_org_id()
    );

-- Pipeline Jobs RLS
CREATE POLICY pipeline_jobs_tenant_isolation ON public.pipeline_jobs
    FOR ALL
    USING (
        is_superadmin() OR org_id = current_org_id()
    )
    WITH CHECK (
        is_superadmin() OR org_id = current_org_id()
    );
