"""CLI AI handler — authenticate via a chat/CLI subscription (Claude Code / Codex).

Instead of calling the provider API with an API key (pay-per-token, like the
default ``LiteLLMAIHandler``), this handler drives a *subscription CLI* in
headless mode — e.g. ``claude -p`` (Claude Max) or ``codex exec`` (ChatGPT Pro).
Those CLIs authenticate through the subscription's OAuth session, so the review
runs on the **subscription quota** — no API key and no GitHub Copilot quota.

Requirement: the CLI must be authenticated in the environment where pr-agent
runs (your local machine, or a self-hosted runner already logged in). Standard
cloud runners (GitHub-hosted) have no subscription session — provide the auth via
a secret (see docs/oauth-cli-mode.md).

Selection: set ``[config] ai_handler="cli"`` (default ``"litellm"``) and configure
the ``[cli_ai]`` section in ``configuration.toml``.
"""
import asyncio
import os
import shlex

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger


class CliAiHandler(BaseAiHandler):
    """Drive a subscription CLI (OAuth) in headless mode as the LLM provider."""

    def __init__(self):
        settings = get_settings()
        # Subscription CLI command. E.g. "claude -p" or "codex exec".
        self.command = settings.get("CLI_AI.COMMAND", "claude -p")
        self.timeout = int(settings.get("CLI_AI.TIMEOUT_SECONDS", 300))

    @property
    def deployment_id(self):
        return None

    async def chat_completion(self, model: str, system: str, user: str,
                              temperature: float = 0.2, img_path: str = None):
        if img_path:
            get_logger().warning(
                "CliAiHandler: img_path ignored (not supported via CLI).")

        prompt = f"{system}\n\n{user}" if system else user
        argv = shlex.split(self.command)
        # `codex exec` requires --skip-git-repo-check to run outside a git repo
        # (e.g. a CI runner with no checkout). Lesson from the reference impl (forje).
        if (argv and "codex" in os.path.basename(argv[0])
                and "--skip-git-repo-check" not in argv):
            argv.append("--skip-git-repo-check")

        get_logger().info(
            f"CliAiHandler: running '{' '.join(argv)}' "
            f"(model param '{model}' ignored — the CLI uses the subscription model)")

        # Prompt ALWAYS via stdin (never argv): argv overflows ARG_MAX (~2MB) on
        # large diffs — OSError 'Argument list too long' (forje lesson, TSK#816).
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode()), timeout=self.timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutError(
                f"CliAiHandler: '{self.command}' exceeded {self.timeout}s") from e

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[:800]
            raise RuntimeError(
                f"CliAiHandler: '{self.command}' failed (rc={proc.returncode}). "
                f"Is the CLI authenticated in this environment? stderr: {err}")

        resp = stdout.decode(errors="replace").strip()
        if not resp:
            err = stderr.decode(errors="replace")[:400]
            raise RuntimeError(
                f"CliAiHandler: empty response from '{self.command}'. stderr: {err}")

        # The CLI does not expose a finish_reason; use "stop" (complete response).
        return resp, "stop"
