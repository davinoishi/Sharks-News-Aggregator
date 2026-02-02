"""
Ollama LLM service for relevance checking.

Uses the Hailo-Ollama server on Pi5-AI2 to validate article relevance.
Falls back to keyword-based validation if Ollama is unavailable.
"""
import re
import time
from typing import Tuple, Optional
from dataclasses import dataclass

import httpx

from app.core.config import settings


RELEVANCE_PROMPT = """You are a relevance filter for a San Jose Sharks news aggregator.

## Task
Determine if the article is PRIMARILY about the San Jose Sharks, their players, coaches, or organization.

## Examples

APPROVE (YES):
- "Sharks trade Hertl to Vegas for picks" - directly about team moves
- "Macklin Celebrini scores hat trick in win" - Sharks player performance
- "Ryan Warsofsky addresses lineup changes" - coach discussing team

REJECT (NO):
- "NHL Power Rankings: Where all 32 teams stand" - Sharks only mentioned briefly
- "Oilers defeat Canucks 4-2" - Sharks not involved
- "Kings preview: Facing Sharks on Thursday" - opponent's perspective

## Instructions
1. First, explain in ONE sentence why this is or isn't primarily about the Sharks
2. Then respond with your decision and confidence

Format your response EXACTLY as:
REASON: <one sentence explanation>
DECISION: <YES or NO>
CONFIDENCE: <HIGH, MEDIUM, or LOW>

Title: {title}
Description: {description}

Response:"""


@dataclass
class RelevanceResult:
    """Result of a relevance check."""
    is_relevant: bool
    response: Optional[str]  # Raw LLM response
    confidence: Optional[str]  # HIGH, MEDIUM, LOW
    reason: Optional[str]  # Chain-of-thought explanation
    error: Optional[str]
    latency_ms: int


class OllamaService:
    """
    Client for Ollama LLM API.

    Provides synchronous methods for use in Celery tasks.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.ollama_model
        self.timeout = timeout or settings.ollama_timeout_seconds

    def health_check(self) -> bool:
        """
        Check if Ollama service is available.

        Returns:
            True if service is responding, False otherwise
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    def check_relevance(
        self,
        title: str,
        description: Optional[str] = None
    ) -> RelevanceResult:
        """
        Check if an article is relevant to San Jose Sharks.

        Args:
            title: Article title
            description: Article description (optional)

        Returns:
            RelevanceResult with is_relevant bool, raw response, and any error
        """
        start_time = time.time()

        prompt = RELEVANCE_PROMPT.format(
            title=title or "",
            description=description or "(no description)"
        )

        try:
            with httpx.Client(timeout=float(self.timeout)) as client:
                response = client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,  # Low temp for consistent output
                            "num_predict": 100,  # Need room for REASON/DECISION/CONFIDENCE
                        }
                    }
                )

                latency_ms = int((time.time() - start_time) * 1000)

                if response.status_code != 200:
                    return RelevanceResult(
                        is_relevant=True,  # Default to accepting on error
                        response=None,
                        confidence=None,
                        reason=None,
                        error=f"HTTP {response.status_code}: {response.text[:200]}",
                        latency_ms=latency_ms
                    )

                result = response.json()
                llm_response = result.get("response", "").strip()

                # Parse structured response (REASON/DECISION/CONFIDENCE)
                is_relevant, confidence, reason = self._parse_structured_response(llm_response)

                if is_relevant is None:
                    # Fallback: try simple YES/NO detection
                    response_upper = llm_response.upper()
                    if "YES" in response_upper:
                        is_relevant = True
                    elif "NO" in response_upper:
                        is_relevant = False
                    else:
                        # Ambiguous response - treat as error, but accept article
                        return RelevanceResult(
                            is_relevant=True,
                            response=llm_response[:100],
                            confidence=None,
                            reason=None,
                            error=f"Ambiguous LLM response: {llm_response[:50]}",
                            latency_ms=latency_ms
                        )

                return RelevanceResult(
                    is_relevant=is_relevant,
                    response=llm_response[:100],
                    confidence=confidence,
                    reason=reason,
                    error=None,
                    latency_ms=latency_ms
                )

        except httpx.TimeoutException:
            latency_ms = int((time.time() - start_time) * 1000)
            return RelevanceResult(
                is_relevant=True,  # Accept on timeout
                response=None,
                confidence=None,
                reason=None,
                error=f"Timeout after {self.timeout}s",
                latency_ms=latency_ms
            )
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return RelevanceResult(
                is_relevant=True,  # Accept on error
                response=None,
                confidence=None,
                reason=None,
                error=str(e)[:200],
                latency_ms=latency_ms
            )

    def _parse_structured_response(self, response: str) -> Tuple[Optional[bool], Optional[str], Optional[str]]:
        """
        Parse the structured LLM response format.

        Expected format:
        REASON: <one sentence explanation>
        DECISION: <YES or NO>
        CONFIDENCE: <HIGH, MEDIUM, or LOW>

        Returns:
            Tuple of (is_relevant, confidence, reason) - any can be None if parsing fails
        """
        is_relevant = None
        confidence = None
        reason = None

        # Extract REASON
        reason_match = re.search(r'REASON:\s*(.+?)(?:\n|DECISION:|$)', response, re.IGNORECASE | re.DOTALL)
        if reason_match:
            reason = reason_match.group(1).strip()[:500]  # Limit length

        # Extract DECISION
        decision_match = re.search(r'DECISION:\s*(YES|NO)', response, re.IGNORECASE)
        if decision_match:
            is_relevant = decision_match.group(1).upper() == "YES"

        # Extract CONFIDENCE
        confidence_match = re.search(r'CONFIDENCE:\s*(HIGH|MEDIUM|LOW)', response, re.IGNORECASE)
        if confidence_match:
            confidence = confidence_match.group(1).upper()

        return is_relevant, confidence, reason


# Module-level convenience functions
_service: Optional[OllamaService] = None


def get_service() -> OllamaService:
    """Get or create the singleton service instance."""
    global _service
    if _service is None:
        _service = OllamaService()
    return _service


def check_relevance(title: str, description: Optional[str] = None) -> RelevanceResult:
    """
    Check article relevance using LLM.

    Module-level convenience function.
    """
    return get_service().check_relevance(title, description)


def health_check() -> bool:
    """
    Check if Ollama service is available.

    Module-level convenience function.
    """
    return get_service().health_check()
