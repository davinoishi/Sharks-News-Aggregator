"""Shared, import-cycle-free constants.

Kept in ``app.core`` so both the task layer (``app.tasks.submissions``) and the
core helpers (``db_utils``, ``health_checks``) can reference the same identity
without importing each other.
"""

# Stable identity of the synthetic source that owns user-submitted links.
#
# User submissions need a real ``sources`` row to satisfy the
# ``raw_items.source_id`` foreign key, but it is NOT a fetchable feed: it uses
# the API ingest method (a no-op stub). It must therefore be excluded from the
# scheduled ingest rotation (otherwise the stub keeps bumping its
# ``fetch_error_count``) and from the pipeline-health "broken source" check.
USER_SUBMISSION_SOURCE_NAME = "User Submissions"
USER_SUBMISSION_SOURCE_URL = "https://submissions.internal/"
