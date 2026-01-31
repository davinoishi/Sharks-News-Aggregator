"""
BlueSky posting tasks for Celery.

Handles scheduled posting of new clusters and retrying failed posts.
"""
from datetime import datetime, timedelta

from app.tasks.celery_app import celery
from app.core.database import SessionLocal
from app.core.config import settings


@celery.task(name="app.tasks.bluesky.post_new_clusters")
def post_new_clusters():
    """
    Post new clusters to BlueSky.

    Runs every 15 minutes via Celery Beat.
    Finds clusters that haven't been posted yet and posts them.

    Filters:
    - source_count >= bluesky_min_sources (default 1)
    - event_type != 'opinion'
    - Not already posted
    - 5-minute minimum between posts to avoid spam
    """
    if not settings.bluesky_enabled:
        return {"status": "disabled", "message": "BlueSky posting is disabled"}

    from app.models import Cluster, ClusterStatus, EventType
    from app.models.bluesky_post import BlueSkyPost, PostStatus
    from app.services.bluesky import get_service, format_cluster_post
    from app.core.queries import get_cluster_variants_sorted

    db = SessionLocal()
    try:
        # Check last post time (5-minute minimum between posts)
        last_post = db.query(BlueSkyPost).filter(
            BlueSkyPost.status == PostStatus.POSTED
        ).order_by(BlueSkyPost.posted_at.desc()).first()

        if last_post and last_post.posted_at:
            time_since_last = datetime.utcnow() - last_post.posted_at.replace(tzinfo=None)
            if time_since_last < timedelta(minutes=5):
                return {
                    "status": "rate_limited",
                    "message": f"Last post was {time_since_last.seconds}s ago, waiting for 5-minute cooldown"
                }

        # Find clusters eligible for posting
        # Get cluster IDs that already have BlueSky posts
        posted_cluster_ids = db.query(BlueSkyPost.cluster_id).all()
        posted_cluster_ids = [p[0] for p in posted_cluster_ids]

        # Query for eligible clusters
        eligible_clusters = db.query(Cluster).filter(
            Cluster.status == ClusterStatus.ACTIVE,
            Cluster.source_count >= settings.bluesky_min_sources,
            Cluster.event_type != EventType.OPINION,
            ~Cluster.id.in_(posted_cluster_ids) if posted_cluster_ids else True
        ).order_by(Cluster.first_seen_at.asc()).limit(5).all()

        if not eligible_clusters:
            return {"status": "no_clusters", "message": "No new clusters to post"}

        # Get BlueSky service
        service = get_service()
        if not service.health_check():
            return {"status": "error", "message": "BlueSky service is not available"}

        posted_count = 0
        results = []

        for cluster in eligible_clusters:
            # Get best source URL (prefer official, then press)
            variants = get_cluster_variants_sorted(db, cluster.id)
            if not variants:
                # Skip cluster with no variants
                skip_record = BlueSkyPost(
                    cluster_id=cluster.id,
                    status=PostStatus.SKIPPED,
                    error_message="No variants found"
                )
                db.add(skip_record)
                db.commit()
                continue

            best_variant = variants[0]
            link_url = best_variant.url

            # Get cluster tags
            tags = [
                {"name": ct.tag.name, "slug": ct.tag.slug}
                for ct in cluster.cluster_tags
            ]

            # Format post text
            post_text = format_cluster_post(
                headline=cluster.headline,
                event_type=cluster.event_type.value,
                source_count=cluster.source_count,
                tags=tags,
                link_url=link_url
            )

            # Create post
            result = service.create_post(
                text=post_text,
                link_url=link_url,
                link_title=best_variant.title or cluster.headline,
                link_description=""
            )

            # Create record
            post_record = BlueSkyPost(
                cluster_id=cluster.id,
                post_text=post_text,
                status=PostStatus.POSTED if result.success else PostStatus.FAILED,
                post_uri=result.post_uri,
                post_cid=result.post_cid,
                error_message=result.error,
                posted_at=datetime.utcnow() if result.success else None
            )
            db.add(post_record)
            db.commit()

            if result.success:
                posted_count += 1
                results.append({
                    "cluster_id": cluster.id,
                    "headline": cluster.headline[:50],
                    "status": "posted",
                    "post_uri": result.post_uri
                })
                # Only post one at a time to respect rate limits
                break
            else:
                results.append({
                    "cluster_id": cluster.id,
                    "headline": cluster.headline[:50],
                    "status": "failed",
                    "error": result.error
                })

        return {
            "status": "success",
            "posted_count": posted_count,
            "results": results
        }

    except Exception as e:
        return {"status": "error", "message": str(e)[:500]}
    finally:
        db.close()


