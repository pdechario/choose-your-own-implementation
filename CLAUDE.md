## Quick Navigation

| Line | Section | Purpose | Files |
|------|---------|---------|-------|
| 17 | [Project Overview](#project-overview) | What this tool does | DESIGN.md |
| 33 | [Foundation](#foundation) | CLI scaffold, state machine, config | workflow.py, state.py, models.py |
| 51 | [Tool Definitions](#tool-definitions) | SDK tool schemas, call loop | tools.py |
| 76 | [Workflow Steps](#workflow-steps) | The 7 bidirectional steps | steps/*.py, prompts/*.md |
| 111 | [Token Optimization](#token-optimization) | Cost reduction strategies | (cross-cutting) |
| 132 | [GitHub Integration](#github-integration) | KANBAN sync to Issues | .github/scripts/sync_kanban.py, KANBAN.md |
| 175 | [Story Context](#story-context) | Prior implementation decisions, file-to-story lookup | STORY_CONTEXT.md |
| 212 | [Local Development](#local-development) | Python version, local testing setup | (all test scripts) |

Line numbers in this table are file line numbers. Use `Read` with `offset: <line>` to jump directly to a section. Update these numbers when sections are added or moved.

---

## Project Overview

**choose-your-own-implementation** is a Python CLI tool that guides software development through a structured, spec-driven workflow. Users choose their own adventure through 7 steps, each refining the prior output. The tool uses the Anthropic SDK directly — no frameworks, no delegation.

**When to read DESIGN.md in full:** You're implementing a new step, optimizing token usage, or need to understand why a design decision was made. Otherwise, reference it for specifics.

**State machine (bidirectional):**
```
context ↔ spec ↔ tests ↔ code ↔ run-tests ↔ review ↔ merge
```
Users can move forward, revise a prior step (which invalidates downstream steps), or iterate within a step before approving.

- Future implementation should involve not invalidating downstream steps. The user should advise what changes will be made and claude will do that for them. 

---

## Foundation

**Summary:** Core CLI setup, state persistence, model selection.

**Key files:**
- `workflow.py` — Entry point (`python workflow.py step <name>`); uses Click's `@cli.command()` dispatch; currently orchestrates the tool call loop (moves to dedicated module in S2.2)
- `state.py` — Read/write `.claude/workflow/*.json` as opaque strings; no content interpretation; mark downstream steps `pending` on backward navigation
- `models.py` — Select Haiku vs Sonnet per step; auto-escalate on divergence/failure; configure prompt caching headers

**Scope:** Minimal. Workflow.py routes to step modules via Click; state.py is a thin opaque read/write layer. Models.py maps steps to (model, system_prompt_path).

**Step module contract (S1.3):** All step modules use signature `run(client, project_root, manifest)` (changed from `run(client, state)` in S1.3).

**When to dive deep:**
- Fixing bugs in state transitions (backward navigation cascades statuses and appends history; see S1.3 notes)
- Adding a new step (register in models.py; implement as `run(client, project_root, manifest)`)
- Tuning model escalation rules or changing a step's model tier
- Understanding state.py: reads/writes opaque JSON strings; decision objects with IDs are a convention written by steps (see S1.3)

---

## Tool Definitions

**Summary:** Anthropic SDK tool schemas that steps declare and Python executes.

**Key file:** `tools.py`

**Tools:**
- `read_file` — Read a file from disk (all steps)
- `run_bash` — Execute shell commands (code steps, test execution, git ops)
- `git_diff` — Get diff between HEAD and working tree (review step)
- `list_directory` — Traverse codebase (context step, broad exploration)

**Call loop:** Implemented in `workflow.py`. When a step returns `tool_use` stop reason:
1. Extract tool name and input
2. Execute the tool (Python handles the call)
3. Feed result back to Claude in a new message
4. Repeat until Claude emits final output or stop reason changes

**When to dive deep:**
- Adding a new tool (define schema, implement execution, wire into call loop)
- Debugging tool input/output mismatch
- Changing tool error handling or timeouts

---

## Workflow Steps

**Summary:** Seven steps that form a bidirectional linked list. Each step reads prior state, calls Claude with tools, iterates on feedback, writes output JSON.

**Step structure:**
- Input: Reads selective fields from prior JSONs (token efficiency)
- Process: Calls Anthropic SDK; runs refinement loop (feedback → refine → approval)
- Output: Writes `{step}.json` to `.claude/workflow/`
- State: Recorded in `workflow.json` (current step, statuses, history)

**The steps:**

| Step | Model | Purpose | Reads | Outputs |
|------|-------|---------|-------|---------|
| context | Haiku | Explore problem space | — | context.json (problem, affected files, constraints, options) |
| spec | Sonnet | Make design decisions | context | spec.json (chosen approach, data models, edge cases) |
| tests | Sonnet | Plan test strategy | context + spec | tests.json (unit/integration/e2e test cases, mocking needs) |
| code | Sonnet | Plan implementation | context + spec | code.json (tasks, files to touch, functions, new deps) |
| run-tests | Haiku (→ Sonnet) | Execute & parse tests | tests | run_tests.json (pass/fail counts, failures, suggested fixes) |
| review | Haiku (→ Sonnet) | Pre-commit checks | spec + tests + code + run_tests + git diff | review.json (linting status, spec adherence, blockers, commit msg) |
| merge | Haiku | Finalize & document | all prior | merge.json (changelog, docs updates, PR description, stale TODOs) |

**Files:**
- `steps/{context,spec,tests,code,run_tests,review,merge}.py` — Step logic
- `prompts/{context,spec,tests,code,run_tests,review,merge}.md` — System prompts (use `cache_control` header)

**When to dive deep:**
- Implementing a step (read its section in DESIGN.md; see **The 7 Steps**)
- Debugging a step's output (check the system prompt; verify it reads the right prior state)
- Adding a within-step iteration feature (all steps have a refinement loop; it's consistent)

**Key pattern:** Each step is independent. To add a new step or modify one, you only need to change that step's .py file and .md prompt — the foundation handles the rest.

---

## Token Optimization

**Summary:** Techniques to keep costs low across long refinement loops and large codebases.

**Strategies:**

1. **Selective field injection** — Each step reads only the fields it needs from prior JSONs (defined in the step's .py file). E.g., `code` step reads `context.problem_statement` and `spec.data_models`, but not `spec.open_items`.

2. **Prompt caching** — System prompts (in `prompts/*.md`) are large and stable. They use `cache_control` header in `models.py`. Within-step iterations (user feedback → refine → loop) reuse the cached system prompt.

3. **Model tiering** — Haiku for fast/cheap tasks (exploration, mechanical parsing); Sonnet for reasoning (design, edge cases). See table above.

4. **Summarization hook** — If a prior JSON exceeds a threshold (e.g., 8000 tokens), summarize it with Haiku before injecting. Implemented in `state.py` or the step's .py file.

**When to dive deep:**
- Measuring cache hit rates (check Anthropic API logs after a full workflow)
- Tuning token thresholds for summarization
- Adding selective fields to a step (modify the step's field-reading logic)

---

## GitHub Integration

**Summary:** KANBAN.md is the source of truth. A GitHub Actions workflow syncs it to Issues, updating checkboxes and closing issues.

**How it works:**
1. Developer marks a story `done` in `KANBAN.md`
2. Commit to `main`
3. GitHub Actions triggers on KANBAN.md changes
4. `.github/scripts/sync_kanban.py` runs:
   - Parses KANBAN.md (regex + line-by-line)
   - Fetches current epic-labeled Issues
   - Calls Claude Haiku to generate issue body from epic/story data
   - PATCHes each issue; auto-closes when all stories are `done`

**KANBAN.md format (strict — required for the sync script):**
```markdown
## Epic {N} — {Title}

> {description}

**Sequencing:** {note}  ← optional

## Stories

| # | Story | Status |
|---|-------|--------|
| S{N}.{M} | {story text} | `{status}` |
```

Valid statuses: `todo`, `in_progress`, `done`.

**Files:**
- `KANBAN.md` — Work tracking (linked to GitHub Issues)
- `.github/scripts/sync_kanban.py` — Parser + Issue syncer
- `.github/workflows/sync-kanban.yml` — GitHub Actions trigger

**When to dive deep:**
- Modifying the sync script (understand the markdown table parsing; test on a real KANBAN.md)
- Adding fields to KANBAN.md (keep the table format; update the regex parser)
- Linking a workflow run to a story (pass `github_reference` at context step invocation; `merge` step updates KANBAN.md)

---

## Story Context

**Summary:** Per-story implementation log. Captures which files each story touched, what it depended on, what depends on it, and any key decisions or gotchas from implementation.

**File:** `STORY_CONTEXT.md`

**When to use it:**
- You know which files you are about to read or modify
- You want to know if a prior story already touched those files and what decisions it made there
- You are debugging unexpected behavior in a file and want to know its implementation history

**How to use it:**
1. Identify the files you are about to impact (from the user's request or your codebase exploration)
2. Open `STORY_CONTEXT.md` and search for those filenames in the Primary Files, Upstream, or Downstream columns
3. For any matching story, read its Notes section (linked from the table) before proceeding

**What not to do:**
- Do not read this file automatically at session start
- Do not traverse every row — look up by file name, not by story order
- Do not consult this file unless you have a concrete file or story ID in mind

**How to update it:**
When a story is complete, add a row to the table. If there is a non-obvious decision, pattern, or gotcha, add a `### S{N}.{M}` section below the table and link to it from the Notes column. If nothing is noteworthy, put `—` in Notes.

---

## Key Design Decisions

1. **No framework dependency**: The tool is a standalone Python script using the Anthropic SDK directly.
2. **Tool definitions in Python**: Anthropic SDK tool schemas are defined in Python, not delegated to Claude Code — gives full control over execution and error handling.
3. **Within-step iteration**: Users refine each step before moving forward; JSON is written only on approval. This prevents wasted downstream work.
4. **Backward navigation with invalidation**: When going back from step N to step M, all downstream steps are marked `pending` — this ensures consistency.
5. **Selective field injection**: Each step only reads the prior state it needs. This keeps token usage low and makes the data flow explicit.

## Local Development

**Python version:** Always use `python3` when running scripts locally (not `python`). The `python` alias may not exist or may point to Python 2.x. Local test scripts should use `python3 script_name.py`.

---

## Testing & Verification

Once a step is complete, verify it against the checklist in DESIGN.md → **The 7 Steps** (each step has a Verify section).

Key integration test: run a full workflow end-to-end on a real small feature; inspect `.claude/workflow/` for correctly written JSON; check Anthropic API logs for model tiers and cache hit rate.

## References

- [DESIGN.md](DESIGN.md) — comprehensive design spec with open questions and first steps
- [KANBAN.md](KANBAN.md) — epics and stories, linked to GitHub Issues
- [.github/scripts/sync_kanban.py](./github/scripts/sync_kanban.py) — GitHub sync script

## End Sections for Claude

## Future Work

**S1.3 Deferred (per notes):**
- Impact analysis generation deferred to a later story (currently backward navigation just cascades statuses)

**Tool call loop (S1.2):**
- Currently in `workflow.py`; scheduled to move to dedicated module in S2.2
