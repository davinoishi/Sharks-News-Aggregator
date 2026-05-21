"""
OpenRouter LLM service for article relevance, tagging, and clustering.

Uses Google Gemma 4 via OpenRouter's OpenAI-compatible API.
Falls back to keyword-based logic if the API is unavailable.
"""
import json
import re
import time
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

import httpx

from app.core.config import settings


RELEVANCE_PROMPT_SYSTEM = (
    "You are a relevance filter for a San Jose Sharks NHL news aggregator. "
    "Respond with valid JSON only."
)

RELEVANCE_PROMPT_USER = """Determine if this article is relevant to San Jose Sharks fans.

APPROVE if the article is about ANY of these:
- The San Jose Sharks or San Jose Barracuda (AHL affiliate)
- Any current or former Sharks/Barracuda player, prospect, or draft pick
- Sharks coaches, staff, or front office
- Games involving the Sharks or Barracuda
- Trades, signings, or rumors involving Sharks-affiliated people
- Articles where a Sharks-affiliated person is a main subject, even if the article is about another team or event (e.g., a Sharks player at an international tournament)

REJECT only if the Sharks and their people have NO meaningful connection to the article.

{entities_context}Title: {title}
Description: {description}

Respond as JSON: {{"relevant": true, "confidence": "HIGH", "reason": "one sentence"}}"""

CLASSIFY_PROMPT_SYSTEM = (
    "You are a classifier for a San Jose Sharks NHL news aggregator. "
    "Respond with valid JSON only."
)

CLASSIFY_PROMPT_USER = """Classify this Sharks article and provide a brief summary for clustering.

Tags (assign ALL that apply):
- Trade: trades, acquisitions, deals between teams
- Injury: injuries, injured reserve, day-to-day status
- Lineup: line changes, scratches, starting goalies
- Recall: AHL call-ups, demotions between Sharks and Barracuda
- Waiver: waiver claims, waiver wire moves
- Signing: contract signings, extensions, agree to terms
- Prospect: draft picks, development camps, junior leagues
- Game: game recaps, scores, results, previews, goals
- Barracuda: San Jose Barracuda AHL affiliate content
- Rumors: trade rumors, speculation from credible sources
- Opinion: analysis, editorial, opinion pieces

Event type (pick exactly ONE primary): trade, injury, lineup, recall, waiver, signing, prospect, game, opinion, other

Title: {title}
Description: {description}
Entities mentioned: {entity_names}

Respond as JSON: {{"tags": ["Tag1", "Tag2"], "event_type": "game", "summary": "5-10 word factual topic using key nouns (e.g. 'Celebrini contract extension analysis')", "confidence": "HIGH"}}"""


@dataclass
class RelevanceResult:
    is_relevant: bool
    response: Optional[str]
    confidence: Optional[str]
    reason: Optional[str]
    error: Optional[str]
    latency_ms: int


@dataclass
class ClassificationResult:
    tags: List[str] = field(default_factory=list)
    event_type: str = "other"
    summary: Optional[str] = None
    confidence: Optional[str] = None
    reason: Optional[str] = None
    error: Optional[str] = None
    latency_ms: int = 0


