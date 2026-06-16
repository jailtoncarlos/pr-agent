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

### Planned

- `action.yml` — package the reviewer as a reusable GitHub Action (tracked in
  [#1](https://github.com/jailtoncarlos/pr-agent/issues/1)).
- Org-wide anchor-governance examples (anchor reusable workflow + Organization
  Ruleset) for applying the reviewer across all repos of an organization.