@celery.task(name="app.tasks.bluesky.retry_failed_posts")
def retry_failed_posts():
    """
    Retry failed BlueSky posts.

    Runs every hour via Celery Beat.
    Retries posts that failed with retry_count < 3.
    """
    if not settings.bluesky_enabled:
        return {"status": "disabled", "message": "BlueSky posting is disabled"}

    from app.models import Cluster
    from app.models.bluesky_post import BlueSkyPost, PostStatus
    from app.services.bluesky import get_service, format_cluster_post
    from app.core.queries import get_cluster_variants_sorted

    db = SessionLocal()
    try:
        # Get BlueSky service
        service = get_service()
        if not service.health_check():
            return {"status": "error", "message": "BlueSky service is not available"}

        # Find failed posts eligible for retry
        failed_posts = db.query(BlueSkyPost).filter(
            BlueSkyPost.status == PostStatus.FAILED,
            BlueSkyPost.retry_count < 3
        ).order_by(BlueSkyPost.created_at.asc()).limit(5).all()

        if not failed_posts:
            return {"status": "no_retries", "message": "No failed posts to retry"}

        retried_count = 0
        results = []

        for post_record in failed_posts:
            cluster = db.query(Cluster).filter(Cluster.id == post_record.cluster_id).first()
            if not cluster:
                post_record.status = PostStatus.SKIPPED
                post_record.error_message = "Cluster not found"
                db.commit()
                continue

            # Get best source URL
            variants = get_cluster_variants_sorted(db, cluster.id)
            if not variants:
                post_record.status = PostStatus.SKIPPED
                post_record.error_message = "No variants found"
                db.commit()
                continue

            best_variant = variants[0]
            link_url = best_variant.url

            # Get cluster tags
            tags = [
                {"name": ct.tag.name, "slug": ct.tag.slug}
                for ct in cluster.cluster_tags
            ]

            # Format post text
            post_text = format_cluster_post(
                headline=cluster.headline,
                event_type=cluster.event_type.value,
                source_count=cluster.source_count,
                tags=tags,
                link_url=link_url
            )

            # Retry post
            result = service.create_post(
                text=post_text,
                link_url=link_url,
                link_title=best_variant.title or cluster.headline,
                link_description=""
            )

            # Update record
            post_record.retry_count += 1
            post_record.post_text = post_text
            post_record.updated_at = datetime.utcnow()

            if result.success:
                post_record.status = PostStatus.POSTED
                post_record.post_uri = result.post_uri
                post_record.post_cid = result.post_cid
                post_record.posted_at = datetime.utcnow()
                post_record.error_message = None
                retried_count += 1
                results.append({
                    "cluster_id": cluster.id,
                    "headline": cluster.headline[:50],
                    "status": "posted",
                    "retry_count": post_record.retry_count
                })
            else:
                post_record.error_message = result.error
                results.append({
                    "cluster_id": cluster.id,
                    "headline": cluster.headline[:50],
                    "status": "failed",
                    "retry_count": post_record.retry_count,
                    "error": result.error
                })

            db.commit()

        return {
            "status": "success",
            "retried_count": retried_count,
            "results": results
        }

    except Exception as e:
        return {"status": "error", "message": str(e)[:500]}
    finally:
        db.close()


@celery.task(name="app.tasks.bluesky.post_cluster")
def post_cluster(cluster_id: int):
    """
    Manually post a specific cluster to BlueSky.

    Args:
        cluster_id: ID of the cluster to post

    Returns:
        Result dict with status and details
    """
    if not settings.bluesky_enabled:
        return {"status": "disabled", "message": "BlueSky posting is disabled"}

    from app.models import Cluster, ClusterStatus
    from app.models.bluesky_post import BlueSkyPost, PostStatus
    from app.services.bluesky import get_service, format_cluster_post
    from app.core.queries import get_cluster_variants_sorted

    db = SessionLocal()
    try:
        # Check if already posted
        existing_post = db.query(BlueSkyPost).filter(
            BlueSkyPost.cluster_id == cluster_id
        ).first()

        if existing_post and existing_post.status == PostStatus.POSTED:
            return {
                "status": "already_posted",
                "post_uri": existing_post.post_uri,
                "posted_at": existing_post.posted_at.isoformat() if existing_post.posted_at else None
            }

        # Get cluster
        cluster = db.query(Cluster).filter(
            Cluster.id == cluster_id,
            Cluster.status == ClusterStatus.ACTIVE
        ).first()

        if not cluster:
            return {"status": "error", "message": "Cluster not found"}

        # Get BlueSky service
        service = get_service()
        if not service.health_check():
            return {"status": "error", "message": "BlueSky service is not available"}

        # Get best source URL
        variants = get_cluster_variants_sorted(db, cluster.id)
        if not variants:
            return {"status": "error", "message": "No variants found for cluster"}

        best_variant = variants[0]
        link_url = best_variant.url

        # Get cluster tags
        tags = [
            {"name": ct.tag.name, "slug": ct.tag.slug}
            for ct in cluster.cluster_tags
        ]

        # Format post text
        post_text = format_cluster_post(
            headline=cluster.headline,
            event_type=cluster.event_type.value,
            source_count=cluster.source_count,
            tags=tags,
            link_url=link_url
        )

        # Create post
        result = service.create_post(
            text=post_text,
            link_url=link_url,
            link_title=best_variant.title or cluster.headline,
            link_description=""
        )

        # Create or update record
        if existing_post:
            existing_post.post_text = post_text
            existing_post.status = PostStatus.POSTED if result.success else PostStatus.FAILED
            existing_post.post_uri = result.post_uri
            existing_post.post_cid = result.post_cid
            existing_post.error_message = result.error
            existing_post.retry_count += 1
            existing_post.posted_at = datetime.utcnow() if result.success else None
            existing_post.updated_at = datetime.utcnow()
        else:
            post_record = BlueSkyPost(
                cluster_id=cluster.id,
                post_text=post_text,
                status=PostStatus.POSTED if result.success else PostStatus.FAILED,
                post_uri=result.post_uri,
                post_cid=result.post_cid,
                error_message=result.error,
                posted_at=datetime.utcnow() if result.success else None
            )
            db.add(post_record)

        db.commit()

        if result.success:
            return {
                "status": "posted",
                "cluster_id": cluster.id,
                "headline": cluster.headline,
                "post_uri": result.post_uri,
                "post_text": post_text
            }
        else:
            return {
                "status": "failed",
                "cluster_id": cluster.id,
                "error": result.error
            }

    except Exception as e:
        return {"status": "error", "message": str(e)[:500]}
    finally:
        db.close()
