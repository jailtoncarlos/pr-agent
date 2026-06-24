# MCP server — review a PR from inside your agent window or a hosted connector

`pr-agent-mcp` is a **local stdio MCP server** that exposes the reviewer as a
**tool** to any MCP-compatible local agent (Claude Code, Cursor, Codex, and
other clients that can launch stdio MCP servers). From your window you ask
*"review PR #X"* and the agent calls the tool.

`pr-agent-mcp-http` exposes the same tools over **Streamable HTTP** for clients
that connect to a reachable URL instead of launching a local subprocess, such as
ChatGPT desktop/web connectors and Windows desktop clients configured for remote
HTTP MCP servers.

The review runs on the configured **subscription CLI handler** (`ai_handler=cli`),
**independent of the host window**. So:

- Window = **Claude Code**, `PR_AGENT_CLI_COMMAND="codex exec"` → reviewer =
  **ChatGPT**.
- Window = **Codex**, `PR_AGENT_CLI_COMMAND="claude -p"` → reviewer = **Claude**.
- Window = **any local MCP client**, `PR_AGENT_CLI_COMMAND="gemini ..."` →
  reviewer = **Gemini** (if you have a Gemini CLI authenticated and allowlisted).

→ the reviewer model **≠** the window model: an **independent second opinion**
(anti-echo-chamber).

This is the **local / interactive** path. The **CI** path is the GitHub Action
(`action.yml`, see `docs/oauth-cli-mode.md`).

