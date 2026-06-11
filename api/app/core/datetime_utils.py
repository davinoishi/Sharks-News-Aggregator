"""Timezone-aware datetime helpers (brief 07, C2).

The codebase historically used the naive ``datetime.utcnow()`` (deprecated in
3.12) together with scattered ``.replace(tzinfo=None)`` patches to reconcile it
with the ``TIMESTAMPTZ`` columns Postgres hands back as aware datetimes. Both
the model columns (``DateTime(timezone=True)``) and the SQL schema are already
timezone-aware, so the fix is to make the *Python* side aware everywhere too.

Use :func:`utcnow` instead of ``datetime.utcnow()`` and
:func:`ensure_aware` to coerce any datetime of unknown provenance (e.g. parsed
out of an RSS feed) to aware UTC before comparing it with another aware value.
"""
from datetime import datetime, timezone
from typing import Optional


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""
    return datetime.now(timezone.utc)


def ensure_aware(value: Optional[datetime]) -> Optional[datetime]:
    """Return ``value`` as an aware UTC datetime (assume UTC if naive).

    ``None`` passes through unchanged. Naive datetimes are interpreted as UTC,
    which matches how this project has always stored timestamps.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
