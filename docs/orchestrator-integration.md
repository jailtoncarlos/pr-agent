# Using PR-Agent as the review engine behind an orchestrator

PR-Agent is a **review producer**: given a PR diff, it generates findings,
inline suggestions, a description, labels, etc. It is **stateless** — one command,
one run, publish, done. It does **not** own the PR lifecycle (lock, rebase, CI
gating, processing the reviewer's comments, merge policy).

A complementary pattern is an **orchestrator** that owns that lifecycle and calls
a review producer as one step. This note documents that split using a concrete,
real-world orchestrator as the worked example: the **forje `pr-review`
finite-state machine** (a 35-state FSM that drives a PR from lock to merge gate).
The mapping is generic — any orchestrator (an FSM, a CI pipeline, a bot) can use
PR-Agent the same way.

## The two roles

| Role | Responsibility | Examples |
|---|---|---|
| **Review producer** | Read the diff → emit findings/suggestions inline | GitHub Copilot reviewer · **PR-Agent (this fork)** · forje `LOCAL_AI_REVIEW` |
| **Orchestrator** | Lock → rebase → CI → *request a review* → **consume** it (classify / fix / reply / resolve) → label → merge gate | forje `pr-review` FSM · a CI workflow · a custom bot |

PR-Agent fills the **producer** role. It is intentionally not an orchestrator.

## Where PR-Agent plugs into the forje FSM (3 phases)

The forje `pr-review` FSM reviews a PR in three phases. PR-Agent maps onto the
**producer** slot of the first two:

1. **Solicit & wait (primary reviewer).** `REQUEST_COPILOT_REVIEW` →
   `WAITING_COPILOT` asks GitHub Copilot and polls for inline comments / a review.
   *PR-Agent could replace Copilot here* — the orchestrator triggers PR-Agent
   (`/review`, `/improve`) instead of, or alongside, Copilot.
2. **Produce review (in-house fallback).** If Copilot times out with zero signals,
   `LOCAL_AI_REVIEW` produces the review itself. *This is the slot PR-Agent fits
   most naturally* — a vendor-neutral reviewer running on a subscription
   (`ai_handler=cli`) instead of the Copilot quota.
3. **Consume the review (the orchestrator's own work).** `PROCESSING_COMMENTS →
   FIXING → BATCH_COMMIT → POST_FIXES_REPLY → RESOLVE_THREADS →
   GENERATE_FINDINGS_BLOCK → VALIDATE_REVIEW_MARKERS`: classify each finding
   (accept / dismiss / defer + confidence), apply accepted fixes under a scope
   invariant, reply on every thread, resolve threads, emit a machine-readable
   findings block, and apply the review label. **PR-Agent has no Phase 3** — that
   is the orchestrator's job.

> **Takeaway.** PR-Agent = Phase 1/2 (the producer). The orchestrator owns Phase 3
> (the critical-consumption loop) and the whole lifecycle around it.

## PR-Agent vs. forje `LOCAL_AI_REVIEW` — both are producers, but different

Both take a diff and emit a review. The differences are in **flow, technology, and
technique** (grounded in the code of each):

| Axis | forje `LOCAL_AI_REVIEW` | PR-Agent (this fork) |
|---|---|---|
| **Role/shape** | One **state** inside a larger FSM; **fallback-only** (fires when Copilot is absent) | A **self-contained, stateless** per-command pipeline (`/review`, `/improve`, …) |
| **Diff fitting** | **Line-cap truncation** — `_truncate_diff` at `max_diff_lines` (5000), appends a "[truncated]" note | **Token-aware compression + dynamic context** — `token_handler` (tiktoken), `allow_dynamic_context` expands a hunk up to its enclosing function/class (`max_extra_lines_before_dynamic_context`), `patch_extra_lines_before/after` |
| **Calls per run** | **Single pass** — one `run_prompt(local-review.md.j2)` | **Chunking + multiple async predictions** — `patches_diff_list` split, one `_get_prediction` per chunk, aggregated (`num_code_suggestions_per_chunk`) |
| **Quality passes** | **One pass**, no re-scoring | **Two-pass self-reflection** — `pr_code_suggestions_reflect_prompts.toml` + `self_reflect_on_*` scores suggestions and drops low-score ones (`focus_only_on_problems`) |
| **Resilience** | **Provider failover chain** — tries `claude-cli → codex-cli → …` in order; auth/rate-limit/timeout → next provider; a parse `ValidationError` stops (prompt bug, not provider) | **Model fallback + retries** — `fallback_models`, `ratelimit_retries`, `publish_inline_comments_fallback_with_verification` (422-safe inline) |
| **Human gate** | **Confidence gate** — `avg(confidence) < threshold` → `AWAITING_HUMAN` | **None** — posts and stops (the orchestrator, if any, decides) |
| **Git access** | **`gh` CLI** on a local checkout (`gh pr view` / `gh pr diff`) | **Git-provider SDK/API** — PyGithub / python-gitlab / Bitbucket / Azure / CodeCommit (server-side, multi-platform) |
| **LLM access** | forje provider abstraction — **CLI subscription** (`claude-cli`/`codex-cli`, OAuth) **and** API providers | **LiteLLM** (~100 models via API) **+ this fork's `CliAiHandler`** (CLI subscription, OAuth) |
| **Output typing** | **Pydantic** `LocalReviewOutput` — `confidence ∈ [0,1]`, `severity ∈ {BLOCKER,HIGH,MEDIUM,LOW}` enforced at parse | **YAML** parsed by `load_yaml` with a **retry** on first-parse failure |
| **Governance coupling** | Tightly coupled — emits the forje findings YAML taxonomy + drives label/merge gates | Generic — emits review/suggestions; coupling is whatever the orchestrator adds |

### One-line summary

- **`LOCAL_AI_REVIEW`** optimizes for **governed, resilient fallback inside an
  FSM**: provider failover, a confidence-to-human gate, typed invariants, and a
  findings format the rest of the FSM consumes — but a **simple single-pass,
  truncate-the-diff** producer.
- **PR-Agent** optimizes for **review quality on arbitrary PRs**: token-aware
  compression, dynamic context, chunking, and a self-reflection scoring pass — but
  **stateless**, with no built-in human gate or lifecycle.

They are **complementary, not competing**: drop PR-Agent into the
`LOCAL_AI_REVIEW` (or Copilot) slot to get its diff-handling and quality passes,
and let the FSM keep owning resilience-as-orchestration, the human gate, and the
consumption loop. The convergence point is authentication — **both** can run on a
**chat/CLI subscription over OAuth**, no API key (forje via its `claude-cli`/
`codex-cli` providers; this fork via `CliAiHandler`).

## See also

- `docs/how-it-works-explained.md` — PR-Agent's own flow (producer pipeline).
- `docs/oauth-cli-mode.md` — running PR-Agent on a subscription (the shared
  auth model).
