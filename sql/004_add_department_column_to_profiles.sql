-- ============================================================================
-- RoSense AI - Migration: Add 'department' column to profiles table
-- Run this in Supabase SQL Editor so department saves directly to profiles
-- ============================================================================

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS department VARCHAR(255);
