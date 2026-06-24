import pytest

import pr_agent.servers.mcp_server as mcp_server
from pr_agent.algo.ai_handlers.cli_ai_handler import CliAiHandler
from pr_agent.config_loader import get_settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB__USER_TOKEN", raising=False)
    monkeypatch.delenv("PR_AGENT_AI_HANDLER", raising=False)
    monkeypatch.delenv("PR_AGENT_CLI_COMMAND", raising=False)
    monkeypatch.delenv("PR_AGENT_CLI_TIMEOUT", raising=False)


def test_ai_handler_defaults_to_cli_handler():
    assert mcp_server._ai_handler() is CliAiHandler


def test_ai_handler_can_defer_to_default_pr_agent_resolution(monkeypatch):
    monkeypatch.setenv("PR_AGENT_AI_HANDLER", "litellm")

    assert mcp_server._ai_handler() is None


def test_configure_sets_cli_mode_and_github_token(monkeypatch):
    monkeypatch.setenv("PR_AGENT_CLI_COMMAND", "codex exec")
    monkeypatch.setenv("PR_AGENT_CLI_TIMEOUT", "900")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")

    mcp_server._configure()

    settings = get_settings()
    assert settings.get("CONFIG.AI_HANDLER") == "cli"
    assert settings.get("CLI_AI.COMMAND") == "codex exec"
    assert settings.get("CLI_AI.TIMEOUT_SECONDS") == "900"
    assert settings.get("GITHUB.USER_TOKEN") == "ghp_test"


@pytest.mark.asyncio
async def test_run_passes_explicit_cli_handler_to_pr_agent(monkeypatch):
    calls = []

    class FakePRAgent:
        def __init__(self, ai_handler=None):
            calls.append({"ai_handler": ai_handler})

        async def handle_request(self, pr_url, command):
            calls[-1].update({"pr_url": pr_url, "command": command})
            return True

    monkeypatch.setenv("PR_AGENT_CLI_COMMAND", "codex exec")
    monkeypatch.setattr(mcp_server, "PRAgent", FakePRAgent)

    result = await mcp_server._run("https://github.com/o/r/pull/1", ["review"])

    assert result == "Posted a review on https://github.com/o/r/pull/1."
    assert calls == [{
        "ai_handler": CliAiHandler,
        "pr_url": "https://github.com/o/r/pull/1",
        "command": ["review"],
    }]
