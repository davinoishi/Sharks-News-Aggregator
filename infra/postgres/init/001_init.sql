-- Sharks Aggregator Database Schema
-- Based on Engineering Execution PRD

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Source categories: official, press, other
CREATE TYPE source_category AS ENUM ('official', 'press', 'other');

-- Source status lifecycle
CREATE TYPE source_status AS ENUM ('candidate', 'queued_for_review', 'approved', 'rejected');

-- Ingest methods
CREATE TYPE ingest_method AS ENUM ('rss', 'html', 'api', 'reddit', 'twitter');

-- Content types
CREATE TYPE content_type AS ENUM ('article', 'video', 'podcast', 'social_post', 'forum_post');

-- Cluster and variant status
CREATE TYPE cluster_status AS ENUM ('active', 'archived', 'merged');
CREATE TYPE variant_status AS ENUM ('active', 'pending_cluster', 'archived');

-- Submission status
CREATE TYPE submission_status AS ENUM ('received', 'published', 'pending_review', 'rejected', 'duplicate');

-- Event types for clustering
CREATE TYPE event_type AS ENUM ('trade', 'injury', 'lineup', 'recall', 'waiver', 'signing', 'prospect', 'game', 'opinion', 'other');

-- ============================================================================
-- SOURCES TABLE
-- ============================================================================
CREATE TABLE sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category source_category NOT NULL,
    ingest_method ingest_method NOT NULL,
    base_url TEXT NOT NULL,
    feed_url TEXT,
    status source_status NOT NULL DEFAULT 'approved',
    priority INTEGER DEFAULT 100,
    last_fetched_at TIMESTAMPTZ,
    fetch_error_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sources_status ON sources(status);
CREATE INDEX idx_sources_category ON sources(category);

-- ============================================================================
-- RAW ITEMS TABLE
-- ============================================================================
CREATE TABLE raw_items (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id) ON DELETE CASCADE,
    source_item_id VARCHAR(500),  -- external ID from RSS/API
    ingestion_origin VARCHAR(50) DEFAULT 'scheduled',  -- 'scheduled' or 'user_submitted'
    original_url TEXT NOT NULL,
    canonical_url TEXT,
    raw_title TEXT,
    raw_description TEXT,
    raw_content TEXT,
    published_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    ingest_hash VARCHAR(64),  -- fallback dedup key
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_raw_items_source_item ON raw_items(source_id, source_item_id) WHERE source_item_id IS NOT NULL;
CREATE UNIQUE INDEX idx_raw_items_canonical_url ON raw_items(canonical_url) WHERE canonical_url IS NOT NULL;
CREATE INDEX idx_raw_items_published_at ON raw_items(published_at DESC);

-- ============================================================================
-- ENTITIES TABLE
-- ============================================================================
CREATE TABLE entities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    entity_type VARCHAR(50) NOT NULL,  -- 'player', 'coach', 'team', 'staff'
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_entities_type ON entities(entity_type);

-- ============================================================================
-- TAGS TABLE
-- ============================================================================
CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    display_color VARCHAR(7),  -- hex color code
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default tags
INSERT INTO tags (name, slug, display_color) VALUES
    ('News', 'news', '#1E90FF'),
    ('Rumors Press', 'rumors-press', '#FF8C00'),
    ('Rumors Other', 'rumors-other', '#FFD700'),
    ('Injury', 'injury', '#DC143C'),
    ('Trade', 'trade', '#32CD32'),
    ('Lineup', 'lineup', '#8A2BE2'),
    ('Recall', 'recall', '#00CED1'),
    ('Waiver', 'waiver', '#FF6347'),
    ('Signing', 'signing', '#20B2AA'),
    ('Prospect', 'prospect', '#FF69B4'),
    ('Game', 'game', '#4169E1'),
    ('Official', 'official', '#228B22'),
    ('Barracuda', 'barracuda', '#F47920');

