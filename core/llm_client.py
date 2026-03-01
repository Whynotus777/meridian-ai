"""Unified LLM client adapter.

Wraps both Anthropic (Claude) and Google (Gemini) so all core modules
can call a single `.complete()` method without caring about the provider.

Provider is selected via ModelConfig.provider ("anthropic" | "gemini").
API key is read from ANTHROPIC_API_KEY or GOOGLE_API_KEY respectively.

For Gemini we use Google's OpenAI-compatible endpoint so we only need
the `openai` package — no extra Google SDK required.
"""

from __future__ import annotations

import re
from typing import Optional
from config.settings import ModelConfig


def strip_fences(text: str) -> str:
    """Remove markdown code fences from an LLM response.

    Handles all variants Gemini/Claude may return:
        ```json\\n{...}\\n```
        ```\\n{...}\\n```
        ```json{...}```
    """
    text = text.strip()
    text = re.sub(r"^```(?:json|markdown|text)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


class LLMClient:
    """Provider-agnostic LLM completion client.

    Usage:
        client = LLMClient(config)
        text = client.complete(system="You are...", user="Analyze this...")
    """

    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self._client = self._build_client()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        """Send a system + user prompt and return the response text.

        Args:
            system:      System / persona prompt.
            user:        User message / task prompt.
            max_tokens:  Maximum tokens in response.
            temperature: Sampling temperature (0 = deterministic).

        Returns:
            Response text as a plain string.
        """
        if self.config.provider == "gemini":
            return self._complete_gemini(system, user, max_tokens, temperature)
        return self._complete_anthropic(system, user, max_tokens, temperature)

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _complete_anthropic(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> str:
        response = self._client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text.strip()

    def _complete_gemini(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> str:
        response = self._client.chat.completions.create(
            model=self.config.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return response.choices[0].message.content.strip()

    # ------------------------------------------------------------------
    # Client factory
    # ------------------------------------------------------------------

    def _build_client(self):
        if self.config.provider == "gemini":
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(
                    "Gemini provider requires the `openai` package. "
                    "Run: pip install openai"
                )
            return OpenAI(
                api_key=self.config.api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
        else:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "Anthropic provider requires the `anthropic` package. "
                    "Run: pip install anthropic"
                )
            return anthropic.Anthropic(api_key=self.config.api_key)
