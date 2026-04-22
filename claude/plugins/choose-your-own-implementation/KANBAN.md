# choose-your-own-implementation — Kanban Epics

Each epic is a self-contained vertical slice of work. Stories within an epic are ordered; the verification story at the end of each epic gates the start of dependent epics.

### Data Structure

Epics and stories follow a strict format so the sync script can parse them reliably. **Do not deviate from this structure.**

**Epic heading**
```
## Epic {N} — {Title}
```

**Epic body**
```
> {one-line description}                     ← required

**Sequencing:** {note}                        ← optional

## Stories

| # | Story | Status |
|---|-------|--------|
| S{N}.{M} | {story text} | `{status}` |
```

**Valid status values**

| Value | Meaning |
|-------|---------|
| `todo` | Not started |
| `in_progress` | Actively being worked |
| `done` | Complete — triggers GHA sync to check the box in GitHub Issues |

**Rules**
- Story IDs must follow `S{epic_number}.{story_number}` exactly (e.g. `S3.2`)
- The description blockquote (`>`) is required on every epic
- Status must be one of the three values above — any other value is ignored by the sync script
- Story table rows are split on ` | ` (space-pipe-space) — avoid pipes in story text

---

### Two-phase structure (steps 3–9)

Each workflow step has two phases:
1. **Plan phase** — Claude reasons, produces JSON, user iterates until approval. JSON is the source of truth.
2. **Execute phase** — Claude reads the approved JSON and writes actual files (test code, implementation, docs). Nothing is written to disk until the plan is approved.

Steps that are plan-only (`context`, `spec`, `run-tests`) have no execute phase — their output is the JSON itself.

---

## Sequencing

```
Epic 1 (Foundation) → Epic 2 (Tools) → Epics 3–9 (Steps, in order)
                                      ↘ Epic 10 (Navigation, starts after Epic 3)
Epics 11–13 start once core steps work (can run in parallel with each other)
```

---

## Epic 1 — Foundation & CLI Scaffold

> Get the repo installable and the CLI routing working. Everything else blocks on this.

| # | Story | Status |
|---|-------|--------|
| S1.1 | Init `pyproject.toml` with deps: `anthropic`, `click`, `python-dotenv` | `todo` |
| S1.2 | Implement `workflow.py` — CLI entry; `python workflow.py step <name>` routes to the right step module | `todo` |
| S1.3 | Implement `state.py` — read/write `.claude/workflow/*.json`; enforce schema; mark downstream steps `pending` on backward navigation | `todo` |
| S1.4 | Implement `models.py` — model selection per step + auto-escalation rules (Haiku → Sonnet on failures/divergences) | `todo` |
| S1.5 | **Verify:** `python workflow.py --help` works; `state.py` round-trips a JSON file correctly | `todo` |

---

## Epic 2 — SDK Tool Definitions

> Define the tools Claude will call in each step. Python implements the call loop; Claude declares which tool to use.

| # | Story | Status |
|---|-------|--------|
| S2.1 | Implement `tools.py` — `read_file`, `run_bash`, `git_diff` as Anthropic SDK tool schemas | `todo` |
| S2.2 | Implement tool call loop in `workflow.py` — handle `tool_use` stop reason, execute, feed result back | `todo` |
| S2.3 | Add `list_directory` tool for broad codebase traversal (used by `context` step) | `todo` |
| S2.4 | **Verify:** call a model with `read_file`; confirm Python receives, executes, and returns the result correctly | `todo` |

---

## Epic 3 — Step: `context`

> First working end-to-end step. Serves as the template for all subsequent step implementations.

| # | Story | Status |
|---|-------|--------|
| S3.1 | Write `prompts/context.md` — system prompt for codebase exploration, open questions, prototype options | `todo` |
| S3.2 | Implement `steps/context.py` — reads user input, calls Haiku with tools, runs refinement loop, writes `context.json` | `todo` |
| S3.3 | Wire `context` into `workflow.py` routing | `todo` |
| S3.4 | **Verify:** `python workflow.py step context` produces valid `context.json` on a real small feature | `todo` |

---

## Epic 4 — Step: `spec`

| # | Story | Status |
|---|-------|--------|
| S4.1 | Write `prompts/spec.md` | `todo` |
| S4.2 | Implement `steps/spec.py` — reads `context.json` (selective fields), calls Sonnet, writes `spec.json` | `todo` |
| S4.3 | Wire into routing | `todo` |
| S4.4 | **Verify:** `spec.json` resolves open questions from `context.json`; chosen approach and rationale are present | `todo` |

---

## Epic 5 — Step: `tests`

| # | Story | Status |
|---|-------|--------|
| S5.1 | Write `prompts/tests.md` | `todo` |
| S5.2 | Implement `steps/tests.py` — reads `context.json` + `spec.json`, calls Sonnet, writes `tests.json` | `todo` |
| S5.3 | Wire into routing | `todo` |
| S5.4 | **Execute:** write actual test files based on approved `tests.json` — Claude uses `write_file` tool to create test stubs for all cases in the spec | `todo` |
| S5.5 | **Verify:** `tests.json` covers all edge cases listed in `spec.json`; test files exist on disk and fail (red) before `code` step runs | `todo` |

---

## Epic 6 — Step: `code`

