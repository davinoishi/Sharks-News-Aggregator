"""
BlueSky social media posting service.

Uses the AT Protocol SDK to post new story clusters to BlueSky.
"""
from datetime import datetime
from typing import Optional, Tuple
from dataclasses import dataclass

from app.core.config import settings


@dataclass
class PostResult:
    """Result of a BlueSky post attempt."""
    success: bool
    post_uri: Optional[str]
    post_cid: Optional[str]
    error: Optional[str]


class BlueSkyService:
    """
    Client for BlueSky AT Protocol API.

    Provides synchronous methods for use in Celery tasks.
    """

    def __init__(
        self,
        handle: Optional[str] = None,
        app_password: Optional[str] = None,
    ):
        self.handle = handle or settings.bluesky_handle
        self.app_password = app_password or settings.bluesky_app_password
        self._client = None

    def _get_client(self):
        """Get or create authenticated AT Protocol client."""
        if self._client is None:
            try:
                from atproto import Client
                self._client = Client()
                self._client.login(self.handle, self.app_password)
            except Exception as e:
                raise RuntimeError(f"Failed to authenticate with BlueSky: {e}")
        return self._client

    def health_check(self) -> bool:
        """
        Check if BlueSky service is available and authenticated.

        Returns:
            True if service is responding and authenticated, False otherwise
        """
        if not settings.bluesky_enabled:
            return False

        if not self.handle or not self.app_password:
            return False

        try:
            client = self._get_client()
            # Verify we can access profile
            client.get_profile(self.handle)
            return True
        except Exception:
            self._client = None  # Reset client on failure
            return False

    def create_post(
        self,
        text: str,
        link_url: Optional[str] = None,
        link_title: Optional[str] = None,
        link_description: Optional[str] = None,
    ) -> PostResult:
        """
        Create a post on BlueSky.

        Args:
            text: Post text content (max 300 chars)
            link_url: Optional URL to embed as link card
            link_title: Title for link card
            link_description: Description for link card

        Returns:
            PostResult with success status, post URI/CID, or error message
        """
        try:
            from atproto import Client, client_utils

            client = self._get_client()

            # Build the post with optional link embed
            if link_url:
                # Create link card embed
                embed = {
                    "$type": "app.bsky.embed.external",
                    "external": {
                        "uri": link_url,
                        "title": link_title or "",
                        "description": link_description or "",
                    }
                }

                # Parse text for facets (links, mentions, hashtags)
                text_builder = client_utils.TextBuilder()

                # Split text into parts and handle hashtags
                current_pos = 0
                text_to_process = text

                # Find all hashtags and build text with proper facets
                import re
                hashtag_pattern = r'#(\w+)'

                parts = []
                last_end = 0
                for match in re.finditer(hashtag_pattern, text):
                    if match.start() > last_end:
                        parts.append(('text', text[last_end:match.start()]))
                    parts.append(('tag', match.group(0), match.group(1)))
                    last_end = match.end()
                if last_end < len(text):
                    parts.append(('text', text[last_end:]))

                # Build with facets
                for part in parts:
                    if part[0] == 'text':
                        text_builder.text(part[1])
                    elif part[0] == 'tag':
                        text_builder.tag(part[1], part[2])

                response = client.send_post(
                    text_builder,
                    embed=embed
                )
            else:
                response = client.send_post(text)

            return PostResult(
                success=True,
                post_uri=response.uri,
                post_cid=response.cid,
                error=None
            )

        except Exception as e:
            self._client = None  # Reset client on failure
            return PostResult(
                success=False,
                post_uri=None,
                post_cid=None,
                error=str(e)[:500]
            )


# Module-level convenience functions
_service: Optional[BlueSkyService] = None


def get_service() -> BlueSkyService:
    """Get or create the singleton service instance."""
    global _service
    if _service is None:
        _service = BlueSkyService()
    return _service


def health_check() -> bool:
    """
    Check if BlueSky service is available.

    Module-level convenience function.
    """
    return get_service().health_check()


def create_post(
    text: str,
    link_url: Optional[str] = None,
    link_title: Optional[str] = None,
    link_description: Optional[str] = None,
) -> PostResult:
    """
    Create a post on BlueSky.

    Module-level convenience function.
    """
    return get_service().create_post(text, link_url, link_title, link_description)


def format_cluster_post(
    headline: str,
    event_type: str,
    source_count: int,
    tags: list,
    link_url: str,
) -> str:
    """
    Format a cluster into a BlueSky post text.

    Post format (max 300 chars):
    [Headline - max 180 chars]

    [Event Type] | [N] sources

    #SJSharks #Sharks [#dynamic_tags]

    Args:
        headline: Cluster headline
        event_type: Event type (trade, injury, etc.)
        source_count: Number of sources
        tags: List of tag dicts with 'name' and 'slug'
        link_url: URL to the source article

    Returns:
        Formatted post text
    """
    # Truncate headline if needed (leave room for rest of post)
    max_headline = 180
    if len(headline) > max_headline:
        headline = headline[:max_headline - 3] + "..."

    # Format event type for display
    event_display = event_type.replace("_", " ").title()

    # Build source info line
    source_text = f"1 source" if source_count == 1 else f"{source_count} sources"
    info_line = f"{event_display} | {source_text}"

    # Build hashtags - always include base tags
    hashtags = ["#SJSharks", "#Sharks"]

    # Add dynamic tags from cluster (convert to hashtag format)
    for tag in tags[:3]:  # Limit to 3 additional tags
        tag_name = tag.get("name", "").replace(" ", "").replace("-", "")
        if tag_name and len(tag_name) <= 20:
            hashtags.append(f"#{tag_name}")

    hashtag_line = " ".join(hashtags)

    # Assemble post
    post_text = f"{headline}\n\n{info_line}\n\n{hashtag_line}"

    # Final length check (300 char limit)
    if len(post_text) > 300:
        # Reduce headline further
        overflow = len(post_text) - 300
        new_max = max_headline - overflow - 3
        headline = headline[:new_max] + "..."
        post_text = f"{headline}\n\n{info_line}\n\n{hashtag_line}"

    return post_text
