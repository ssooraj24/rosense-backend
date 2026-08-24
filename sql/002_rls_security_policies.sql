-- ============================================================================
-- RoSense AI - Row Level Security Policies (002_rls_security_policies.sql)
-- Multi-Tenant Isolation & Security Layer 01 Implementation
-- ============================================================================

-- Enable Row Level Security on all core tables
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.department_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.iam_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.role_policy_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_policy_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- HELPER FUNCTIONS FOR JWT CLAIMS & ROLES
-- ============================================================================

-- Function to extract user_id from current session
CREATE OR REPLACE FUNCTION public.current_user_id()
RETURNS UUID AS $$
    SELECT COALESCE(
        nullif(current_setting('request.jwt.claim.sub', true), '')::uuid,
        auth.uid()
    );
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- Function to extract user's current organization_id
CREATE OR REPLACE FUNCTION public.current_org_id()
RETURNS UUID AS $$
    SELECT COALESCE(
        nullif(current_setting('request.jwt.claims.org_id', true), '')::uuid,
        (SELECT org_id FROM public.profiles WHERE id = auth.uid())
    );
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- Function to check if current user is RoSense AI Superadmin
CREATE OR REPLACE FUNCTION public.is_superadmin()
RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.user_roles
        WHERE user_id = auth.uid()
        AND role = 'superadmin'
    );
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- Function to check if current user is Organization Admin for their tenant
CREATE OR REPLACE FUNCTION public.is_org_admin(target_org_id UUID)
RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.user_roles
        WHERE user_id = auth.uid()
        AND org_id = target_org_id
        AND role IN ('superadmin', 'org_admin')
    );
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- ============================================================================
-- 1. ORGANIZATIONS RLS POLICIES
-- ============================================================================
CREATE POLICY organizations_select_policy ON public.organizations
    FOR SELECT
    USING (
        is_superadmin() OR id = current_org_id()
    );

CREATE POLICY organizations_insert_policy ON public.organizations
    FOR INSERT
    WITH CHECK (
        is_superadmin()
    );

CREATE POLICY organizations_update_policy ON public.organizations
    FOR UPDATE
    USING (
        is_superadmin() OR (id = current_org_id() AND is_org_admin(id))
    )
    WITH CHECK (
        is_superadmin() OR (id = current_org_id() AND is_org_admin(id))
    );

CREATE POLICY organizations_delete_policy ON public.organizations
    FOR DELETE
    USING (
        is_superadmin()
    );

-- ============================================================================
-- 2. DEPARTMENTS RLS POLICIES
-- ============================================================================
CREATE POLICY departments_tenant_isolation ON public.departments
    FOR ALL
    USING (
        is_superadmin() OR org_id = current_org_id()
    )
    WITH CHECK (
        is_superadmin() OR org_id = current_org_id()
    );

-- ============================================================================
-- 3. PROFILES RLS POLICIES
-- ============================================================================
CREATE POLICY profiles_select_policy ON public.profiles
    FOR SELECT
    USING (
        is_superadmin() OR org_id = current_org_id() OR id = auth.uid()
    );

CREATE POLICY profiles_update_policy ON public.profiles
    FOR UPDATE
    USING (
        is_superadmin() OR id = auth.uid() OR is_org_admin(org_id)
    )
    WITH CHECK (
        is_superadmin() OR id = auth.uid() OR is_org_admin(org_id)
    );

-- ============================================================================
-- 4. USER ROLES RLS POLICIES
-- ============================================================================
CREATE POLICY user_roles_tenant_isolation ON public.user_roles
    FOR ALL
    USING (
        is_superadmin() OR org_id = current_org_id()
    )
    WITH CHECK (
        is_superadmin() OR is_org_admin(org_id)
    );

-- ============================================================================
-- 5. DEPARTMENT MEMBERS RLS POLICIES
-- ============================================================================
CREATE POLICY department_members_isolation ON public.department_members
    FOR ALL
    USING (
        is_superadmin() OR EXISTS (
            SELECT 1 FROM public.departments d
            WHERE d.id = department_members.department_id
            AND d.org_id = current_org_id()
        )
    );

-- ============================================================================
-- 6. IAM POLICIES RLS POLICIES
-- ============================================================================
CREATE POLICY iam_policies_select ON public.iam_policies
    FOR SELECT
    USING (
        is_system_policy OR is_superadmin() OR org_id = current_org_id()
    );

CREATE POLICY iam_policies_modify ON public.iam_policies
    FOR ALL
    USING (
        is_superadmin() OR (org_id = current_org_id() AND is_org_admin(org_id) AND NOT is_system_policy)
    )
    WITH CHECK (
        is_superadmin() OR (org_id = current_org_id() AND is_org_admin(org_id) AND NOT is_system_policy)
    );

-- ============================================================================
-- 7. AUDIT LOGS RLS POLICIES (Immutable Read-Only Access)
-- ============================================================================
CREATE POLICY audit_logs_select ON public.audit_logs
    FOR SELECT
    USING (
        is_superadmin() OR org_id = current_org_id()
    );

CREATE POLICY audit_logs_insert ON public.audit_logs
    FOR INSERT
    WITH CHECK (
        is_superadmin() OR org_id = current_org_id() OR org_id IS NULL
    );

-- Prevent update and delete on audit logs to ensure immutability
CREATE POLICY audit_logs_no_update ON public.audit_logs
    FOR UPDATE USING (FALSE);

CREATE POLICY audit_logs_no_delete ON public.audit_logs
    FOR DELETE USING (FALSE);