| # | Story | Status |
|---|-------|--------|
| S6.1 | Write `prompts/code.md` | `todo` |
| S6.2 | Implement `steps/code.py` — reads `context.json` + `spec.json` (NOT `tests.json`), calls Sonnet, writes `code.json` | `todo` |
| S6.3 | Wire into routing | `todo` |
| S6.4 | **Execute:** write implementation files based on approved `code.json`; Claude reads the test files written by `tests` execute phase as TDD ground truth during implementation | `todo` |
| S6.5 | **Verify:** `code.json` implementation tasks map directly to spec's API contracts; written code makes the test suite go green | `todo` |

---

## Epic 7 — Step: `run-tests`

> Has its own internal decision tree — suite selection and failure branching.

| # | Story | Status |
|---|-------|--------|
| S7.1 | Write `prompts/run_tests.md` | `todo` |
| S7.2 | Implement `steps/run_tests.py` — reads `tests.json`, presents suite selection menu, executes via `run_bash`, cross-references results against `tests.json` spec | `todo` |
| S7.3 | Implement failure branching: [1] go back to `code`, [2] re-run subset, [3] skip and note | `todo` |
| S7.4 | Implement e2e as a separate opt-in prompt: "Run e2e tests now? (~Xm) [y/N]" | `todo` |
| S7.5 | Wire into routing | `todo` |
| S7.6 | **Verify:** run unit tests on a real project; simulate a failure; confirm all three branching options appear and work | `todo` |

---

## Epic 8 — Step: `review`

| # | Story | Status |
|---|-------|--------|
| S8.1 | Write `prompts/review.md` | `todo` |
| S8.2 | Implement `steps/review.py` — reads `spec.json` + `tests.json` + `code.json` + `run_tests.json` + live `git diff`; calls Haiku; escalates to Sonnet on divergences; writes `review.json` | `todo` |
| S8.3 | Wire into routing | `todo` |
| S8.4 | **Execute:** apply any linting fixes from `review.json`; stage files for commit using the drafted commit message | `todo` |
| S8.5 | **Verify:** linting runs, diff reviewed against spec, commit message drafted, blockers list is present; no uncommitted linting fixes remain | `todo` |

---

## Epic 9 — Step: `merge`

| # | Story | Status |
|---|-------|--------|
| S9.1 | Write `prompts/merge.md` | `todo` |
| S9.2 | Implement `steps/merge.py` — reads all prior JSONs, calls Haiku, writes `merge.json` (changelog entry, docs updates, PR description, stale TODO scan) | `todo` |
| S9.3 | Wire into routing | `todo` |
| S9.4 | **Execute:** write `CHANGELOG.md` entry, update docs files, and add/update `CLAUDE.md` section — all based on approved `merge.json` | `todo` |
| S9.5 | **Verify:** `merge.json` contains coherent changelog entry and PR description draft; stale TODO scan runs; written files match the merge plan | `todo` |

---

## Epic 10 — Navigation & CYOA UX

> The "adventure" layer — non-linear flow, backward revision, within-step refinement.

| # | Story | Status |
|---|-------|--------|
| S10.1 | Implement forward navigation — after each step, display: [1] continue → next step [2] revise this step [3] go back [4] exit | `todo` |
| S10.2 | Implement backward navigation — mark target step `in_progress`; mark all downstream steps `pending` | `todo` |
| S10.3 | Implement re-run prompt after backward revision — "Re-run invalidated steps automatically? [y/N/ask each]" | `todo` |
| S10.4 | Implement within-step iteration loop — after output, prompt feedback or approval; loop until approved; write JSON only on approval | `todo` |
| S10.5 | **Verify:** go backward from `spec` to `context`; confirm `spec.json` and later files are marked `pending`; confirm iteration loop refines without writing prematurely | `todo` |

---

## Epic 11 — Token Optimization

| # | Story | Status |
|---|-------|--------|
| S11.1 | Implement selective field injection — each step reads only the fields it needs from prior JSONs (defined per step in `steps/*.py`) | `todo` |
| S11.2 | Implement prompt caching — add `cache_control` header to system prompts in all steps | `todo` |
| S11.3 | Implement summarization hook — if a prior JSON exceeds a token threshold, run a Haiku summarization pass before injecting | `todo` |
| S11.4 | **Verify:** run a full workflow end-to-end; inspect Anthropic API logs for cache hit rate and model usage per step | `todo` |

---

## Epic 12 — Claude Code Integration

> Optional v1 — slash commands in the IDE that invoke the CLI underneath.

| # | Story | Status |
|---|-------|--------|
| S12.1 | Write `plugin.yaml` — define slash commands (`/design-context`, `/design-spec`, etc.) that invoke `python workflow.py step <name>` | `todo` |
| S12.2 | **Verify:** install plugin; run `/design-context` from Claude Code IDE; confirm it routes correctly | `todo` |
| S12.3 | Document integration steps in setup guide | `todo` |

---

## Epic 13 — Distribution & Docs

| # | Story | Status |
|---|-------|--------|
| S13.1 | Write `README.md` — install instructions, `ANTHROPIC_API_KEY` setup, first run walkthrough | `todo` |
| S13.2 | Document `.env` fallback for API key (using `python-dotenv`) | `todo` |
| S13.3 | Run full end-to-end verification on a real project (see Verification section in DESIGN.MD) | `todo` |
| S13.4 | Decide and document distribution path: local editable install (`pip install -e .`) vs PyPI publish | `todo` |
