# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Navigation

| Section | Purpose | Files |
|---------|---------|-------|
| [Project Overview](#project-overview) | What this tool does | DESIGN.md |
| [Foundation](#foundation) | CLI scaffold, state machine, config | workflow.py, state.py, models.py |
| [Tool Definitions](#tool-definitions) | SDK tool schemas, call loop | tools.py |
| [Workflow Steps](#workflow-steps) | The 7 bidirectional steps | steps/*.py, prompts/*.md |
| [Token Optimization](#token-optimization) | Cost reduction strategies | (cross-cutting) |
| [GitHub Integration](#github-integration) | KANBAN sync to Issues | .github/scripts/sync_kanban.py, KANBAN.md |

---

## Project Overview

**choose-your-own-implementation** is a Python CLI tool that guides software development through a structured, spec-driven workflow. Users choose their own adventure through 7 steps, each refining the prior output. The tool uses the Anthropic SDK directly — no frameworks, no delegation.

**When to read DESIGN.md in full:** You're implementing a new step, optimizing token usage, or need to understand why a design decision was made. Otherwise, reference it for specifics.

**State machine (bidirectional):**
```
context ↔ spec ↔ tests ↔ code ↔ run-tests ↔ review ↔ merge
```
Users can move forward, revise a prior step (which invalidates downstream steps), or iterate within a step before approving.

---

## Foundation

**Summary:** Core CLI setup, state persistence, model selection.

**Key files:**
- `workflow.py` — Entry point (`python workflow.py step <name>`); orchestrates the tool call loop
- `state.py` — Read/write `.claude/workflow/*.json`; enforce schemas; mark downstream steps `pending` on backward navigation
- `models.py` — Select Haiku vs Sonnet per step; auto-escalate on divergence/failure; configure prompt caching headers

**Scope:** Minimal. Workflow.py routes to step modules; state.py is a thin read/write layer. Models.py maps steps to (model, system_prompt_path).

**When to dive deep:**
- Fixing bugs in state transitions (backward navigation, pending invalidation)
- Adding a new step (need to register in models.py)
- Tuning model escalation rules or changing a step's model tier

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

## Key Design Decisions

Why these choices?

1. **No framework dependency** — Standalone Python script + Anthropic SDK. Lightweight, open-sourceable, easier to audit.

2. **Tool definitions in Python** — Not delegated to Claude Code. Gives full control over execution, error handling, timeouts.

3. **Within-step iteration** — Users refine each step before moving forward. JSON is written only on approval. Prevents wasted downstream work.

4. **Backward navigation with invalidation** — Going back from step N to M marks M as `in_progress` and all downstream steps as `pending`. Ensures consistency; prevents stale state.

5. **Bidirectional workflow** — Users can move forward, revise a prior step, or iterate. Not a rigid pipeline.

6. **Selective field injection** — Each step only reads what it needs. Makes data flow explicit; keeps tokens low.

---

## Testing & Verification

**Per-step:** See DESIGN.md → **The 7 Steps**. Each step has a Verify section (e.g., "Run `python workflow.py step context` on a real small feature; confirm `context.json` is written with correct schema").

**Integration:** Run a full workflow end-to-end on a real feature. Check:
- `.claude/workflow/` has all 7 JSON files with correct schema
- Anthropic API logs show correct model tiers and cache hit rate
- Backward navigation invalidates downstream steps
- Within-step iteration refines without writing prematurely
- KANBAN.md sync updates the corresponding GitHub Issue

**When to dive deep:** Implementing a new step; troubleshooting state transitions; tuning token optimization.

---

## Where to Look

| Question | Answer |
|----------|--------|
| How do I run the tool? | `python workflow.py step <name>` — see **Foundation** |
| What does a step do? | See **Workflow Steps** table + DESIGN.md → **The 7 Steps** |
| How do I add a new step? | Register in models.py; create steps/{name}.py and prompts/{name}.md |
| How does state persist? | `.claude/workflow/*.json` — see state.py |
| How does backward navigation work? | state.py marks target step `in_progress`, downstream `pending` |
| Why does the review step call Sonnet sometimes? | It escalates from Haiku to Sonnet if divergences are found; see models.py |
| How do I optimize token usage? | See **Token Optimization** section |
| How does KANBAN.md sync to GitHub? | See **GitHub Integration** section |
| Where's the full design? | DESIGN.md — architectural decisions, open questions, first steps |
