-- Migration: Add game-centric clustering and LLM confidence tracking columns
-- Date: 2026-02-02
--
-- Part 1: Game-Centric Clustering
-- Adds game_identifier column to clusters table for grouping game previews/recaps
--
-- Part 2: LLM Accuracy Improvements
-- Adds llm_confidence and llm_reason columns to validation_logs for chain-of-thought tracking

-- Add game_identifier to clusters table
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS game_identifier VARCHAR(20);
CREATE INDEX IF NOT EXISTS ix_clusters_game_identifier ON clusters(game_identifier);

-- Add LLM confidence tracking to validation_logs table
ALTER TABLE validation_logs ADD COLUMN IF NOT EXISTS llm_confidence VARCHAR(10);
ALTER TABLE validation_logs ADD COLUMN IF NOT EXISTS llm_reason TEXT;

-- Update llm_response column to accommodate longer structured responses
ALTER TABLE validation_logs ALTER COLUMN llm_response TYPE VARCHAR(100);

-- Verification queries (uncomment to run):
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'clusters' AND column_name = 'game_identifier';
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'validation_logs' AND column_name IN ('llm_confidence', 'llm_reason');
