"""Local stdio MCP server — expose the PR-Agent reviewer as a tool.

The review runs on the configured **subscription CLI handler**
(``ai_handler=cli``), independent of the host agent window. So from a **Claude
Code** window you can review with ``codex exec`` (ChatGPT) — and vice-versa — an
**independent second opinion** with a different model (anti-echo-chamber).

The host agent launches this as a **local stdio subprocess** (configured in
``.mcp.json`` for Claude Code / Cursor, or ``[mcp_servers]`` for Codex). Because
it runs locally, the CLIs (``claude`` / ``codex``) reuse your **already-logged-in
subscription session** — no OAuth token in config, no auth prompt. A **GitHub
token** is needed to fetch the diff and post comments (``GITHUB_TOKEN`` / a
logged-in ``gh``).

This is the **local / interactive** path. The **CI** path is ``action.yml`` (#1),
where the CLI is authenticated via a token secret.

Requires the optional ``mcp`` dependency::

    pip install "pr-agent[mcp]"

Run (normally launched by the host agent, not by hand)::

    pr-agent-mcp
"""
import os
import subprocess

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - import-time guard
    raise SystemExit(
        "The PR-Agent MCP server needs the 'mcp' package. Install it with:\n"
        '    pip install "pr-agent[mcp]"'
    ) from exc

from pr_agent.agent.pr_agent import PRAgent
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger

mcp = FastMCP("pr-agent")


def _github_token() -> str | None:
    """Resolve a GitHub token: env first, then a logged-in ``gh`` CLI."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB__USER_TOKEN")
    if token:
        return token
    try:
        out = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _configure() -> None:
    """Point pr-agent at the subscription CLI handler, from the (trusted) env.

    The CLI command comes from ``PR_AGENT_CLI_COMMAND`` — this is the trusted
    source the hardened ``CliAiHandler`` prefers, so a per-repo ``.pr_agent.toml``
    cannot redirect the executed command.
    """
    settings = get_settings()
    settings.set("CONFIG.AI_HANDLER", os.environ.get("PR_AGENT_AI_HANDLER", "cli"))
    settings.set("CLI_AI.COMMAND", os.environ.get("PR_AGENT_CLI_COMMAND", "claude -p"))
    settings.set("CLI_AI.TIMEOUT_SECONDS", os.environ.get("PR_AGENT_CLI_TIMEOUT", "300"))
    token = _github_token()
    if token:
        settings.set("GITHUB.USER_TOKEN", token)


_RESULT_NOUN = {
    "review": "a review",
    "improve": "code suggestions",
    "describe": "a description update",
}


async def _run(pr_url: str, command: list[str]) -> str:
    """Run a pr-agent command and return a human-readable result for the host.

    ``handle_request`` already swallows command errors (returns ``False``), but
    ``_configure()`` and ``PRAgent()`` construction run before it — wrap the whole
    thing so a config/auth/network failure is reported as a readable string
    instead of surfacing as an opaque MCP server error.
    """
    noun = _RESULT_NOUN.get(command[0], command[0])
    try:
        # Configure before constructing PRAgent — the AI handler is resolved in
        # PRAgent.__init__ from CONFIG.AI_HANDLER.
        _configure()
        get_logger().info(f"MCP: running {command} on {pr_url}")
        ok = await PRAgent().handle_request(pr_url, command)
    except Exception as exc:
        get_logger().error(f"MCP request failed: {exc}")
        return f"Error posting {noun} on {pr_url}: {exc}"
    return (f"Posted {noun} on {pr_url}." if ok
            else f"Failed to post {noun} on {pr_url} (see server logs).")


@mcp.tool()
async def review_pr(pr_url: str) -> str:
    """Review a GitHub/GitLab/Bitbucket Pull Request and post a review summary.

    Runs on the configured subscription CLI (e.g. ``claude -p`` / ``codex exec``),
    which may use a different model than this window.
    """
    return await _run(pr_url, ["review"])


@mcp.tool()
async def improve_pr(pr_url: str) -> str:
    """Suggest concrete code improvements on a PR as inline, committable suggestions."""
    return await _run(pr_url, ["improve"])


@mcp.tool()
async def describe_pr(pr_url: str) -> str:
    """Generate or refresh a PR's title and description."""
    return await _run(pr_url, ["describe"])


def main() -> None:
    """Console entry point (``pr-agent-mcp``) — stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
