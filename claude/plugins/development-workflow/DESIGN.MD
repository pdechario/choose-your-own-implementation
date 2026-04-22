# development-workflow Plugin — Design Spec

A Claude Code plugin that guides software development through a structured, spec-driven workflow. Covers new feature development and bug fixes. Exposes 5 skills (slash commands), each representing a phase. State persists in JSON files so work survives session restarts. Intended to be open-sourced.

---

## How It Works

Each skill is a Claude Code slash command that shells out to a Python CLI (`workflow.py`). Python manages state, selects the model, builds the prompt (injecting only the fields needed from prior steps), calls the Claude API, and writes output JSON. Claude Code itself is just the entry point.

```
Claude Code IDE
    ↓ /design-context
workflow.py step context
    ↓ calls Claude API (model: Haiku)
    ↓ writes .claude/workflow/context.json
    → displays output, prompts user approval / feedback loop

    ↓ /design-spec
workflow.py step spec
    ↓ reads context.json (selective fields only)
    ↓ calls Claude API (model: Sonnet)
    ↓ writes spec.json
    ...and so on
```

---

## Directory Layout

```
claude/plugins/development-workflow/
├── DESIGN.MD                    ← this file
├── plugin.yaml                  ← skill definitions (slash command registry)
├── workflow.py                  ← CLI entry: `python workflow.py step <name>`
├── state.py                     ← read/write .claude/workflow/*.json
├── models.py                    ← model selection + prompt caching config
├── steps/
│   ├── context.py
│   ├── spec.py
│   ├── tests.py
│   ├── review.py
│   └── merge.py
└── prompts/
    ├── context.md               ← prompt template injected at each step
    ├── spec.md
    ├── tests.md
    ├── review.md
    └── merge.md
```

### State Files (live in the project being worked on)

```
<project-root>/.claude/workflow/
├── workflow.json       ← overall state (current step, step statuses, history)
├── context.json        ← output of /design-context
├── spec.json           ← output of /design-spec
├── tests.json          ← output of /design-tests
├── review.json         ← output of /review-iterate-commit
└── merge.json          ← output of /merge
```

---

## Workflow Navigation (Doubly-Linked List)

Steps are a linked list: `context ↔ spec ↔ tests ↔ review ↔ merge`

### Forward (normal)
After each step completes, the orchestrator suggests the next. User confirms before advancing.

### Backward (revision)
Going back from step N to step M:
1. Mark step M as `in_progress`
2. Mark all steps after M as `pending` (invalidated — their JSON is stale)
3. User re-runs step M and approves the new output
4. Orchestrator prompts to re-run each invalidated step in order (or auto-runs them)

### Within-step iteration
Each step runs a refinement loop before writing JSON:
1. Claude produces candidate output
2. User reads it; can provide feedback ("narrow the scope to auth only")
3. Claude refines — same step, same model, prior attempt stays in context
4. Loop exits on user approval (`approve` / `done` / empty enter)
5. JSON is written only on approval

---

## The 5 Skills

### 1. `/design-context`
**Purpose:** Understand the problem space before any design decisions.

**Inputs (user provides at invocation):**
- Brief description of what they want to build or fix
- Optionally: ticket/issue reference

**Claude tasks:**
- Explore the codebase to find affected files, services, utilities
- Identify what must NOT be broken (blast radius)
- Surface ambiguities and open questions
- Propose 2–3 high-level prototype options with tradeoffs

**Output schema — `context.json`:**
```json
{
  "problem_statement": "string",
  "affected_files": ["path/to/file.py"],
  "connected_services": ["ServiceName"],
  "constraints": ["must not break existing session tokens"],
  "open_questions": ["should we support OAuth?"],
  "prototype_options": [
    {
      "name": "Option A",
      "summary": "string",
      "tradeoffs": "string"
    }
  ],
  "step_status": "complete",
  "timestamp": "ISO8601"
}
```

**Model:** `claude-haiku-4-5-20251001` — fast and cheap for codebase exploration

---

### 2. `/design-spec`
**Purpose:** Make explicit design decisions based on the gathered context.

**Reads from:** `context.json` (fields: `problem_statement`, `open_questions`, `prototype_options`, `constraints`)

**Claude tasks:**
- Resolve the open questions from context
- Select one prototype option with justification
- Define data models, API contracts, interfaces
- Note edge cases that must be handled
- Call out anything deferred to a future iteration

**Output schema — `spec.json`:**
```json
{
  "chosen_approach": "Option A",
  "rationale": "string",
  "data_models": {},
  "api_contracts": ["POST /api/foo → { bar: string }"],
  "edge_cases": ["empty payload", "concurrent writes"],
  "out_of_scope": ["pagination"],
  "open_items": [],
  "step_status": "complete",
  "timestamp": "ISO8601"
}
```

**Model:** `claude-sonnet-4-6` — complex reasoning required

---

### 3. `/design-tests`
**Purpose:** Define the test strategy before implementation begins.

**Reads from:** `context.json` + `spec.json` (selective fields)

**Claude tasks:**
- Identify testing levels needed (unit / integration / e2e)
- Generate concrete test case descriptions for happy path and all edge cases from spec
- Flag dependencies that need mocking vs real implementation
- Note what is hard to test and why

