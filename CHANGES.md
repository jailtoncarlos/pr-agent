# Fork changes

Changes made in **this fork** relative to upstream
[qodo-ai/pr-agent](https://github.com/qodo-ai/pr-agent) (Apache-2.0).

> **This is the living document of the fork.** Append a new entry here for every
> change you make on top of upstream. Keep `LICENSE` and `NOTICE` intact; this file
> is where "what we changed" is stated (Apache-2.0 §4(b)).

## Unreleased — branch `feat/oauth-cli-ai-handler`

### Added — CLI/OAuth AI handler (run on a chat/CLI subscription, no API key)

- `pr_agent/algo/ai_handlers/cli_ai_handler.py` — **`CliAiHandler`**: drives a
  logged-in subscription CLI (`claude -p` / `codex exec`) in headless mode as the
  LLM provider, instead of an API key. The review runs on the **subscription quota**
  (OAuth) — no API key, no GitHub Copilot quota.
- `pr_agent/agent/pr_agent.py` — `_resolve_ai_handler()` selects the handler via
  `[config] ai_handler` (`"litellm"` default | `"cli"`). Backward-compatible.
- `pr_agent/settings/configuration.toml` — new `[cli_ai]` section
  (`command`, `timeout_seconds`, `pass_prompt_via`) + `[config] ai_handler`.
- `docs/oauth-cli-mode.md` — how to enable, run on CI via a subscription-token
  secret, and known constraints.
- `NOTICE`, `CHANGES.md`, README fork notice — fork attribution / Apache-2.0 hygiene.

### Added — Reusable GitHub Action ([#1](https://github.com/jailtoncarlos/pr-agent/issues/1))

- `action.yml` (composite) — runs the reviewer on a PR. Usable **directly** in a
  single repo (`uses: jailtoncarlos/pr-agent@<sha>`) **or** from an org-anchor
  reusable workflow. Installs the Claude CLI, authenticates via
  `claude_code_oauth_token`, installs this fork, runs the review on the subscription.
- `pr_agent/servers/cli_action_runner.py` — Action entrypoint: selects the CLI
  handler (from env) and runs the standard PR-Agent action flow.
- `docs/examples/single-repo-pr-review.yml` — drop-in workflow for one repo.
- `docs/examples/org-anchor-reusable-workflow.yml` — anchor reusable workflow +
  caller / Organization Ruleset for org-wide governance.

### Changed — port reference-impl (forje) lessons into `CliAiHandler`

- Always send the prompt via **stdin** (removed the `pass_prompt_via` / "arg"
  option): argv overflows `ARG_MAX` on large diffs (`Argument list too long`).
- Add `--skip-git-repo-check` automatically when the command is `codex`, so
  `codex exec` works outside a git repo / in CI (fixes a latent break for the
  cross-model case in [#1](https://github.com/jailtoncarlos/pr-agent/issues/1)).
- All fork-added code comments/docs are in English.

### Changed — defaults

- `[pr_code_suggestions] commitable_code_suggestions = true` (was `false`): by
  default, `/improve` now posts suggestions as **inline line-anchored** comments
  instead of a single summary table. Validated E2E on a real PR (no 422).

### Planned

- End-to-end validation on a real PR — main risk is structured-output reliability
  via the CLI (no API `response_format`).
