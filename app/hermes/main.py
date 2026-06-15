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
import re
import signal
import sys
import threading
import traceback
from pathlib import Path
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
_workspace_sync = None
_workspace_namespace = ""
_workspace_lock = threading.Lock()


def _derive_workspace_namespace(payload: dict[str, Any], context: Any) -> str:
    """Return a stable S3 prefix namespace for this invocation."""
    candidates = [
        payload.get("userId"),
        payload.get("user_id"),
        payload.get("actorId"),
        payload.get("actor_id"),
        getattr(context, "runtime_user_id", None),
        getattr(context, "runtimeUserId", None),
        getattr(context, "user_id", None),
    ]
    for candidate in candidates:
        if candidate:
            raw = str(candidate)
            namespace = re.sub(r"[^A-Za-z0-9._=-]+", "_", raw).strip("._-")
            if namespace:
                return namespace[:128]
    return "agentcore-default"


def _ensure_workspace(namespace: str) -> None:
    """Restore and start S3 sync for the namespace, if configured."""
    global _workspace_namespace, _workspace_sync

    bucket = os.environ.get("S3_BUCKET", "")
    if not bucket:
        return

    with _workspace_lock:
        if _workspace_sync is not None:
            if _workspace_namespace != namespace:
                raise RuntimeError(
                    "Workspace already initialized for "
                    f"{_workspace_namespace}; refusing to serve {namespace} "
                    "in the same container",
                )
            return

        from bridge.workspace_sync import WorkspaceSync

        sync = WorkspaceSync()
        sync.restore(namespace)
        workspace = Path(os.environ.get("WORKSPACE_PATH", "/mnt/workspace/.hermes"))
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / ".workspace_namespace").write_text(namespace + "\n")
        sync.start_periodic_save(namespace)
        _workspace_sync = sync
        _workspace_namespace = namespace
        os.environ["AGENTCORE_USER_NAMESPACE"] = namespace
        log.info("Workspace sync initialised (bucket=%s, ns=%s)", bucket, namespace)


def _save_workspace() -> None:
    """Persist the current workspace when S3 sync has been initialised."""
    if _workspace_sync is None or not _workspace_namespace:
        return
    _workspace_sync.save(_workspace_namespace)


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
    log.info("SIGTERM received — saving workspace and shutting down")
    try:
        _save_workspace()
    except Exception as exc:
        log.error("Workspace save failed during shutdown: %s", exc)
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
    namespace = _derive_workspace_namespace(payload, context)

    if not message or not message.strip():
        yield ""
        return

    try:
        _ensure_workspace(namespace)
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
    finally:
        try:
            _save_workspace()
        except Exception as exc:
            log.error("Workspace save failed after invocation: %s", exc)


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
