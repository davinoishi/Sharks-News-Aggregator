# SQLAlchemy Models Documentation

## Overview

All SQLAlchemy models have been created to match the database schema defined in `infra/postgres/init/001_init.sql`. The models provide ORM (Object-Relational Mapping) capabilities for Python code to interact with the PostgreSQL database.

## Model Files Created

### Core Models

1. **`app/models/source.py`** - Source
   - Represents ingestion sources (RSS feeds, websites, APIs)
   - Enums: `SourceCategory`, `SourceStatus`, `IngestMethod`
   - Properties: `source_signal` (for headline ranking)

2. **`app/models/raw_item.py`** - RawItem
   - Raw ingested content before processing
   - First stage of ingestion pipeline
   - Properties: `display_title` for UI

3. **`app/models/story_variant.py`** - StoryVariant
   - One source's version of a story
   - Enriched version of RawItem
   - Enums: `ContentType`, `VariantStatus`
   - Method: `to_dict()` for API responses

4. **`app/models/cluster.py`** - Cluster
   - Represents a single real-world event/story
   - Groups multiple variants together
   - Enums: `ClusterStatus`, `EventType`
   - Methods: `update_source_count()`, `get_tags()`, `get_entities()`

### Relationship Models

5. **`app/models/cluster_variant.py`** - ClusterVariant
   - Many-to-many mapping: Clusters ↔ StoryVariants
   - Stores similarity score used for clustering

6. **`app/models/cluster_tag.py`** - ClusterTag
   - Many-to-many mapping: Clusters ↔ Tags

7. **`app/models/cluster_entity.py`** - ClusterEntity
   - Many-to-many mapping: Clusters ↔ Entities

### Supporting Models

8. **`app/models/entity.py`** - Entity
   - Players, coaches, teams, staff
   - Static method: `make_slug()` for URL-friendly names

9. **`app/models/tag.py`** - Tag
   - Story categorization tags
   - Method: `to_dict()` for API responses

10. **`app/models/submission.py`** - Submission
    - User-submitted links (Option C)
    - Enum: `SubmissionStatus`
    - Method: `mark_processed()` for workflow

11. **`app/models/candidate_source.py`** - CandidateSource
    - Proposed sources awaiting admin review
    - Method: `approve_and_create_source()` for approval workflow

12. **`app/models/feed_cache.py`** - FeedCache
    - Optional database-backed cache
    - Property: `is_expired` to check validity

## Utility Files

### Database Utilities (`app/core/db_utils.py`)

Helper functions for common database operations:

- **`get_or_create_tag()`** - Idempotent tag creation
- **`get_or_create_entity()`** - Idempotent entity creation
- **`get_active_sources()`** - Get approved sources for ingestion
- **`get_tag_by_slug()`** - Lookup tag by slug
- **`get_entity_by_slug()`** - Lookup entity by slug
- **`add_tags_to_cluster()`** - Associate tags with cluster
- **`add_entities_to_cluster()`** - Associate entities with cluster
- **`get_candidate_clusters()`** - Get clusters for matching
- **`attach_variant_to_cluster()`** - Link variant to cluster
- **`find_variant_by_url()`** - URL-based deduplication
- **`check_submission_rate_limit()`** - Rate limiting logic

### Query Builders (`app/core/queries.py`)

Query functions for API endpoints:

- **`build_feed_query()`** - Main feed query with filters
  - Supports filtering by tags, entities, time
  - Returns paginated results with total count

- **`get_cluster_with_details()`** - Eager load cluster relationships

- **`get_cluster_variants_sorted()`** - Get variants sorted by:
  1. Source category (official → press → other)
  2. Recency (newest first)

- **`format_cluster_for_feed()`** - Format cluster for feed API

- **`format_cluster_detail()`** - Format cluster detail with variants

- **`search_entities_by_name()`** - Entity search

- **`get_recent_clusters_count()`** - Statistics

- **`get_tag_distribution()`** - Tag usage stats

## Model Relationships

### Relationship Graph

```
Source
  ├─→ RawItem (one-to-many)
  └─→ StoryVariant (one-to-many)

RawItem
  ├─→ StoryVariant (one-to-many)
  └─→ Submission (one-to-many)

StoryVariant
  ├─→ ClusterVariant (one-to-many)
  └─→ Submission (one-to-many)

Cluster
  ├─→ ClusterVariant (one-to-many) → StoryVariant
  ├─→ ClusterTag (one-to-many) → Tag
  ├─→ ClusterEntity (one-to-many) → Entity
  └─→ Submission (one-to-many)

Submission
  ├─→ RawItem (many-to-one)
  ├─→ StoryVariant (many-to-one)
  ├─→ Cluster (many-to-one)
  └─→ CandidateSource (one-to-many)

CandidateSource
  └─→ Submission (many-to-one)
```

