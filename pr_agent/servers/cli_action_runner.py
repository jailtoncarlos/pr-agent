"""GitHub Action entrypoint for the CLI/OAuth handler (fork).

Thin wrapper around ``github_action_runner.run_action()``: selects the
``CliAiHandler`` and configures it from environment variables set by
``action.yml``, then runs the standard PR-Agent action flow (reads the PR from
the event and posts the review). Makes the review run on a **chat/CLI
subscription** (Claude Code / Codex) instead of an API key.

Environment variables read (set by action.yml):
- ``PR_AGENT_AI_HANDLER``  (default "cli")
- ``PR_AGENT_CLI_COMMAND`` (default "claude -p")
- ``PR_AGENT_CLI_TIMEOUT`` (default "300")

Subscription auth (e.g. ``CLAUDE_CODE_OAUTH_TOKEN``) is read by the CLI itself —
action.yml exports it into the environment.
"""
import asyncio
import os

from pr_agent.config_loader import get_settings
from pr_agent.servers.github_action_runner import run_action


def _configure_cli_handler() -> None:
    settings = get_settings()
    settings.set("CONFIG.AI_HANDLER",
                 os.environ.get("PR_AGENT_AI_HANDLER", "cli"))
    settings.set("CLI_AI.COMMAND",
                 os.environ.get("PR_AGENT_CLI_COMMAND", "claude -p"))
    settings.set("CLI_AI.TIMEOUT_SECONDS",
                 os.environ.get("PR_AGENT_CLI_TIMEOUT", "300"))


def main() -> None:
    _configure_cli_handler()
    asyncio.run(run_action())


if __name__ == "__main__":
    main()
