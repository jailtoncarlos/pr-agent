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

Security — command allowlist
----------------------------
This handler **executes** ``CLI_AI.COMMAND``. That value can be overridden by a
per-repo ``.pr_agent.toml`` (``apply_repo_settings`` merges repo config), so an
untrusted PR could otherwise set it to an arbitrary binary → remote code
execution on the runner. Two defenses:

1. The configured command is preferred from the **trusted environment**
   (``PR_AGENT_CLI_COMMAND``, set by the operator/workflow) over the merged
   settings (which a repo file can influence).
2. The resolved **executable is allowlisted** (default ``claude`` / ``codex``).
   Anything else is refused. Extend the allowlist only via the trusted env var
   ``PR_AGENT_CLI_ALLOWED_COMMANDS`` (comma-separated basenames) — never from
   repo config.
"""
import asyncio
import contextlib
import os
import shlex

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger

# Executable basenames this handler is allowed to run. Closes the RCE where a
# per-repo `.pr_agent.toml` overrides `[cli_ai] command` with an arbitrary
# binary. Extend ONLY via the trusted env var PR_AGENT_CLI_ALLOWED_COMMANDS.
_DEFAULT_ALLOWED_COMMANDS = ("claude", "codex")


def _allowed_commands() -> set[str]:
    extra = os.environ.get("PR_AGENT_CLI_ALLOWED_COMMANDS", "")
    names = {c.strip() for c in extra.split(",") if c.strip()}
    return set(_DEFAULT_ALLOWED_COMMANDS) | names


class CliAiHandler(BaseAiHandler):
    """Drive a subscription CLI (OAuth) in headless mode as the LLM provider."""

    def __init__(self):
        settings = get_settings()
        # Prefer the command from the trusted environment over merged settings: a
        # per-repo .pr_agent.toml can override CLI_AI.COMMAND, so the env var
        # (operator/workflow controlled) takes precedence when present.
        self.command = (os.environ.get("PR_AGENT_CLI_COMMAND")
                        or settings.get("CLI_AI.COMMAND", "claude -p"))
        # Guard the int() conversion: the value may come from an env var as a raw
        # string, so a malformed/empty value must not crash construction.
        try:
            self.timeout = int(settings.get("CLI_AI.TIMEOUT_SECONDS", 300))
            # A non-positive timeout makes asyncio.wait_for fire immediately on
            # every call (and kill the CLI) — treat it as invalid too.
            if self.timeout <= 0:
                self.timeout = 300
        except (TypeError, ValueError):
            self.timeout = 300

    @property
    def deployment_id(self):
        return None

    def _resolve_argv(self) -> list[str]:
        """Parse ``self.command`` and enforce the executable allowlist.

        Raises:
            ValueError: if the command is empty.
            PermissionError: if the executable is not allowlisted (defends
                against an untrusted repo overriding ``[cli_ai] command``).
        """
        argv = shlex.split(self.command)
        if not argv:
            raise ValueError("CliAiHandler: empty CLI_AI.COMMAND.")
        # A repo-controlled command can point at a path whose basename is
        # allowlisted (e.g. a malicious './claude' committed to the PR checkout,
        # which lives on the runner). Only the trusted env may supply a
        # path-qualified executable; otherwise require a bare command name
        # resolved via PATH.
        if os.path.dirname(argv[0]) and not os.environ.get("PR_AGENT_CLI_COMMAND"):
            raise PermissionError(
                "CliAiHandler: refusing a path-qualified executable from untrusted "
                "config; use a bare command name resolved via PATH (or set the "
                "trusted env var PR_AGENT_CLI_COMMAND).")
        executable = os.path.basename(argv[0])
        allowed = _allowed_commands()
        if executable not in allowed:
            raise PermissionError(
                f"CliAiHandler: refusing to run '{executable}'. The CLI command is "
                f"allowlisted to {sorted(allowed)} to prevent arbitrary command "
                f"execution from untrusted config (a per-repo .pr_agent.toml could "
                f"otherwise override [cli_ai] command). Extend the allowlist via the "
                f"trusted env var PR_AGENT_CLI_ALLOWED_COMMANDS.")
        # `codex exec` requires --skip-git-repo-check to run outside a git repo
        # (e.g. a CI runner with no checkout). Lesson from the reference impl (forje).
        if "codex" in executable and "--skip-git-repo-check" not in argv:
            argv.append("--skip-git-repo-check")
        return argv

    async def chat_completion(self, model: str, system: str, user: str,
                              temperature: float = 0.2, img_path: str = None):
        if img_path:
            get_logger().warning(
                "CliAiHandler: img_path ignored (not supported via CLI).")

        prompt = f"{system}\n\n{user}" if system else user
        argv = self._resolve_argv()

        get_logger().info(
            f"CliAiHandler: running '{' '.join(argv)}' "
            f"(model param '{model}' ignored — the CLI uses the subscription model)")

        # Prompt ALWAYS via stdin (never argv): argv overflows ARG_MAX (~2MB) on
        # large diffs — OSError 'Argument list too long' (forje lesson, TSK#816).
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode()), timeout=self.timeout)
        except asyncio.TimeoutError as e:
            # wait_for cancels communicate() but the CLI subprocess keeps running;
            # kill and reap it, otherwise it leaks (orphan process) on every timeout.
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
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
