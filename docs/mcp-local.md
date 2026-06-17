# Local MCP server — review a PR from inside your agent window

`pr-agent-mcp` is a **local stdio MCP server** that exposes the reviewer as a
**tool** to any MCP-compatible agent (Claude Code, Cursor, Codex). From your
window you ask *"review PR #X"* and the agent calls the tool.

The review runs on the configured **subscription CLI handler** (`ai_handler=cli`),
**independent of the host window**. So:

- Window = **Claude Code**, `PR_AGENT_CLI_COMMAND="codex exec"` → reviewer =
  **ChatGPT**.
- Window = **Codex**, `PR_AGENT_CLI_COMMAND="claude -p"` → reviewer = **Claude**.

→ the reviewer model **≠** the window model: an **independent second opinion**
(anti-echo-chamber).

This is the **local / interactive** path. The **CI** path is the GitHub Action
(`action.yml`, see `docs/oauth-cli-mode.md`).

## Tools

| Tool | Action |
|---|---|
| `review_pr(pr_url)` | post a review summary + labels |
| `improve_pr(pr_url)` | post inline, committable code suggestions |
| `describe_pr(pr_url)` | generate/refresh the PR title + description |

## Install

```bash
pip install "pr-agent[mcp]"   # adds the optional `mcp` dependency
```

This provides the `pr-agent-mcp` console command (the MCP server).

## Auth — local, no token in config

- **LLM**: the server fires `claude -p` / `codex exec`, which **reuse your
  already-logged-in CLI session** — no OAuth token in config, no prompt. Just keep
  the CLIs logged in on your machine (`claude` / `codex login`).
- **GitHub**: needed to fetch the diff and post comments. Set `GITHUB_TOKEN`, or
  just have the `gh` CLI logged in (the server falls back to `gh auth token`).

## Configure the host agent

### Claude Code / Cursor — `.mcp.json`

(see [`docs/examples/mcp-claude-code.json`](examples/mcp-claude-code.json))

```json
{
  "mcpServers": {
    "pr-agent": {
      "command": "pr-agent-mcp",
      "env": {
        "PR_AGENT_CLI_COMMAND": "codex exec",
        "GITHUB_TOKEN": "ghp_xxx_or_omit_to_use_gh_auth"
      }
    }
  }
}
```

### Codex — `~/.codex/config.toml`

(see [`docs/examples/mcp-codex-config.toml`](examples/mcp-codex-config.toml))

```toml
[mcp_servers.pr-agent]
command = "pr-agent-mcp"
env = { PR_AGENT_CLI_COMMAND = "claude -p", GITHUB_TOKEN = "ghp_xxx_or_omit_to_use_gh_auth" }
```

## Use

In the host window:

> review https://github.com/owner/repo/pull/42

The agent calls `review_pr` → the server runs the review on the configured CLI →
the result is posted on the PR.

## Environment variables

| Var | Default | Meaning |
|---|---|---|
| `PR_AGENT_CLI_COMMAND` | `claude -p` | the subscription CLI to run as the reviewer (`claude -p` / `codex exec`) |
| `PR_AGENT_AI_HANDLER` | `cli` | handler selection (keep `cli` for the subscription path) |
| `PR_AGENT_CLI_TIMEOUT` | `300` | per-call timeout (seconds) |
| `GITHUB_TOKEN` | — | GitHub token; if unset, falls back to `gh auth token` |

`PR_AGENT_CLI_COMMAND` is the **trusted source** the hardened `CliAiHandler`
prefers (see `docs/oauth-cli-mode.md` → Security), so a per-repo `.pr_agent.toml`
cannot redirect the executed command.

## Notes

- **Cross-model is the whole point.** A "thin" tool where the *host window* does
  the reasoning cannot review with a different model — see issue #2.
- Same structured-output / non-determinism caveats as the CLI handler apply
  (`docs/oauth-cli-mode.md`).
