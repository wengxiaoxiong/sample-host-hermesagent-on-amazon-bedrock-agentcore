"""Lightweight warm-up agent for fast cold-start response.

Handles user messages while the full hermes-agent is loading (~10-30 s).
Uses the configured OpenAI-compatible model API directly — no hermes
dependencies.
"""

from __future__ import annotations

import logging
import os

import litellm

logger = logging.getLogger("agentcore.warmup")

SYSTEM_PROMPT = """\
You are Hermes, a helpful AI assistant deployed on AgentCore.

The full agent (with 40+ tools including terminal, browser, web search, file \
operations, code execution, and more) is still loading. While it warms up you \
can answer questions directly from your knowledge.

For requests that require tools (running code, browsing the web, managing \
files, etc.), let the user know you will be fully ready in a moment.

Keep responses concise and helpful."""


class WarmupAgent:
    """Minimal agent backed by a single OpenAI-compatible completion call."""

    def __init__(self) -> None:
        self.base_url = os.environ.get("LITELLM_BASE_URL") or os.environ.get(
            "HERMES_BASE_URL",
            "",
        )
        self.api_key = os.environ.get("LITELLM_API_KEY") or os.environ.get(
            "OPENAI_API_KEY",
            "",
        )
        self.model_id = (
            os.environ.get("WARMUP_MODEL")
            or os.environ.get("LITELLM_MODEL")
            or os.environ.get("HERMES_MODEL")
            or os.environ.get("MODEL_NAME")
            or "gpt-4o-mini"
        )
        if not self.base_url:
            raise RuntimeError("LITELLM_BASE_URL or HERMES_BASE_URL must be set")
        if not self.api_key:
            raise RuntimeError("LITELLM_API_KEY or OPENAI_API_KEY must be set")
        logger.info(
            "WarmupAgent initialised (model=%s, base_url=%s)",
            self.model_id,
            self.base_url,
        )

    def handle(self, message: str, user_id: str) -> str:
        """Return a response for *message* using the configured model API."""
        try:
            response = self._call_model(message)
            return self._extract_text(response)
        except Exception as exc:
            logger.error("WarmupAgent.handle error: %s", exc)
            return (
                "I'm still starting up — please try again in a few seconds."
            )

    # ------------------------------------------------------------------

    def _call_model(self, message: str):
        return litellm.completion(
            model=self.model_id,
            api_base=self.base_url,
            api_key=self.api_key,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": message,
                },
            ],
            max_tokens=2048,
            temperature=0.7,
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        try:
            return response.choices[0].message.content or ""
        except (AttributeError, IndexError, KeyError, TypeError):
            try:
                return response["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                return ""
