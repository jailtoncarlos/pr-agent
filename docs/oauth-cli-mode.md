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
  PR-Agent already **retries** an initial parse failure (`load_yaml` in
  `pr_agent/algo/utils.py`), which usually recovers.
- **`model`** is ignored (the CLI uses the subscription model); token counting
  (`tiktoken`) becomes an approximation for diff compression.
- **Latency**: there is CLI startup cost per call.

> Status: integration handler. End-to-end viability (structured-output quality via
> the CLI) should be validated on a real PR before production use.

## Output behavior — determinism and suggestion volume

These two are commonly observed when comparing runs (or comparing to the GitHub
Copilot reviewer). Neither is a bug; both are explained below with the relevant
knobs.

### Run-to-run results differ (non-determinism)

Two `/improve` (or `/review`) runs on the same PR can surface **different**
findings. Causes:

- **Sampling is non-deterministic** — defaults are `temperature = 0.2` and
  `seed = -1` (`pr_agent/settings/configuration.toml`); a negative seed means *no*
  seed fixing, so each call samples differently.
- **The CLI/OAuth path cannot fix the seed.** Setting `seed` to a positive value
  (which forces `temperature = 0`) only works through the **API** path
  (`ai_handler = litellm`). The subscription CLI (`claude -p` / `codex exec`) has
  **no seed / `response_format` parameter**, so full determinism is **not
  controllable in this mode**. This is an inherent trade-off of running on a
  subscription instead of an API.
- **PR-Agent is history-aware.** It reads previous suggestion comments
  (`pr_code_suggestions.max_history_len`, the "Previous suggestions" section in
  `pr_code_suggestions.py`), so a second run is *not* independent of the first — it
  tends to present a refreshed set.

### Why fewer comments than expected — and the right knob

> **Key correction.** `/improve` reads **`pr_code_suggestions.num_code_suggestions_per_chunk`**
> (`pr_agent/tools/pr_code_suggestions.py:43`), **not** `num_code_suggestions`. The
> `num_code_suggestions` key (default 4) belongs to **`[pr_improve_component]`**
> (`/improve_component`), a *different* tool. Setting
> `PR_CODE_SUGGESTIONS__NUM_CODE_SUGGESTIONS` therefore has **no effect** on
> `/improve`. This fork's default for the right key is
> `num_code_suggestions_per_chunk = 8`.

The per-chunk value is a **ceiling, not a floor**. The actual count is also shaped
by a filter chain, so a small/clean diff yields fewer:

1. **`focus_only_on_problems = true`** — only real problems pass; style/nits are
   dropped (this caps the *supply* of suggestions).
2. **Self-reflection scoring** — each suggestion is scored
   (`pr_code_suggestions_reflect_prompts.toml`); note self-reflection only
   *assigns* a score (it does not drop). The score then feeds the threshold below.
3. **Score threshold** — `suggestions_score_threshold` drops `score < max(1, threshold)`
   (`pr_code_suggestions.py:717`). With the default `0` this only removes `score < 1`.
4. **Inline anchoring (422-safe)** — a committable inline suggestion is only posted
   when its `relevant_lines_start/end` fall **inside a diff hunk**
   (`push_inline_code_suggestions`); ones that don't map to a changed line are
   dropped. Strictest with `commitable_code_suggestions = true` (this fork's default).
5. **Chunking** — `num_code_suggestions_per_chunk` × `max_number_of_calls` (3);
   a small PR is a single chunk, so only one call runs.

### Empirical isolation (PR with ~100 lines of changed Python, CLI/OAuth handler)

Three committable runs, varying one factor at a time, counting **only** the
inline comments each run posted:

| Run | `num_code_suggestions_per_chunk` | `focus_only_on_problems` | inline posted |
|---|---|---|---|
| 1 | 3 | true | 2 |
| 2 | **8** | true | 3 |
| 3 | 8 | **false** | 4 |

Findings:

- **The ceiling was never binding.** Every run produced *fewer* suggestions than
  its ceiling (2 and 3 under a cap of 3/8). Raising 3 → 8 did **not** unlock more.
- **Each lever moved the count by ~±1** — within run-to-run **non-determinism**.
  The *sets* barely overlapped across runs (different files/lines each time); what
  changes between runs is **which** findings, more than **how many**.
- On a **small/clean PR the binding factor is supply** (how many real issues exist)
  **plus non-determinism**, not the config. `focus_only_on_problems = false` adds
  roughly one marginal nit.
- The genuine driver of higher volume is a **larger PR** (more changed code → more
  chunks → more real issues), not the ceiling.

### Knobs (still useful, with realistic expectations)

| Goal | Knob | Note |
|---|---|---|
| Raise the ceiling | `pr_code_suggestions.num_code_suggestions_per_chunk` ↑ | The **correct** key for `/improve`. A ceiling only — won't add volume when supply is below it. |
| Include style/nits | `pr_code_suggestions.focus_only_on_problems = false` | More volume, more noise (~+1 on small PRs). |
| Keep low-score ones | lower `pr_code_suggestions.suggestions_score_threshold` | Already `0` by default (minimal). |
| Cover bigger diffs | `pr_code_suggestions.max_number_of_calls` ↑ | More chunks = more LLM calls = more latency/cost. Helps **large** PRs. |

> The inline-anchoring filter (#4) cannot be relaxed without re-introducing HTTP
> 422 errors — it exists precisely to keep committable comments on valid diff lines.
>
> The GitHub Copilot reviewer posts more comments because it has no per-chunk
> ceiling **and** a liberal review-style design — a different philosophy
> (quantity) from `/improve` (curated, score-gated).
