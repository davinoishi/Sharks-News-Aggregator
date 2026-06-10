-- Migration: Store hashed submitter IPs instead of raw IPs (brief 03, S5)
-- Date: 2026-06-10
--
-- submissions.submitter_ip now holds a salted SHA-256 hex digest (64 chars)
-- rather than a raw IPv4/IPv6 string. Widen the column to fit the digest.
--
-- Existing rows keep their old raw-IP values; they simply won't match the new
-- hash format and age out of the 1-hour rate-limit window. Optionally clear
-- them (uncomment below) to purge any historical raw IPs.

ALTER TABLE submissions ALTER COLUMN submitter_ip TYPE VARCHAR(64);

-- Optional: purge historical raw IPs.
-- UPDATE submissions SET submitter_ip = NULL WHERE length(submitter_ip) <> 64;

-- Verification (uncomment to run):
-- SELECT column_name, data_type, character_maximum_length
--   FROM information_schema.columns
--  WHERE table_name = 'submissions' AND column_name = 'submitter_ip';
