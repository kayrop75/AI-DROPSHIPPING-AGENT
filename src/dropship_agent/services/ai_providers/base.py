"""
Abstract AI provider interface.

Every provider adapter must implement this interface.
ProductContentGenerator depends only on AIProvider — never on a specific
provider class.  This keeps the service testable with MockProvider and
makes future provider changes (Anthropic, Gemini, local LLM) a one-file
addition without touching any other module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AIProvider(ABC):
    """
    Interface that every AI provider adapter must implement.

    Rules
    -----
    - complete() must return a non-empty string on success.
    - complete() must raise AIProviderError (from models.content) on any
      failure: network error, authentication failure, timeout, rate limit,
      or empty / malformed response.
    - Providers must never log or expose API keys.
    - Providers must never make calls during unit tests.  Use MockProvider
      in tests; real providers are injected at runtime.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Human-readable identifier for this provider.
        Examples: "mock", "openai-gpt-4o-mini".
        Used in GeneratedContentItem.provider_used for provenance.
        """

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        """
        Send a text prompt and return the model's response.

        Parameters
        ----------
        prompt      : The full prompt string.
        max_tokens  : Approximate upper bound on response length.

        Returns
        -------
        A non-empty string containing the model's response.

        Raises
        ------
        AIProviderError
            On any failure: network, auth, timeout, rate limit, or when
            the response is empty or cannot be parsed.
        """
