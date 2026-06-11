-- Migration: drop the unused feed_cache table (brief 04, P2)
-- Date: 2026-06-10
--
-- The feed_cache model/table was never read or written (the cleanup task was a
-- stub). The feed query is now cheap — keyset pagination + selectinload + a
-- limit+1 fetch with no count() — so a DB-backed feed cache adds complexity for
-- no measurable benefit on the Pi. Removing the table.

DROP TABLE IF EXISTS feed_cache;
