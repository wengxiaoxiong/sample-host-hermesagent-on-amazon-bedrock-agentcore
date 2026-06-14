"""Hermes Agent on AgentCore with an OpenAI-compatible model API.

Uses the bedrock-agentcore SDK (BedrockAgentCoreApp) which handles the
/ping and /invocations HTTP contract automatically.

Architecture:
  - Keeps AgentCore as the runtime host.
  - Routes model calls to the user-provided OpenAI-compatible endpoint via
    hermes-agent provider/base_url settings.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import traceback
from typing import Any


def _get_region() -> str:
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-west-2"
    )


from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402

logger = logging.getLogger("hermes.agentcore")
app = BedrockAgentCoreApp()
log = app.logger

# ---------------------------------------------------------------------------
# Cached agent singleton
# ---------------------------------------------------------------------------

_agent = None


def get_or_create_agent():
    """Lazy-init the full hermes-agent. Blocks on first call (~5-15s)."""
    global _agent
    if _agent is not None:
        return _agent

    log.info("Initializing hermes-agent (first request) …")

    os.environ["HERMES_HEADLESS"] = "1"
    os.environ.setdefault("AGENTCORE_MODE", "1")

    region = _get_region()
    os.environ.setdefault("AWS_DEFAULT_REGION", region)
    os.environ.setdefault("AWS_REGION", region)

    base_url = os.environ.get("LITELLM_BASE_URL") or os.environ.get("HERMES_BASE_URL")
    api_key = os.environ.get("LITELLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = (
        os.environ.get("LITELLM_MODEL")
        or os.environ.get("HERMES_MODEL")
        or os.environ.get("MODEL_NAME")
        or "gpt-4o-mini"
    )
    provider = os.environ.get("HERMES_PROVIDER", "openai")

    if not base_url:
        raise RuntimeError("LITELLM_BASE_URL or HERMES_BASE_URL must be set")
    if not api_key:
        raise RuntimeError("LITELLM_API_KEY or OPENAI_API_KEY must be set")

    os.environ.setdefault("OPENAI_API_KEY", api_key)

    from run_agent import AIAgent

    _agent = AIAgent(
        model=model,
        provider=provider,
        quiet_mode=True,
        base_url=base_url,
        api_key=api_key,
    )

    log.info(
        "hermes-agent ready (model=%s, provider=%s, base_url=%s, region=%s)",
        model,
        provider,
        base_url,
        region,
    )
    return _agent


# ---------------------------------------------------------------------------
# SIGTERM handler
# ---------------------------------------------------------------------------

def _sigterm_handler(signum: int, frame: Any) -> None:
    log.info("SIGTERM received — shutting down")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

@app.entrypoint
async def invoke(payload, context):
    """Handle an AgentCore invocation."""
    prompt = payload.get("prompt", "")
    channel = payload.get("channel", "agentcore")
    message = payload.get("message", prompt)

    if not message or not message.strip():
        yield ""
        return

    try:
        agent = get_or_create_agent()

        system_extra = f"The user is contacting you via {channel}."
        if payload.get("chatId"):
            system_extra += f" Chat ID: {payload['chatId']}."

        # Restore conversation history from the gateway payload so the
        # agent has context from previous turns.
        history = payload.get("conversationHistory") or None

        result = agent.run_conversation(
            user_message=message,
            system_message=system_extra,
            conversation_history=history,
        )
        yield result.get("final_response", "")
    except Exception as exc:
        log.error("Agent error: %s\n%s", exc, traceback.format_exc())
        yield f"Sorry, an error occurred: {exc}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    signal.signal(signal.SIGTERM, _sigterm_handler)
    app.run()
