#!/usr/bin/env python3
"""
Migration script for bluesky_posts table.

Run this script to create the bluesky_posts table:
    python -m app.scripts.migrate_bluesky_posts

This is an idempotent operation - safe to run multiple times.
"""
from sqlalchemy import text
from app.core.database import engine


MIGRATION_SQL = """
-- Create bluesky_posts table for tracking BlueSky social media posts
CREATE TABLE IF NOT EXISTS bluesky_posts (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL UNIQUE REFERENCES clusters(id) ON DELETE CASCADE,
    status VARCHAR(10) NOT NULL DEFAULT 'pending',  -- pending, posted, failed, skipped
    post_uri VARCHAR(500),
    post_cid VARCHAR(100),
    post_text TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    posted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_bluesky_posts_cluster ON bluesky_posts(cluster_id);
CREATE INDEX IF NOT EXISTS idx_bluesky_posts_status ON bluesky_posts(status);
CREATE INDEX IF NOT EXISTS idx_bluesky_posts_created ON bluesky_posts(created_at);
CREATE INDEX IF NOT EXISTS idx_bluesky_posts_posted ON bluesky_posts(posted_at);
"""


def migrate():
    """Run the migration."""
    print("="*60)
    print("MIGRATION: bluesky_posts table")
    print("="*60)

    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'bluesky_posts'
            );
        """))
        exists = result.scalar()

        if exists:
            print("\n✓ Table 'bluesky_posts' already exists.")
            print("  Migration is idempotent - no changes made.")
        else:
            print("\nCreating table 'bluesky_posts'...")
            conn.execute(text(MIGRATION_SQL))
            conn.commit()
            print("✓ Table created successfully!")

        # Show table info
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'bluesky_posts'
            ORDER BY ordinal_position;
        """))
        columns = result.fetchall()

        print("\nTable structure:")
        for col in columns:
            nullable = "NULL" if col[2] == "YES" else "NOT NULL"
            print(f"  {col[0]:20} {col[1]:20} {nullable}")

        # Count existing records
        result = conn.execute(text("SELECT COUNT(*) FROM bluesky_posts"))
        count = result.scalar()
        print(f"\nCurrent record count: {count}")

    print("\n" + "="*60)


if __name__ == "__main__":
    migrate()
