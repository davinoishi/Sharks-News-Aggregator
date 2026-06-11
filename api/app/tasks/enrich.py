"""Enrichment Celery task (brief 07, Q4).

This module is now a thin orchestrator: the heavy lifting lives in
``app.enrichment.*`` (entity extraction, relevance/event/tag classification,
clustering, and the NHL opponent table). The Celery task keeps its registered
name ``app.tasks.enrich.enrich_raw_item`` so messages already queued before a
deploy still resolve.

The helpers are re-exported here for backwards compatibility with existing
imports (``from app.tasks.enrich import ...``).
"""
from app.core.database import SessionLocal
from app.core.datetime_utils import utcnow
from app.enrichment.classify import (
    check_sharks_relevance,
    classify_article,
    classify_event_type_keyword,
    classify_tags_keyword,
    count_event_keyword_matches,
    log_validation,
    validate_sharks_relevance,
)
from app.enrichment.clustering import (
    add_cluster_entity_associations,
    add_cluster_tag_associations,
    create_cluster,
    entity_overlap_score,
    event_compatibility_score,
    get_cluster_entities,
    get_time_window_for_event,
    is_match,
    jaccard_similarity,
    match_or_create_cluster,
    normalize_title_for_matching,
    normalize_tokens,
    summary_similarity,
    title_similarity,
    update_cluster_metadata,
)
from app.enrichment.entities import (
    extract_entities,
    filter_team_entities,
    get_entity_names,
)
from app.enrichment.teams import NHL_OPPONENT_TEAMS, extract_game_identifier
from app.models.validation_log import ValidationMethod, ValidationResult
from app.tasks.celery_app import celery

__all__ = [
    "enrich_raw_item",
    # entities
    "extract_entities",
    "filter_team_entities",
    "get_entity_names",
    # classify
    "check_sharks_relevance",
    "validate_sharks_relevance",
    "log_validation",
    "classify_event_type_keyword",
    "count_event_keyword_matches",
    "classify_article",
    "classify_tags_keyword",
    # clustering
    "normalize_tokens",
    "match_or_create_cluster",
    "create_cluster",
    "update_cluster_metadata",
    "get_cluster_entities",
    "add_cluster_entity_associations",
    "add_cluster_tag_associations",
    "entity_overlap_score",
    "jaccard_similarity",
    "event_compatibility_score",
    "normalize_title_for_matching",
    "title_similarity",
    "summary_similarity",
    "is_match",
    "get_time_window_for_event",
    # teams
    "NHL_OPPONENT_TEAMS",
    "extract_game_identifier",
]


@celery.task(name="app.tasks.enrich.enrich_raw_item", bind=True)
def enrich_raw_item(self, raw_item_id: int):
    """
    Process a raw_item into a story_variant.
    Extracts entities, normalizes text, tags, and clusters.

    Args:
        raw_item_id: ID of the raw_item to process
    """
    from app.models import EventType, RawItem, Source, StoryVariant

    db = SessionLocal()
    try:
        # Load raw_item from database
        raw_item = db.query(RawItem).filter(RawItem.id == raw_item_id).first()
        if not raw_item:
            return {"error": "RawItem not found", "raw_item_id": raw_item_id}

        print(f"Enriching raw item {raw_item_id}: {raw_item.raw_title[:50]}...")

        # Load source for tagging and relevance check
        source = db.query(Source).filter(Source.id == raw_item.source_id).first()

        # Step 1: Extract and normalize text
        text = f"{raw_item.raw_title or ''} {raw_item.raw_description or ''}"
        tokens = normalize_tokens(text)

        # Step 2: Extract entities
        entity_ids = extract_entities(db, text)

        # Step 2.5: Check relevance unless source is dedicated to Sharks news
        source_metadata = source.extra_metadata or {}
        if not source_metadata.get('skip_relevance_check'):
            validation_result = validate_sharks_relevance(
                db=db,
                raw_item_id=raw_item_id,
                title=raw_item.raw_title or '',
                description=raw_item.raw_description or '',
                entity_ids=entity_ids
            )

            if not validation_result:
                print(f"  ⊘ Skipped (not Sharks-relevant): {raw_item.raw_title[:50]}...")
                return {
                    "status": "skipped",
                    "reason": "not_sharks_relevant",
                    "raw_item_id": raw_item_id
                }
        else:
            # Log that we skipped validation for dedicated sources
            log_validation(
                db=db,
                raw_item_id=raw_item_id,
                method=ValidationMethod.SKIP,
                result=ValidationResult.APPROVED,
                reason="Source has skip_relevance_check flag",
                entity_ids=entity_ids
            )

        # Step 3: Classify event type and tags (LLM with keyword fallback)
        event_type_str, tag_names, llm_summary = classify_article(
            db, text, entity_ids, raw_item.raw_title or "", raw_item.raw_description or "",
            source, url=raw_item.canonical_url or ""
        )
        event_type_enum = EventType[event_type_str.upper()] if event_type_str.upper() in EventType.__members__ else EventType.OTHER

        # Step 4: Create story_variant
        extra_metadata = {}
        if llm_summary:
            extra_metadata["llm_summary"] = llm_summary

        variant = StoryVariant(
            raw_item_id=raw_item.id,
            source_id=raw_item.source_id,
            title=raw_item.raw_title or "Untitled",
            url=raw_item.canonical_url,
            published_at=raw_item.published_at or utcnow(),
            event_type=event_type_enum,
            tokens=tokens,
            entities=entity_ids,
            extra_metadata=extra_metadata,
        )

        db.add(variant)
        db.flush()

        db.commit()

        # Step 5: Match or create cluster (this also handles entity and tag associations)
        cluster_id = match_or_create_cluster(db, variant, tokens, entity_ids, event_type_str, source, tag_names)

        print(f"  ✓ Created variant {variant.id}, matched to cluster {cluster_id}")

        return {
            "status": "success",
            "raw_item_id": raw_item_id,
            "variant_id": variant.id,
            "cluster_id": cluster_id,
            "entities": entity_ids,
            "event_type": event_type_str
        }

    except Exception as exc:
        print(f"  ✗ Error enriching raw item {raw_item_id}: {exc}")
        db.rollback()
        raise
    finally:
        db.close()