It is **not** the same integration path as a hosted ChatGPT app or a desktop app
configured to consume a remote HTTP MCP server. Those integrations need a
reachable app/MCP server transport such as Streamable HTTP, plus an
authentication model. See
[ChatGPT / hosted apps](#chatgpt--hosted-apps).

## Tools

| Tool | Action |
|---|---|
| `review_pr(pr_url)` | post a review summary + labels |
| `improve_pr(pr_url)` | post inline, committable code suggestions |
| `describe_pr(pr_url)` | generate/refresh the PR title + description |

## Local stdio — Claude calls MCP, Codex reviews

Goal: from a Claude Code window in any repo, ask *"review PR #X"* and have a
**different model** (e.g. ChatGPT via `codex`) review it on your subscription.

**1. Install the fork (with the `mcp` extra).** This fork is **not on PyPI** —
install from git. Requires **Python ≥ 3.12**. `pipx` keeps `pr-agent-mcp` on PATH:

```bash
pipx install "pr-agent[mcp] @ git+https://github.com/jailtoncarlos/pr-agent.git"
which pr-agent-mcp        # note the path (e.g. ~/.local/bin/pr-agent-mcp)
```

(venv alternative: `python3.12 -m venv ~/.venvs/pr-agent && ~/.venvs/pr-agent/bin/pip install "pr-agent[mcp] @ git+https://github.com/jailtoncarlos/pr-agent.git"` — then use the absolute `~/.venvs/pr-agent/bin/pr-agent-mcp` as the `command`.)

**2. Log in the CLIs (reused by the server, no token in config).**

```bash
codex login     # if the reviewer is ChatGPT  (PR_AGENT_CLI_COMMAND="codex exec")
claude /login   # if the reviewer is Claude    (PR_AGENT_CLI_COMMAND="claude -p")
gemini auth     # if your Gemini CLI uses an auth command like this
gh auth login   # so the server can resolve a GitHub token via `gh auth token`
```

**3. Register the server — user scope (applies to every repo you open).**

```bash
claude mcp add pr-agent --scope user \
  --env PR_AGENT_CLI_COMMAND="codex exec" \
  --env CONFIG__RESPONSE_LANGUAGE="pt-BR" \
  -- pr-agent-mcp
```

(Equivalent to a `mcpServers` entry in `~/.claude.json` — see [Configure](#configure-the-host-agent) below. Use the absolute path to `pr-agent-mcp` if it is not on PATH.)

This is the important wiring:

- **Host window**: Claude Code.
- **MCP tool server**: `pr-agent-mcp`, launched by Claude as a local subprocess.
- **Reviewer**: Codex, because `PR_AGENT_CLI_COMMAND="codex exec"`.
- **GitHub access**: `GITHUB_TOKEN`, or the local `gh auth token` fallback.

**4. Reload and verify.** Restart the session and run `/mcp` — `pr-agent` should
be **connected**, exposing `review_pr` / `improve_pr` / `describe_pr`.

**5. Use it.** In the window:

> improve the PR https://github.com/Prisma-Consultoria/prisma-ccm-docs/pull/440

The agent calls `improve_pr` → the server runs `codex exec` (reviewer = ChatGPT) →
posts inline suggestions on the PR in `pt-BR`. **Window = Claude, reviewer =
ChatGPT** = an independent second opinion.

## Install

```bash
pipx install "pr-agent[mcp] @ git+https://github.com/jailtoncarlos/pr-agent.git"
```

Installs the fork (not on PyPI) with the optional `mcp` dependency, providing the
`pr-agent-mcp` and `pr-agent-mcp-http` console commands. **Python ≥ 3.12.**

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

### Other local MCP clients

Use the same two pieces of configuration:

1. Launch this server as a **stdio** command: `pr-agent-mcp`.
2. Set `PR_AGENT_CLI_COMMAND` to the reviewer CLI you want to run.

For reviewer CLIs beyond the built-in allowlist (`claude`, `codex`, `gemini`),
extend the trusted allowlist from the host configuration:

```bash
PR_AGENT_CLI_COMMAND="gemini ..." \
PR_AGENT_CLI_ALLOWED_COMMANDS="gemini" \
pr-agent-mcp
```

The exact Gemini command depends on the installed Gemini CLI. Verify it manually
first with a tiny stdin prompt before using it as a reviewer.

## Scope and token hygiene

- **User scope** (`--scope user` / `~/.claude.json`) — one config that applies to
  **every repo** you open. Best for a personal reviewer across an org.
- **Project scope** (`.mcp.json` at the repo root) — committed and shared with the
  team. **Do not put a real `GITHUB_TOKEN` here** — it would be committed. Rely on
  the `gh auth token` fallback (omit `GITHUB_TOKEN`), or keep the token in your
  shell env / user scope only.

## Cross-model — pick the reviewer

The reviewer is whatever `PR_AGENT_CLI_COMMAND` runs, **independent of your
window**:

| Window | `PR_AGENT_CLI_COMMAND` | Reviewer |
|---|---|---|
| Claude Code | `codex exec` | **ChatGPT** — independent second opinion |
| Claude Code | `claude -p` | Claude — a fresh second pass (same family) |
| Codex | `claude -p` | **Claude** — independent second opinion |
| Codex / Claude / Cursor | `gemini ...` | **Gemini** — if the Gemini CLI is installed, authenticated, stdin-friendly, and allowlisted |

For a genuine second opinion (anti-echo-chamber), set the reviewer to a model from
a **different** family than your window.

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
| `PR_AGENT_CLI_ALLOWED_COMMANDS` | `claude,codex,gemini` | comma-separated executable basenames allowed for the CLI handler; extend only from trusted host config |
| `GITHUB_TOKEN` | — | GitHub token; if unset, falls back to `gh auth token` |
| `PR_AGENT_MCP_HTTP_HOST` | `127.0.0.1` | HTTP server bind host for `pr-agent-mcp-http` |
| `PR_AGENT_MCP_HTTP_PORT` | `8000` | HTTP server bind port for `pr-agent-mcp-http` |
| `PR_AGENT_MCP_HTTP_PATH` | `/mcp` | Streamable HTTP MCP path |
| `PR_AGENT_MCP_HTTP_LOG_LEVEL` | `info` | uvicorn log level |
| `PR_AGENT_MCP_BEARER_TOKEN` | — | optional Bearer token required by `pr-agent-mcp-http` |

`PR_AGENT_CLI_COMMAND` is the **trusted source** the hardened `CliAiHandler`
prefers (see `docs/oauth-cli-mode.md` → Security), so a per-repo `.pr_agent.toml`
cannot redirect the executed command.

## Local HTTP server

Use this when the MCP client connects to a URL instead of spawning a stdio
process. The server still runs locally and still uses your local CLI sessions.

```bash
export PR_AGENT_CLI_COMMAND="codex exec"
export CONFIG__RESPONSE_LANGUAGE="pt-BR"
pr-agent-mcp-http --host 127.0.0.1 --port 3333 --path /mcp
```

The local endpoint is:

```text
http://127.0.0.1:3333/mcp
```

For local clients that support Bearer auth:

```bash
export PR_AGENT_MCP_BEARER_TOKEN="$(openssl rand -hex 24)"
pr-agent-mcp-http --host 127.0.0.1 --port 3333 --path /mcp
```

Then configure the client to send:

```text
Authorization: Bearer <the value of PR_AGENT_MCP_BEARER_TOKEN>
```

Do not bind to `0.0.0.0` unless the host is protected by firewall and explicit
auth. This server can post comments to pull requests.

## ChatGPT or Claude Desktop with a local HTTP server

The ChatGPT desktop app, ChatGPT web app, and desktop clients such as Claude on
Windows do not automatically discover a random `localhost:3333` server. If the
client is configured through a hosted connector or remote HTTP MCP URL, it also
cannot call your private loopback address directly.

For local development, run `pr-agent-mcp-http` and expose it through a temporary
HTTPS tunnel:

```bash
export PR_AGENT_CLI_COMMAND="codex exec"
export CONFIG__RESPONSE_LANGUAGE="pt-BR"
pr-agent-mcp-http --host 127.0.0.1 --port 3333 --path /mcp
```

In another terminal:

```bash
ngrok http 3333
```

Use the HTTPS tunnel URL plus `/mcp` as the connector URL, for example:

```text
https://example.ngrok-free.app/mcp
```

If the connector or tunnel can send a Bearer header, set
`PR_AGENT_MCP_BEARER_TOKEN`. If it cannot, treat the tunnel as a short-lived
development-only setup and shut it down immediately after the test. For shared or
production usage, implement the authentication flow expected by the target
connector instead of exposing an unauthenticated tunnel.

For Claude Desktop on Windows there are two possible shapes:

1. If Claude Desktop is configured to launch local stdio MCP servers, use the
   same `pr-agent-mcp` configuration from
   [Local stdio — Claude calls MCP, Codex reviews](#local-stdio--claude-calls-mcp-codex-reviews).
   In that mode no tunnel is needed; Claude launches the local process and the
   reviewer is Codex because `PR_AGENT_CLI_COMMAND="codex exec"`.
2. If Claude Desktop is configured to connect to a remote/HTTP MCP server, run
   `pr-agent-mcp-http` and provide an HTTPS URL, either through a development
   tunnel or a cloud deployment.

## Cloud HTTP server

For a cloud deployment, run the same HTTP entry point behind HTTPS:

```bash
export PR_AGENT_CLI_COMMAND="codex exec"
export CONFIG__RESPONSE_LANGUAGE="pt-BR"
export GITHUB_TOKEN="ghp_or_fine_grained_token"
export PR_AGENT_MCP_BEARER_TOKEN="long_random_secret"
pr-agent-mcp-http --host 0.0.0.0 --port 8000 --path /mcp
```

Recommended production shape:

1. Put the service behind a reverse proxy or platform load balancer that
   terminates TLS.
2. Use connector-supported auth, preferably OAuth or another first-class app
   authorization flow.
3. Store GitHub credentials in the platform secret manager, scoped to the repos
   the service may review.
4. Run the reviewer through a server-side CLI or API account that is acceptable
   for your data-retention policy.
5. Log PR URLs and request IDs, but avoid logging full diffs or tokens.

The cloud server must not rely on a developer's local `gh auth token`; use
explicit server-side credentials.

## ChatGPT / hosted apps

`pr-agent-mcp` is a **local stdio** server. That is the right shape for local
developer agents that can spawn a subprocess on your machine.

For the installed ChatGPT desktop app or ChatGPT web app, do not assume
`~/.codex/config.toml` or a local `pr-agent-mcp` binary will be used. Use
`pr-agent-mcp-http` for a reachable Streamable HTTP endpoint, and define its auth
story:

- GitHub auth cannot rely on the user's local `gh auth token`.
- Reviewer execution cannot rely on a local desktop shell unless you run a
  controlled bridge service yourself.
- The server should provide explicit user/workspace authorization before posting
  comments to PRs.
- Confidential PR diffs are sent to whichever reviewer backend the server runs;
  document retention and data handling before enabling it broadly.

A practical hosted architecture is:

1. A small remote MCP/app server exposes `review_pr`, `improve_pr`, and
   `describe_pr` over Streamable HTTP.
2. The server stores or receives a scoped GitHub token through an OAuth or
   secret-management flow.
3. The reviewer runs through a server-side provider/API or a controlled runner,
   not through the ChatGPT user's local shell.
4. ChatGPT connects to that app server; local Codex/Claude/Cursor can continue
   using the stdio server.

So yes: supporting ChatGPT as an installed app requires an additional remote/app
adapter. The local stdio MCP server remains useful and should not be stretched
into that role.

## Notes

- **Cross-model is the whole point.** A "thin" tool where the *host window* does
  the reasoning cannot review with a different model — see issue #2.
- Same structured-output / non-determinism caveats as the CLI handler apply
  (`docs/oauth-cli-mode.md`).