-- ============================================================================
-- CLUSTERS TABLE
-- ============================================================================
CREATE TABLE clusters (
    id SERIAL PRIMARY KEY,
    headline TEXT NOT NULL,
    headline_source_signal INTEGER DEFAULT 1,  -- 1=other, 2=press, 3=official
    event_type event_type NOT NULL DEFAULT 'other',
    status cluster_status NOT NULL DEFAULT 'active',
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    tokens TEXT[],  -- normalized tokens for clustering
    entities_agg INTEGER[],  -- aggregated entity IDs
    source_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_clusters_status_last_seen ON clusters(status, last_seen_at DESC);
CREATE INDEX idx_clusters_event_type ON clusters(event_type);
CREATE INDEX idx_clusters_first_seen ON clusters(first_seen_at DESC);

-- ============================================================================
-- STORY VARIANTS TABLE
-- ============================================================================
CREATE TABLE story_variants (
    id SERIAL PRIMARY KEY,
    raw_item_id INTEGER REFERENCES raw_items(id) ON DELETE CASCADE,
    source_id INTEGER REFERENCES sources(id) ON DELETE CASCADE,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    content_type content_type NOT NULL DEFAULT 'article',
    published_at TIMESTAMPTZ NOT NULL,
    tokens TEXT[],  -- normalized tokens
    entities INTEGER[],  -- entity IDs
    event_type event_type NOT NULL DEFAULT 'other',
    source_signal INTEGER DEFAULT 1,  -- derived from source.category
    status variant_status NOT NULL DEFAULT 'active',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_story_variants_published_at ON story_variants(published_at DESC);
CREATE INDEX idx_story_variants_source ON story_variants(source_id);
CREATE INDEX idx_story_variants_status ON story_variants(status);
CREATE INDEX idx_story_variants_event_type ON story_variants(event_type);

-- ============================================================================
-- CLUSTER VARIANTS MAPPING TABLE
-- ============================================================================
CREATE TABLE cluster_variants (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER REFERENCES clusters(id) ON DELETE CASCADE,
    variant_id INTEGER REFERENCES story_variants(id) ON DELETE CASCADE,
    similarity_score NUMERIC(5, 3),
    added_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(cluster_id, variant_id)
);

CREATE INDEX idx_cluster_variants_cluster ON cluster_variants(cluster_id);
CREATE INDEX idx_cluster_variants_variant ON cluster_variants(variant_id);

-- ============================================================================
-- CLUSTER TAGS MAPPING TABLE
-- ============================================================================
CREATE TABLE cluster_tags (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER REFERENCES clusters(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(cluster_id, tag_id)
);

CREATE INDEX idx_cluster_tags_cluster ON cluster_tags(cluster_id);
CREATE INDEX idx_cluster_tags_tag ON cluster_tags(tag_id);

-- ============================================================================
-- CLUSTER ENTITIES MAPPING TABLE
-- ============================================================================
CREATE TABLE cluster_entities (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER REFERENCES clusters(id) ON DELETE CASCADE,
    entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(cluster_id, entity_id)
);

CREATE INDEX idx_cluster_entities_cluster ON cluster_entities(cluster_id);
CREATE INDEX idx_cluster_entities_entity ON cluster_entities(entity_id);

-- ============================================================================
-- SUBMISSIONS TABLE
-- ============================================================================
CREATE TABLE submissions (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL,
    normalized_url TEXT,
    domain VARCHAR(255),
    note TEXT,
    submitter_ip VARCHAR(45),
    status submission_status NOT NULL DEFAULT 'received',
    raw_item_id INTEGER REFERENCES raw_items(id) ON DELETE SET NULL,
    variant_id INTEGER REFERENCES story_variants(id) ON DELETE SET NULL,
    cluster_id INTEGER REFERENCES clusters(id) ON DELETE SET NULL,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX idx_submissions_status ON submissions(status);
CREATE INDEX idx_submissions_created_at ON submissions(created_at DESC);
CREATE INDEX idx_submissions_domain ON submissions(domain);

-- ============================================================================
-- CANDIDATE SOURCES TABLE
-- ============================================================================
CREATE TABLE candidate_sources (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL UNIQUE,
    base_url TEXT NOT NULL,
    discovered_from_submission_id INTEGER REFERENCES submissions(id) ON DELETE SET NULL,
    suggested_category source_category,
    suggested_ingest_method ingest_method,
    discovered_feed_url TEXT,
    rss_discovery_attempted BOOLEAN DEFAULT FALSE,
    rss_discovery_success BOOLEAN DEFAULT FALSE,
    status source_status NOT NULL DEFAULT 'candidate',
    evidence JSONB DEFAULT '{}',  -- sample articles, metadata
    review_notes TEXT,
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_candidate_sources_status ON candidate_sources(status);
CREATE INDEX idx_candidate_sources_domain ON candidate_sources(domain);

-- ============================================================================
-- FEED CACHE TABLE (Optional - can use Redis instead)
-- ============================================================================
CREATE TABLE feed_cache (
    id SERIAL PRIMARY KEY,
    cache_key VARCHAR(500) NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_feed_cache_key ON feed_cache(cache_key);
CREATE INDEX idx_feed_cache_expires ON feed_cache(expires_at);

-- ============================================================================
-- HEALTHCHECK TABLE
-- ============================================================================
CREATE TABLE healthcheck (
    id SERIAL PRIMARY KEY,
    ok BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- UPDATE TRIGGERS
-- ============================================================================

-- Auto-update updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_sources_updated_at BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_clusters_updated_at BEFORE UPDATE ON clusters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_candidate_sources_updated_at BEFORE UPDATE ON candidate_sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Feed view with aggregated data
CREATE VIEW feed_view AS
SELECT
    c.id,
    c.headline,
    c.event_type,
    c.first_seen_at,
    c.last_seen_at,
    c.source_count,
    c.status,
    COALESCE(json_agg(DISTINCT jsonb_build_object('id', t.id, 'name', t.name, 'slug', t.slug, 'color', t.display_color))
        FILTER (WHERE t.id IS NOT NULL), '[]') as tags,
    COALESCE(json_agg(DISTINCT jsonb_build_object('id', e.id, 'name', e.name, 'slug', e.slug, 'type', e.entity_type))
        FILTER (WHERE e.id IS NOT NULL), '[]') as entities
FROM clusters c
LEFT JOIN cluster_tags ct ON c.id = ct.cluster_id
LEFT JOIN tags t ON ct.tag_id = t.id
LEFT JOIN cluster_entities ce ON c.id = ce.cluster_id
LEFT JOIN entities e ON ce.entity_id = e.id
WHERE c.status = 'active'
GROUP BY c.id, c.headline, c.event_type, c.first_seen_at, c.last_seen_at, c.source_count, c.status;

-- Cluster detail view with all variants
CREATE VIEW cluster_detail_view AS
SELECT
    c.id as cluster_id,
    c.headline,
    c.event_type,
    c.first_seen_at,
    c.last_seen_at,
    json_agg(
        json_build_object(
            'variant_id', sv.id,
            'title', sv.title,
            'url', sv.url,
            'published_at', sv.published_at,
            'content_type', sv.content_type,
            'source_name', s.name,
            'source_category', s.category
        )
        ORDER BY s.category DESC, sv.published_at DESC
    ) as variants
FROM clusters c
INNER JOIN cluster_variants cv ON c.id = cv.cluster_id
INNER JOIN story_variants sv ON cv.variant_id = sv.id
INNER JOIN sources s ON sv.source_id = s.id
GROUP BY c.id, c.headline, c.event_type, c.first_seen_at, c.last_seen_at;
