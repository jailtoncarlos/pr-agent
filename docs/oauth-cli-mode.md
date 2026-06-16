# OAuth/CLI subscription mode (Claude Code / Codex) — no API key

This fork adds an **AI handler** that runs PR review on your **chat/CLI
subscription quota** (Claude Max via the `claude` CLI, ChatGPT Pro via the
`codex` CLI), instead of an **API key** (pay-per-token). It solves the case of
having only a subscription (no API quota) and/or hitting the **GitHub Copilot
review quota**.

## Why

Upstream PR-Agent talks to the LLM via an **API key** (`litellm` → OpenAI/Anthropic
API). A **chat/CLI subscription** is **OAuth**, not API — it powers the chat apps
and the terminal clients, but does **not** expose an API key. The only way to use
the subscription is to **drive the logged-in CLI** in headless mode.

## How it works

`CliAiHandler` (`pr_agent/algo/ai_handlers/cli_ai_handler.py`) implements the
`BaseAiHandler.chat_completion(...)` interface by running the CLI as a subprocess:
the prompt (the system + user message that PR-Agent already builds) goes in via
`stdin`, and the response is `stdout`. **The rest of the PR-Agent pipeline is
reused** — diff hunking, prompts, inline posting via the Reviews API, incremental
review.

```
trigger → diff hunks → prompt (.toml) → CliAiHandler → claude -p / codex exec
        → response → parse → post inline (Reviews API)
```

## How to enable

In `configuration.toml` (or your repo's `.pr_agent.toml`):

```toml
[config]
ai_handler = "cli"          # default is "litellm" (API key)

[cli_ai]
command = "claude -p"       # or "codex exec"
timeout_seconds = 300
```

Then run as usual (e.g. `python -m pr_agent.cli --pr_url <URL> review`).

## Run as a GitHub Action

This fork ships an `action.yml` (composite) that packages the reviewer. In any
repo, `.github/workflows/pr-review.yml`:

```yaml
on: { pull_request: { types: [opened, synchronize, reopened] } }
permissions: { pull-requests: write, contents: read }
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: jailtoncarlos/pr-agent@<COMMIT_SHA>
        with:
          cli_command: "claude -p"
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
```

Ready-made examples: `docs/examples/single-repo-pr-review.yml` (single repo) and
`docs/examples/org-anchor-reusable-workflow.yml` (org-wide governance from an
anchor repo).

## Where it runs — the subscription auth must be available in the environment

The `claude`/`codex` CLIs authenticate through the subscription's **OAuth
session**. That session must be present where pr-agent runs. Two scenarios — **CI
included**:

### Local / self-hosted runner
✅ Direct — the CLI just needs to be logged in (`claude` / `codex login`).

### GitHub-hosted runner (cloud CI) — ✅ with the subscription token as a *secret*
There is no session by default, but you **inject the credential via a secret**;
the handler is the same, only the **workflow** changes (install the CLI + provide
the auth):

- **Claude Code (official CI mechanism)**: generate a long-lived OAuth token with
  `claude setup-token` (tied to the Max subscription) and store it as a secret
  (e.g. `CLAUDE_CODE_OAUTH_TOKEN`). The `claude` CLI reads that env var and runs
  on the subscription on a GitHub-hosted runner. *(Confirm the exact
  command/env-var name in the current Claude Code docs.)*
- **Codex (ChatGPT Pro)**: restore the credential from `codex login`
  (e.g. `~/.codex/auth.json`) from a secret before running. Works, but less
  official than Claude's `setup-token`.

### CI auth caveats
- **Token lifecycle**: the CI token expires / can be revoked → rotate the secret.
- **ToS**: `claude setup-token` is provided by Anthropic for automation/CI
  (intended use). For **Codex/ChatGPT Pro**, headless CI use is a grayer area —
  check OpenAI's terms first.
- **Security**: the token **is your account** — treat the secret carefully
  (scope, who can access the repo).

## Known limitations

- **Structured output**: the prompts ask for YAML/JSON; the CLI produces it, but
  without the API's `response_format` — may need firmer prompts / robust parsing.
- **`model`** is ignored (the CLI uses the subscription model); token counting
  (`tiktoken`) becomes an approximation for diff compression.
- **Latency**: there is CLI startup cost per call.

> Status: integration handler. End-to-end viability (structured-output quality via
> the CLI) should be validated on a real PR before production use.