class OpenRouterService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.api_key = api_key or settings.openrouter_api_key
        self.model = model or settings.openrouter_model
        self.base_url = base_url or settings.openrouter_base_url
        self.timeout = timeout or settings.openrouter_timeout_seconds

    def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False

    def _call_chat(
        self,
        messages: list,
        max_tokens: int = 120,
        temperature: float = 0.1,
    ) -> Tuple[Optional[dict], Optional[str]]:
        if not self.api_key:
            return None, "OPENROUTER_API_KEY not configured"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://sharks-news.app",
            "X-Title": "Sharks News Aggregator",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        for attempt in range(2):
            try:
                with httpx.Client(timeout=float(self.timeout)) as client:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )

                if resp.status_code == 429:
                    try:
                        retry_after = min(int(resp.headers.get("Retry-After", "5")), 30)
                    except (ValueError, TypeError):
                        retry_after = 5
                    if attempt == 0:
                        time.sleep(retry_after)
                        continue
                    return None, f"Rate limited (429) after retry"

                if resp.status_code >= 500:
                    if attempt == 0:
                        time.sleep(2)
                        continue
                    return None, f"Server error ({resp.status_code}) after retry"

                if resp.status_code != 200:
                    return None, f"HTTP {resp.status_code}: {resp.text[:200]}"

                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                return self._parse_json_content(content)

            except httpx.TimeoutException:
                return None, f"Timeout after {self.timeout}s"
            except (KeyError, IndexError) as e:
                return None, f"Unexpected response structure: {e}"
            except Exception as e:
                return None, str(e)[:200]

        return None, "Max retries exceeded"

    def _parse_json_content(self, content: str) -> Tuple[Optional[dict], Optional[str]]:
        # Try direct JSON parse
        try:
            return json.loads(content), None
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code blocks
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1)), None
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0)), None
            except json.JSONDecodeError:
                pass

        return None, f"Could not parse JSON from response: {content[:100]}"

    def check_relevance(
        self, title: str, description: Optional[str] = None,
        entity_names: Optional[str] = None,
    ) -> RelevanceResult:
        start_time = time.time()

        if entity_names:
            entities_context = (
                f"The following Sharks-affiliated people were detected in this article: {entity_names}\n\n"
            )
        else:
            entities_context = ""

        messages = [
            {"role": "system", "content": RELEVANCE_PROMPT_SYSTEM},
            {
                "role": "user",
                "content": RELEVANCE_PROMPT_USER.format(
                    title=title or "",
                    description=description or "(no description)",
                    entities_context=entities_context,
                ),
            },
        ]

        parsed, error = self._call_chat(messages, max_tokens=80, temperature=0.1)
        latency_ms = int((time.time() - start_time) * 1000)

        if error:
            return RelevanceResult(
                is_relevant=True, response=None, confidence=None,
                reason=None, error=error, latency_ms=latency_ms,
            )

        is_relevant = parsed.get("relevant", True)
        if isinstance(is_relevant, str):
            is_relevant = is_relevant.lower() in ("true", "yes")

        return RelevanceResult(
            is_relevant=bool(is_relevant),
            response=json.dumps(parsed)[:100],
            confidence=parsed.get("confidence"),
            reason=parsed.get("reason"),
            error=None,
            latency_ms=latency_ms,
        )

    def classify_and_summarize(
        self,
        title: str,
        description: Optional[str] = None,
        entity_names: Optional[str] = None,
    ) -> ClassificationResult:
        start_time = time.time()
        messages = [
            {"role": "system", "content": CLASSIFY_PROMPT_SYSTEM},
            {
                "role": "user",
                "content": CLASSIFY_PROMPT_USER.format(
                    title=title or "",
                    description=description or "(no description)",
                    entity_names=entity_names or "(none detected)",
                ),
            },
        ]

        parsed, error = self._call_chat(messages, max_tokens=150, temperature=0.2)
        latency_ms = int((time.time() - start_time) * 1000)

        if error:
            return ClassificationResult(error=error, latency_ms=latency_ms)

        valid_tags = {
            "Trade", "Injury", "Lineup", "Recall", "Waiver",
            "Signing", "Prospect", "Game", "Barracuda", "Rumors", "Opinion",
        }
        valid_events = {
            "trade", "injury", "lineup", "recall", "waiver",
            "signing", "prospect", "game", "opinion", "other",
        }

        raw_tags = parsed.get("tags", [])
        if isinstance(raw_tags, list):
            tags = [t for t in raw_tags if t in valid_tags]
        else:
            tags = []

        event_type = parsed.get("event_type", "other")
        if event_type not in valid_events:
            event_type = "other"

        summary = parsed.get("summary")
        if isinstance(summary, str):
            summary = summary[:100]

        return ClassificationResult(
            tags=tags,
            event_type=event_type,
            summary=summary,
            confidence=parsed.get("confidence"),
            error=None,
            latency_ms=latency_ms,
        )


# Module-level convenience functions
_service: Optional[OpenRouterService] = None


def get_service() -> OpenRouterService:
    global _service
    if _service is None:
        _service = OpenRouterService()
    return _service


def check_relevance(title: str, description: Optional[str] = None, entity_names: Optional[str] = None) -> RelevanceResult:
    return get_service().check_relevance(title, description, entity_names)


def classify_and_summarize(
    title: str,
    description: Optional[str] = None,
    entity_names: Optional[str] = None,
) -> ClassificationResult:
    return get_service().classify_and_summarize(title, description, entity_names)


def health_check() -> bool:
    return get_service().health_check()
