"""Tests for workspace sync in the AgentCore app entrypoint."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest


class _FakeAgentCoreApp:
    logger = None

    def __init__(self) -> None:
        import logging

        self.logger = logging.getLogger("test.agentcore")

    def entrypoint(self, fn):
        return fn

    def run(self) -> None:
        return None


@pytest.fixture
def main_module(monkeypatch):
    """Import app/hermes/main.py with a fake AgentCore SDK."""
    runtime = types.ModuleType("bedrock_agentcore.runtime")
    runtime.BedrockAgentCoreApp = _FakeAgentCoreApp
    package = types.ModuleType("bedrock_agentcore")
    package.runtime = runtime
    monkeypatch.setitem(sys.modules, "bedrock_agentcore", package)
    monkeypatch.setitem(sys.modules, "bedrock_agentcore.runtime", runtime)

    module_path = Path(__file__).resolve().parents[1] / "app" / "hermes" / "main.py"
    spec = importlib.util.spec_from_file_location("hermes_main_for_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_derive_workspace_namespace_sanitizes_payload_user_id(main_module):
    namespace = main_module._derive_workspace_namespace(
        {"userId": "feishu:user/abc 123"},
        object(),
    )

    assert namespace == "feishu_user_abc_123"


def test_derive_workspace_namespace_uses_context_fallback(main_module):
    context = types.SimpleNamespace(runtime_user_id="runtime:user")

    namespace = main_module._derive_workspace_namespace({}, context)

    assert namespace == "runtime_user"


def test_ensure_workspace_restores_and_starts_periodic_save(main_module, monkeypatch, tmp_path):
    calls = []
    workspace = tmp_path / ".hermes"

    class _FakeWorkspaceSync:
        def restore(self, namespace: str) -> None:
            calls.append(("restore", namespace))

        def start_periodic_save(self, namespace: str) -> None:
            calls.append(("periodic", namespace))

        def save(self, namespace: str) -> None:
            calls.append(("save", namespace))

    monkeypatch.setenv("S3_BUCKET", "bucket")
    monkeypatch.setenv("WORKSPACE_PATH", str(workspace))
    monkeypatch.setattr("bridge.workspace_sync.WorkspaceSync", _FakeWorkspaceSync)

    main_module._ensure_workspace("user123")
    main_module._save_workspace()

    assert calls == [
        ("restore", "user123"),
        ("periodic", "user123"),
        ("save", "user123"),
    ]
    assert main_module._workspace_namespace == "user123"
    assert (workspace / ".workspace_namespace").read_text() == "user123\n"


def test_ensure_workspace_refuses_namespace_switch(main_module, monkeypatch, tmp_path):
    class _FakeWorkspaceSync:
        def restore(self, namespace: str) -> None:
            return None

        def start_periodic_save(self, namespace: str) -> None:
            return None

    monkeypatch.setenv("S3_BUCKET", "bucket")
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path / ".hermes"))
    monkeypatch.setattr("bridge.workspace_sync.WorkspaceSync", _FakeWorkspaceSync)

    main_module._ensure_workspace("user-a")

    with pytest.raises(RuntimeError, match="refusing to serve user-b"):
        main_module._ensure_workspace("user-b")


def test_invoke_restores_before_agent_and_saves_after(main_module, monkeypatch):
    events = []

    class _FakeAgent:
        def run_conversation(self, **kwargs):
            events.append(("agent", kwargs["user_message"]))
            return {"final_response": "ok"}

    def _ensure(namespace: str) -> None:
        events.append(("ensure", namespace))

    def _save() -> None:
        events.append(("save", ""))

    monkeypatch.setattr(main_module, "_ensure_workspace", _ensure)
    monkeypatch.setattr(main_module, "_save_workspace", _save)
    monkeypatch.setattr(main_module, "get_or_create_agent", lambda: _FakeAgent())

    async def _collect():
        values = []
        async for value in main_module.invoke(
            {"userId": "user-1", "message": "hello"},
            object(),
        ):
            values.append(value)
        return values

    result = asyncio.run(_collect())

    assert result == ["ok"]
    assert events == [
        ("ensure", "user-1"),
        ("agent", "hello"),
        ("save", ""),
    ]
