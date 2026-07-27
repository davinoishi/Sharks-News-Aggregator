"""flag search-snippet aggregator sources as description_unreliable

Revision ID: 0004_description_unreliable
Revises: 0003_source_status_unsupported
Create Date: 2026-07-26

Google Alerts items carry the *page's* chrome in the description rather than the
article: nav bars, "Trending" sidebars, unrelated headlines, with the alert query
bolded wherever it appears on the page. An item titled "Edmonton police to
introduce involuntary detention detox" arrived with the description "... San Jose
Sharks won Darnell Nurse trade. Trending ... News · Sports · Opinion ...". That
was enough to extract Darnell Nurse as an entity, clear the relevance gate on
that entity alone, summarize as "Speculation regarding Darnell Nurse trade
implications", and cluster the item with two genuine Nurse stories.

``enrich_raw_item`` now drops the description for sources carrying the
``description_unreliable`` metadata flag. This migration sets that flag on the
existing Google Alerts sources so the fix applies without a manual UPDATE.

Deliberately narrow: only search-alert aggregators are matched. Bluesky mirror
sources must NOT get this flag — their items have no <title>, so the title is
derived *from* the description and dropping it would blind them entirely.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_description_unreliable"
down_revision: Union[str, None] = "0003_source_status_unsupported"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in sync with the metadata key read in app/tasks/enrich.py.
_FLAG = "description_unreliable"

# Matches "Google Alerts - Sharks News" and any sibling alert feed, plus the
# google.com/alerts/feeds/... URL form in case a row is renamed.
_MATCH = """
    (name ILIKE '%%google alert%%' OR COALESCE(feed_url, '') ILIKE '%%google.com/alerts%%')
"""


def upgrade() -> None:
    # sources.metadata is `json`, not `jsonb`: merge through a jsonb round trip
    # and cast back explicitly, since there is no assignment cast either way.
    #
    # Cast the COLUMN, not the COALESCE result. `COALESCE(metadata, '{}'::json)
    # ::jsonb` fails with "COALESCE could not convert type json to jsonb" —
    # Postgres resolves the COALESCE branches before applying the outer cast and
    # won't use the I/O-conversion cast there. Casting each operand sidesteps it.
    #
    # `||` is a merge, so unrelated keys on the row (skip_relevance_check) survive.
    op.execute(
        f"""
        UPDATE sources
        SET metadata = (
            COALESCE(metadata::jsonb, '{{}}'::jsonb) || '{{"{_FLAG}": true}}'::jsonb
        )::json
        WHERE {_MATCH}
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE sources
        SET metadata = (COALESCE(metadata::jsonb, '{{}}'::jsonb) - '{_FLAG}')::json
        WHERE {_MATCH}
        """
    )
