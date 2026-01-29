"""
Ollama LLM service for relevance checking.

Uses the Hailo-Ollama server on Pi5-AI2 to validate article relevance.
Falls back to keyword-based validation if Ollama is unavailable.
"""
import time
from typing import Tuple, Optional
from dataclasses import dataclass

import httpx

from app.core.config import settings


RELEVANCE_PROMPT = """You are a relevance filter for a San Jose Sharks news aggregator. Given an article title and description, respond with YES if the article is primarily about the San Jose Sharks, their players, staff, or organization. Respond NO if the Sharks are only mentioned in passing (e.g., as an upcoming opponent, in a league standings table, or in a general NHL roundup). Respond with only YES or NO.

Title: {title}
Description: {description}

Response:"""


@dataclass
class RelevanceResult:
    """Result of a relevance check."""
    is_relevant: bool
    response: Optional[str]  # Raw LLM response (YES/NO)
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
                            "temperature": 0.1,  # Low temp for consistent yes/no
                            "num_predict": 10,   # Only need YES or NO
                        }
                    }
                )

                latency_ms = int((time.time() - start_time) * 1000)

                if response.status_code != 200:
                    return RelevanceResult(
                        is_relevant=True,  # Default to accepting on error
                        response=None,
                        error=f"HTTP {response.status_code}: {response.text[:200]}",
                        latency_ms=latency_ms
                    )

                result = response.json()
                llm_response = result.get("response", "").strip().upper()

                # Parse YES/NO response
                if llm_response.startswith("YES"):
                    is_relevant = True
                elif llm_response.startswith("NO"):
                    is_relevant = False
                else:
                    # Ambiguous response - treat as error, but accept article
                    return RelevanceResult(
                        is_relevant=True,
                        response=llm_response[:50],
                        error=f"Ambiguous LLM response: {llm_response[:50]}",
                        latency_ms=latency_ms
                    )

                return RelevanceResult(
                    is_relevant=is_relevant,
                    response=llm_response[:10],  # Store just YES/NO
                    error=None,
                    latency_ms=latency_ms
                )

        except httpx.TimeoutException:
            latency_ms = int((time.time() - start_time) * 1000)
            return RelevanceResult(
                is_relevant=True,  # Accept on timeout
                response=None,
                error=f"Timeout after {self.timeout}s",
                latency_ms=latency_ms
            )
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return RelevanceResult(
                is_relevant=True,  # Accept on error
                response=None,
                error=str(e)[:200],
                latency_ms=latency_ms
            )


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
