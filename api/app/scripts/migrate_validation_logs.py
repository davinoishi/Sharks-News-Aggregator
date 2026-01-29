#!/usr/bin/env python3
"""
Migration script for validation_logs table.

Run this script to create the validation_logs table:
    python -m app.scripts.migrate_validation_logs

This is an idempotent operation - safe to run multiple times.
"""
from sqlalchemy import text
from app.core.database import engine


MIGRATION_SQL = """
-- Create validation_logs table for LLM relevance checking audit trail
CREATE TABLE IF NOT EXISTS validation_logs (
    id SERIAL PRIMARY KEY,
    raw_item_id INTEGER NOT NULL REFERENCES raw_items(id) ON DELETE CASCADE,
    method VARCHAR(10) NOT NULL,  -- llm, keyword, skip
    result VARCHAR(10) NOT NULL,  -- approved, rejected, error
    llm_response VARCHAR(50),
    llm_model VARCHAR(100),
    keyword_matched BOOLEAN,
    entities_found JSONB DEFAULT '[]',
    reason TEXT,
    latency_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_validation_logs_raw_item ON validation_logs(raw_item_id);
CREATE INDEX IF NOT EXISTS idx_validation_logs_created ON validation_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_validation_logs_result ON validation_logs(result);
CREATE INDEX IF NOT EXISTS idx_validation_logs_method ON validation_logs(method);
"""


def migrate():
    """Run the migration."""
    print("="*60)
    print("MIGRATION: validation_logs table")
    print("="*60)

    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'validation_logs'
            );
        """))
        exists = result.scalar()

        if exists:
            print("\n✓ Table 'validation_logs' already exists.")
            print("  Migration is idempotent - no changes made.")
        else:
            print("\nCreating table 'validation_logs'...")
            conn.execute(text(MIGRATION_SQL))
            conn.commit()
            print("✓ Table created successfully!")

        # Show table info
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'validation_logs'
            ORDER BY ordinal_position;
        """))
        columns = result.fetchall()

        print("\nTable structure:")
        for col in columns:
            nullable = "NULL" if col[2] == "YES" else "NOT NULL"
            print(f"  {col[0]:20} {col[1]:20} {nullable}")

        # Count existing records
        result = conn.execute(text("SELECT COUNT(*) FROM validation_logs"))
        count = result.scalar()
        print(f"\nCurrent record count: {count}")

    print("\n" + "="*60)


if __name__ == "__main__":
    migrate()
