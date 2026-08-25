-- ============================================================================
-- RoSense AI - Stage 3 Mamba SSM Extraction Schema
-- Migration File: 007_stage3_mamba_extraction.sql
-- Architecture: Decisions, Tasks, Risks, Speaker Dynamics & Executive Insights
-- ============================================================================

-- Enable UUID extension if not present
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. DECISION STATUS & PRIORITY ENUMS
-- ============================================================================
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'decision_status') THEN
        CREATE TYPE decision_status AS ENUM ('open', 'approved', 'rejected', 'superseded');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_priority') THEN
        CREATE TYPE task_priority AS ENUM ('low', 'medium', 'high', 'critical');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_status') THEN
        CREATE TYPE task_status AS ENUM ('pending', 'in_progress', 'completed', 'cancelled');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'risk_severity') THEN
        CREATE TYPE risk_severity AS ENUM ('low', 'medium', 'high', 'critical');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'risk_status') THEN
        CREATE TYPE risk_status AS ENUM ('identified', 'mitigating', 'mitigated', 'accepted');
    END IF;
END $$;

-- ============================================================================
-- 2. DECISIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    owner_speaker_id UUID REFERENCES public.speakers(id) ON DELETE SET NULL,
    speaker_label VARCHAR(50) NOT NULL DEFAULT 'SPEAKER_00',
    reason TEXT,
    status decision_status NOT NULL DEFAULT 'approved',
    confidence FLOAT DEFAULT 0.92,
    evidence_chunk_ids UUID[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decisions_meeting ON public.decisions(meeting_id);
CREATE INDEX IF NOT EXISTS idx_decisions_org ON public.decisions(org_id);
CREATE INDEX IF NOT EXISTS idx_decisions_owner ON public.decisions(owner_speaker_id);

-- ============================================================================
-- 3. TASKS / ACTION ITEMS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    assignee_speaker_id UUID REFERENCES public.speakers(id) ON DELETE SET NULL,
    speaker_label VARCHAR(50) NOT NULL DEFAULT 'SPEAKER_00',
    assignee_name VARCHAR(255),
    due_date DATE,
    due_timeframe VARCHAR(100),
    priority task_priority NOT NULL DEFAULT 'medium',
    status task_status NOT NULL DEFAULT 'pending',
    confidence FLOAT DEFAULT 0.90,
    evidence_chunk_ids UUID[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_meeting ON public.tasks(meeting_id);
CREATE INDEX IF NOT EXISTS idx_tasks_org ON public.tasks(org_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON public.tasks(assignee_speaker_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON public.tasks(status);

-- ============================================================================
-- 4. RISKS & OBJECTIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.risks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    severity risk_severity NOT NULL DEFAULT 'medium',
    owner_speaker_id UUID REFERENCES public.speakers(id) ON DELETE SET NULL,
    speaker_label VARCHAR(50) NOT NULL DEFAULT 'SPEAKER_00',
    mitigation TEXT,
    status risk_status NOT NULL DEFAULT 'identified',
    confidence FLOAT DEFAULT 0.88,
    evidence_chunk_ids UUID[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risks_meeting ON public.risks(meeting_id);
CREATE INDEX IF NOT EXISTS idx_risks_org ON public.risks(org_id);
CREATE INDEX IF NOT EXISTS idx_risks_owner ON public.risks(owner_speaker_id);

-- ============================================================================
-- 5. SPEAKER DYNAMICS & SENTIMENT TABLE (Meeting Mood Map)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.speaker_dynamics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    speaker_id UUID REFERENCES public.speakers(id) ON DELETE SET NULL,
    speaker_label VARCHAR(50) NOT NULL,
    sentiment VARCHAR(30) NOT NULL DEFAULT 'neutral', -- 'positive', 'neutral', 'negative', 'mixed'
    dominant_emotion VARCHAR(50) NOT NULL DEFAULT 'confident', -- 'confident', 'defensive', 'supportive', 'frustrated', 'collaborative'
    intensity INTEGER DEFAULT 5, -- 1 to 10
    confidence_score FLOAT DEFAULT 0.90,
    concern_level VARCHAR(30) DEFAULT 'low', -- 'low', 'medium', 'high', 'critical'
    concern_summary TEXT,
    agreement_stance VARCHAR(50) DEFAULT 'aligned', -- 'aligned', 'partial_agreement', 'disagreeing', 'neutral'
    commitment_level VARCHAR(30) DEFAULT 'high', -- 'high', 'medium', 'low'
    tone VARCHAR(50) DEFAULT 'formal', -- 'formal', 'casual', 'assertive', 'collaborative'
    key_quotes JSONB DEFAULT '[]'::jsonb,
    speaking_share_pct FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(meeting_id, speaker_label)
);

CREATE INDEX IF NOT EXISTS idx_dynamics_meeting ON public.speaker_dynamics(meeting_id);
CREATE INDEX IF NOT EXISTS idx_dynamics_speaker ON public.speaker_dynamics(speaker_id);
CREATE INDEX IF NOT EXISTS idx_dynamics_org ON public.speaker_dynamics(org_id);

-- ============================================================================
-- 6. MEETING EXECUTIVE INSIGHTS & HEALTH TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.meeting_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    executive_summary TEXT NOT NULL,
    key_highlights JSONB DEFAULT '[]'::jsonb,
    agenda_covered JSONB DEFAULT '[]'::jsonb,
    unresolved_questions JSONB DEFAULT '[]'::jsonb,
    decision_quality_score FLOAT DEFAULT 85.0, -- percentage
    alignment_score FLOAT DEFAULT 80.0,        -- percentage
    risk_index FLOAT DEFAULT 15.0,             -- percentage
    meeting_health_rating VARCHAR(30) DEFAULT 'Healthy', -- 'Healthy', 'Moderate Risk', 'High Tension'
    mamba_checkpoint_path TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(meeting_id)
);

CREATE INDEX IF NOT EXISTS idx_insights_meeting ON public.meeting_insights(meeting_id);
CREATE INDEX IF NOT EXISTS idx_insights_org ON public.meeting_insights(org_id);

-- ============================================================================
-- 7. ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================
ALTER TABLE public.decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.speaker_dynamics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.meeting_insights ENABLE ROW LEVEL SECURITY;

CREATE POLICY decisions_tenant_isolation ON public.decisions
    FOR ALL
    USING (is_superadmin() OR org_id = current_org_id())
    WITH CHECK (is_superadmin() OR org_id = current_org_id());

CREATE POLICY tasks_tenant_isolation ON public.tasks
    FOR ALL
    USING (is_superadmin() OR org_id = current_org_id())
    WITH CHECK (is_superadmin() OR org_id = current_org_id());

CREATE POLICY risks_tenant_isolation ON public.risks
    FOR ALL
    USING (is_superadmin() OR org_id = current_org_id())
    WITH CHECK (is_superadmin() OR org_id = current_org_id());

CREATE POLICY speaker_dynamics_tenant_isolation ON public.speaker_dynamics
    FOR ALL
    USING (is_superadmin() OR org_id = current_org_id())
    WITH CHECK (is_superadmin() OR org_id = current_org_id());

CREATE POLICY meeting_insights_tenant_isolation ON public.meeting_insights
    FOR ALL
    USING (is_superadmin() OR org_id = current_org_id())
    WITH CHECK (is_superadmin() OR org_id = current_org_id());
