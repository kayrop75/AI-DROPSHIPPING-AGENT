"""
OpenAI provider adapter.

Uses the OpenAI Chat Completions API via the `requests` package (already a
project dependency).  Does NOT use the `openai` SDK — this keeps the
dependency footprint minimal.

Authentication
--------------
The API key is loaded from the OPENAI_API_KEY environment variable (or from
the project's .env file via python-dotenv).  The key is NEVER hardcoded,
logged, printed or included in any exception message.

If OPENAI_API_KEY is not set, the constructor raises AIProviderError
immediately — before any network call — so callers can fall back to
MockProvider or report the problem clearly.

Usage
-----
    from src.dropship_agent.services.ai_providers import OpenAIProvider
    from src.dropship_agent.services.content_generator import ProductContentGenerator

    provider   = OpenAIProvider()          # raises if no key
    generator  = ProductContentGenerator(provider=provider)

This provider is NOT used in unit tests.  All tests use MockProvider.
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass   # python-dotenv optional at import time; key may still be in env

from ...models.content import AIProviderError
from .base import AIProvider

_OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
_DEFAULT_MODEL  = "gpt-4o-mini"
_REQUEST_TIMEOUT_SECONDS = 30


class OpenAIProvider(AIProvider):
    """
    Adapter for the OpenAI Chat Completions API.

    Parameters
    ----------
    model : str
        OpenAI model identifier.  Defaults to "gpt-4o-mini".
    api_key : str, optional
        Override the environment variable.  Should only be used in
        controlled contexts — never hardcode a key in source files.

    Raises
    ------
    AIProviderError
        At construction time if no API key is available.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        api_key: Optional[str] = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self._api_key:
            raise AIProviderError(
                "OPENAI_API_KEY is not set.  "
                "Add it to your environment or .env file.  "
                "Use MockProvider for offline development and testing."
            )

    @property
    def name(self) -> str:
        return f"openai-{self._model}"

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        """
        Send a prompt to the Chat Completions API and return the response text.

        Raises AIProviderError on network failure, authentication error,
        rate limit, timeout, or malformed / empty response.
        The API key is never included in exception messages.
        """
        try:
            import requests as _requests
        except ImportError as exc:
            raise AIProviderError(
                "The 'requests' package is required for OpenAIProvider."
            ) from exc

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }

        try:
            response = _requests.post(
                _OPENAI_API_URL,
                headers=headers,
                json=payload,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except _requests.exceptions.Timeout:
            raise AIProviderError(
                f"OpenAI API request timed out after {_REQUEST_TIMEOUT_SECONDS}s."
            )
        except _requests.exceptions.ConnectionError as exc:
            raise AIProviderError(
                f"Could not connect to the OpenAI API: {exc}"
            )
        except Exception as exc:
            raise AIProviderError(
                f"Unexpected error calling OpenAI API: {type(exc).__name__}"
            )

        if response.status_code == 401:
            raise AIProviderError(
                "OpenAI API authentication failed.  "
                "Check that OPENAI_API_KEY is valid.  "
                "(Key not shown for security.)"
            )
        if response.status_code == 429:
            raise AIProviderError(
                "OpenAI API rate limit exceeded.  "
                "Wait before retrying or upgrade your usage tier."
            )
        if response.status_code != 200:
            raise AIProviderError(
                f"OpenAI API returned HTTP {response.status_code}.  "
                "Check API status or try again later."
            )

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise AIProviderError(
                f"Could not parse OpenAI API response: {type(exc).__name__}."
            )

        if not text or not text.strip():
            raise AIProviderError("OpenAI API returned an empty response.")

        return text.strip()