**Output schema — `tests.json`:**
```json
{
  "unit_tests": [
    {
      "name": "returns 401 for missing token",
      "target": "src/auth/login.py",
      "notes": "string"
    }
  ],
  "integration_tests": [],
  "e2e_tests": [],
  "mocking_required": ["EmailService"],
  "hard_to_test": ["race condition in session expiry — needs mock clock"],
  "step_status": "complete",
  "timestamp": "ISO8601"
}
```

**Model:** `claude-sonnet-4-6`

---

### 4. `/review-iterate-commit`
**Purpose:** Pre-commit review — catch regressions, version issues, linting issues; draft the commit.

**Reads from:** `spec.json` + `tests.json` + live `git diff`

**Claude tasks:**
- Run linting (via Bash tool)
- Review the diff against the spec (did we implement what we designed?)
- Check for version upgrade concerns (dep bumps, breaking API changes)
- Draft a commit message
- List any blockers that should prevent commit

**Output schema — `review.json`:**
```json
{
  "linting_status": "pass | fail",
  "linting_issues": [],
  "spec_adherence": "full | partial | diverged",
  "divergences": ["added extra param not in spec: reason X"],
  "version_concerns": ["upgraded pydantic 1→2: validators are breaking"],
  "blockers": [],
  "commit_message": "feat: add OAuth login support\n\nLong description...",
  "step_status": "complete",
  "timestamp": "ISO8601"
}
```

**Model:** `claude-haiku-4-5-20251001` for mechanical checks; auto-escalate to `claude-sonnet-4-6` if divergences or blockers are found

---

### 5. `/merge`
**Purpose:** Wrap up — update changelog, docs, Claude context; verify nothing was left behind.

**Reads from:** all prior JSON files

**Claude tasks:**
- Write or append a `CHANGELOG.md` entry
- Update relevant documentation files
- Add/update a `CLAUDE.md` section describing what this change does and where to find it
- Scan for stale TODOs or commented-out code
- Draft PR description

**Output schema — `merge.json`:**
```json
{
  "changelog_entry": "### vX.Y.Z\n- Added OAuth login...",
  "docs_updated": ["docs/auth.md"],
  "claude_md_section": "string",
  "stale_todos": [],
  "pr_description_draft": "string",
  "step_status": "complete",
  "timestamp": "ISO8601"
}
```

**Model:** `claude-haiku-4-5-20251001`

---

## Token Efficiency

| Technique | How |
|-----------|-----|
| Selective injection | Each step reads only the fields it needs from prior JSONs, not the full file |
| Prompt caching | System prompts (step instructions, style guides) use `cache_control` header — stable across iterations |
| Model tiering | Haiku for exploration/mechanical tasks, Sonnet for reasoning (see table below) |
| Summarization hook | If a prior JSON exceeds a token threshold, Python runs a Haiku summarization pass before injecting it |

### Model Tier Table

| Step | Model | Reason |
|------|-------|--------|
| context | `claude-haiku-4-5-20251001` | Fast codebase exploration |
| spec | `claude-sonnet-4-6` | Complex design reasoning |
| tests | `claude-sonnet-4-6` | Deep edge case coverage |
| review | `claude-haiku-4-5-20251001` (default) | Mechanical; escalates to Sonnet on divergence |
| merge | `claude-haiku-4-5-20251001` | Doc formatting |

---

## Open Questions (to resolve before implementation)

1. **Skill invocation mechanism:** How exactly do Claude Code skills call out to Python? Need to verify the YAML skill schema — specifically whether a `command:` field runs `python workflow.py step context` directly or if the prompt itself issues a Bash call.

2. **Distribution:** Does `workflow.py` install globally via pip, or run relative to the plugin directory? Affects how `plugin.yaml` references it and how users set up the plugin.

3. **API key:** The Python orchestrator needs `ANTHROPIC_API_KEY`. Convention: read from env var, fall back to `.env` in project root. Do not use Claude Code's internal credentials.

4. **IDE integration depth:** At minimum, skills appear as slash commands in Claude Code. Richer options (status bar showing current step, side panel) depend on what the Claude Code plugin API supports — investigate after the core workflow works.

---

## First Steps (Implementation Order)

1. Verify Claude Code skill YAML schema — confirm how `command:` works and test a hello-world skill
2. Scaffold `state.py` — the state manager is the foundation everything else depends on
3. Build `/design-context` end-to-end — one working skill as the template for the rest
4. Write `prompts/context.md` — iterate on the prompt with real usage before generalizing
5. Add the remaining 4 skills following the same pattern
6. Implement backward navigation and within-step iteration loop
7. Token optimization pass — selective field injection, prompt caching, summarization hook
8. Write setup docs — install instructions, `ANTHROPIC_API_KEY` config, adding plugin to a project

---

## Verification

- Run `/design-context` on a real small feature; confirm `context.json` is written with correct schema
- Run `/design-spec`; confirm it reads only the needed fields from `context.json` and produces valid `spec.json`
- Navigate backward: re-run `/design-context`, verify all downstream JSONs are marked `pending`
- Test iteration loop: give feedback mid-step, verify Claude refines without writing JSON until approved
- Cost check: run a full workflow end-to-end, inspect API logs for model tiers and cache hit rate