## Enum Types

All enums are defined as string enums for PostgreSQL compatibility:

### SourceCategory
- `OFFICIAL` - Official team sources
- `PRESS` - Credentialed media
- `OTHER` - Fan forums, blogs

### SourceStatus
- `CANDIDATE` - Proposed source
- `QUEUED_FOR_REVIEW` - Awaiting admin review
- `APPROVED` - Active source
- `REJECTED` - Rejected source

### IngestMethod
- `RSS` - RSS feed
- `HTML` - HTML scraping
- `API` - API endpoint
- `REDDIT` - Reddit API
- `TWITTER` - Twitter/X API

### ContentType
- `ARTICLE` - News article
- `VIDEO` - Video content
- `PODCAST` - Audio podcast
- `SOCIAL_POST` - Social media post
- `FORUM_POST` - Forum discussion

### VariantStatus
- `ACTIVE` - Normal variant
- `PENDING_CLUSTER` - Awaiting clustering
- `ARCHIVED` - Old/inactive

### ClusterStatus
- `ACTIVE` - Current cluster
- `ARCHIVED` - Old cluster
- `MERGED` - Merged into another

### EventType
- `TRADE` - Trade news
- `INJURY` - Injury report
- `LINEUP` - Lineup change
- `RECALL` - Player recall
- `WAIVER` - Waiver claim
- `SIGNING` - Contract signing
- `PROSPECT` - Prospect news
- `GAME` - Game coverage
- `OPINION` - Opinion/analysis
- `OTHER` - Uncategorized

### SubmissionStatus
- `RECEIVED` - Just submitted
- `PUBLISHED` - Successfully published
- `PENDING_REVIEW` - Awaiting review
- `REJECTED` - Rejected
- `DUPLICATE` - Duplicate URL

## Usage Examples

### Creating a Cluster

```python
from app.models import Cluster, EventType, ClusterStatus
from datetime import datetime

cluster = Cluster(
    headline="Sharks trade for top prospect",
    event_type=EventType.TRADE,
    status=ClusterStatus.ACTIVE,
    first_seen_at=datetime.utcnow(),
    last_seen_at=datetime.utcnow(),
    tokens=["sharks", "trade", "prospect"],
    entities_agg=[1, 5, 12],
    source_count=1
)
db.add(cluster)
db.commit()
```

### Adding Tags to Cluster

```python
from app.core.db_utils import add_tags_to_cluster

add_tags_to_cluster(db, cluster, ["Trade", "Rumors Press"])
db.commit()
```

### Querying Feed

```python
from app.core.queries import build_feed_query

clusters, total = build_feed_query(
    db,
    tag_slugs=["trade", "injury"],
    limit=50,
    offset=0
)
```

### Getting Cluster Details

```python
from app.core.queries import format_cluster_detail

cluster = get_cluster_with_details(db, cluster_id=123)
formatted = format_cluster_detail(db, cluster)
```

## Next Steps

Now that models are complete, the next tasks are:

1. **Update Worker Tasks** - Replace TODO comments with actual model usage
   - `app/tasks/ingest.py` - Use Source, RawItem models
   - `app/tasks/enrich.py` - Use StoryVariant, Cluster models
   - `app/tasks/submissions.py` - Use Submission, CandidateSource models

2. **Update API Endpoints** - Replace placeholders with real queries
   - `app/main.py` - Use query builders from `queries.py`

3. **Create Initial Data Scripts**
   - Script to import `initial_sources.csv` into database
   - Script to populate entities table with Sharks roster

4. **Test Database Connectivity**
   - Run `docker-compose up` and verify all services start
   - Test database connection from API

## File Structure

```
api/
└── app/
    ├── models/
    │   ├── __init__.py              # Exports all models
    │   ├── source.py                # Source model
    │   ├── raw_item.py              # RawItem model
    │   ├── entity.py                # Entity model
    │   ├── tag.py                   # Tag model
    │   ├── cluster.py               # Cluster model
    │   ├── story_variant.py         # StoryVariant model
    │   ├── cluster_variant.py       # ClusterVariant mapping
    │   ├── cluster_tag.py           # ClusterTag mapping
    │   ├── cluster_entity.py        # ClusterEntity mapping
    │   ├── submission.py            # Submission model
    │   ├── candidate_source.py      # CandidateSource model
    │   └── feed_cache.py            # FeedCache model
    └── core/
        ├── database.py              # Database connection
        ├── db_utils.py              # Database utilities
        └── queries.py               # Query builders
```
