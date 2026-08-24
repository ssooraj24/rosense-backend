-- ============================================================================
-- RoSense AI - Migration: Add 'admin' and 'spoc' to app_role enum
-- Run this in Supabase SQL Editor to enable 'admin' and 'spoc' roles
-- ============================================================================

ALTER TYPE public.app_role ADD VALUE IF NOT EXISTS 'admin' AFTER 'superadmin';
ALTER TYPE public.app_role ADD VALUE IF NOT EXISTS 'spoc' AFTER 'org_admin';
