# choose-your-own-implementation — Design Spec

A Python CLI tool (using the Anthropic SDK directly) that guides software development through a structured, spec-driven workflow. Covers new feature development and bug fixes. Exposes 7 steps, each representing a phase. State persists in JSON files so work survives session restarts. The UX is choose-your-own-adventure style — at each decision point the tool presents branching options rather than a rigid linear pipeline. Intended to be open-sourced.

Claude Code integration (slash commands) is an optional layer on top — the core tool runs standalone from any terminal.

---

## How It Works

`workflow.py` is the entrypoint — a Python CLI that calls the Anthropic SDK directly. It manages state, selects the model per step, builds the prompt (injecting only the fields needed from prior steps), calls `anthropic.Anthropic().messages.create(...)`, and writes output JSON. No Claude Code dependency required.

Tools needed by each step (file reads, bash commands, git diff) are implemented as Anthropic SDK tool definitions — Python handles the tool call loop itself.

```
terminal
    $ python workflow.py step context
    ↓ Anthropic SDK (model: Haiku) + custom tools
    ↓ writes .claude/workflow/context.json
    → displays output, prompts user approval / feedback loop

    $ python workflow.py step spec
    ↓ reads context.json (selective fields only)
    ↓ Anthropic SDK (model: Sonnet)
    ↓ writes spec.json
    ...and so on
```

Claude Code integration is optional: a `plugin.yaml` can register these as slash commands so users can run `/design-context` from the IDE, but the Python CLI works without it.

---

## Directory Layout

```
claude/plugins/development-workflow/
├── DESIGN.MD                    ← this file
├── pyproject.toml               ← package definition, deps (anthropic, click/typer)
├── workflow.py                  ← CLI entry: `python workflow.py step <name>`
├── state.py                     ← read/write .claude/workflow/*.json
├── models.py                    ← model selection + prompt caching config
├── tools.py                     ← Anthropic SDK tool definitions (read_file, run_bash, git_diff)
├── steps/
│   ├── context.py
│   ├── spec.py
│   ├── tests.py
│   ├── code.py
│   ├── run_tests.py
│   ├── review.py
│   └── merge.py
├── prompts/
│   ├── context.md               ← system prompt template for each step
│   ├── spec.md
│   ├── tests.md
│   ├── code.md
│   ├── run_tests.md
│   ├── review.md
│   └── merge.md
└── plugin.yaml                  ← optional: Claude Code slash command definitions
```

### State Files (live in the project being worked on)

```
<project-root>/.claude/workflow/
├── workflow.json       ← overall state (current step, step statuses, history)
├── context.json        ← output of /design-context
├── spec.json           ← output of /design-spec
├── tests.json          ← output of /design-tests
├── code.json           ← output of /design-code
├── run_tests.json      ← output of /run-tests (results + chosen suite)
├── review.json         ← output of /review-iterate-commit
└── merge.json          ← output of /merge
```

---

## Workflow Navigation

Steps are a linked list: `context ↔ spec ↔ tests ↔ code ↔ run-tests ↔ review ↔ merge`

### Choose Your Own Adventure UX

The tool is not a rigid pipeline — at every decision point it presents numbered or lettered options and waits for the user to choose. This applies to:
- Which direction to go (next step, back to revise, skip)
- Which test suite to run in `run-tests`
- How to respond to test failures (fix code, re-run subset, skip and note)
- Whether to run optional substeps (e.g., e2e tests)

The goal is that running the workflow feels engaging and in-control, not like being pushed through a conveyor belt.

### Forward (normal)
After each step completes, the orchestrator presents options like:
```
What next?
  [1] Continue to → run-tests
  [2] Revise this step
  [3] Go back to spec
  [4] Exit and resume later
```

### Backward (revision)
Going back from step N to step M:
1. Mark step M as `in_progress`
2. Mark all steps after M as `pending` (invalidated — their JSON is stale)
3. User re-runs step M and approves the new output
4. Orchestrator presents choices: auto-re-run invalidated steps, or prompt before each

### Within-step iteration
Each step runs a refinement loop before writing JSON:
1. Claude produces candidate output
2. User reads it; can provide feedback ("narrow the scope to auth only")
3. Claude refines — same step, same model, prior attempt stays in context
4. Loop exits on user approval (`approve` / `done` / empty enter)
5. JSON is written only on approval

### Decision Tree: `run-tests`
`run-tests` has its own internal branching — it is not a simple pass/fail:

```
run-tests
├── Choose suite:
│   [1] Unit only (fast)
│   [2] Unit + integration
│   [3] Full suite (includes e2e) ← optional, prompted separately
│   [4] Custom: pick specific test files
│
└── After results:
    ├── All pass → suggest review
    ├── Some fail →
    │   [1] Go back to code step to fix
    │   [2] Re-run only the failing tests
    │   [3] Skip and note failures in review.json
    └── E2e only → separate prompt: "Run e2e tests now? (slow, ~Xm)" [y/N]
```

---

## The 7 Steps

Steps are invoked as `python workflow.py step <name>`. The `/design-*` names are the user-facing aliases (also used as Claude Code slash commands if `plugin.yaml` is installed).

### 1. `context` (`/design-context`)
**Purpose:** Understand the problem space before any design decisions.

**Inputs (user provides at invocation):**
- Brief description of what they want to build or fix
- Optionally: GitHub epic/story reference (e.g. `Epic 6 / S6.2`) — links this run to a tracked story in `KANBAN.md`

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
  "github_reference": { "epic": 6, "story": "S6.2" },
  "step_status": "complete",
  "timestamp": "ISO8601"
}
```

`github_reference` is `null` if no GitHub reference was provided at invocation.

**Model:** `claude-haiku-4-5-20251001` — fast and cheap for codebase exploration

---

### 2. `spec` (`/design-spec`)
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

### 3. `tests` (`/design-tests`)
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

### 4. `code` (`/design-code`)
**Purpose:** Define the implementation plan — which files to touch, what to write, how to structure it.

**Reads from:** `context.json` + `spec.json` (NOT `tests.json` — implementation is derived from the design, not the test strategy)

**Claude tasks:**
- Break the spec down into concrete implementation tasks
- For each task: identify which file(s) to modify or create, what functions/classes/methods to add
- Define function signatures and module interfaces
- Note any new dependencies to add
- Flag anything in the spec that is ambiguous from an implementation standpoint

**Output schema — `code.json`:**
```json
{
  "implementation_tasks": [
    {
      "description": "Add OAuth token validation middleware",
      "files": ["src/auth/middleware.py"],
      "functions": ["validate_oauth_token(token: str) -> User"],
      "notes": "string"
    }
  ],
  "new_dependencies": ["authlib==1.2.1"],
  "implementation_questions": ["Should token refresh be handled here or in the client?"],
  "step_status": "complete",
  "timestamp": "ISO8601"
}
```

**Model:** `claude-sonnet-4-6` — requires reasoning about the codebase structure and spec requirements together

---

### 5. `run-tests` (`/run-tests`)
**Purpose:** Execute the test suite and handle failures before committing.

**Reads from:** `tests.json` — the design-tests spec is the source of truth for correctness. Claude uses it to cross-reference actual results against what was designed: are the tests that were supposed to exist actually present? Are the edge cases from the spec covered? Does a failure indicate a bug in the implementation or a gap in the test design itself?

Does NOT read `code.json` — code quality is assessed by running the tests, not by the implementation plan.

**User chooses at runtime:**
- Which suite to run: unit / unit + integration / full (with e2e) / custom
- E2e tests are prompted separately ("Run e2e? ~Xm [y/N]") — not included by default
- On failure: fix code (loop back to `code` step), re-run subset, or skip with a noted reason

**Claude tasks:**
- Execute the chosen test suite via `run_bash` tool
- Parse test output to extract pass/fail counts, failure messages, and tracebacks
- Cross-reference results against `tests.json`: flag any designed test cases that are missing or untested
- Summarize failures in plain language, noting whether each failure is a code bug or a test design gap
- Record which suites were run and their results

**Output schema — `run_tests.json`:**
```json
{
  "suites_run": ["unit", "integration"],
  "e2e_run": false,
  "results": {
    "unit": {"passed": 42, "failed": 2, "skipped": 1},
    "integration": {"passed": 8, "failed": 0, "skipped": 0}
  },
  "failures": [
    {
      "test": "test_validate_token_expired",
      "file": "tests/auth/test_login.py",
      "message": "AssertionError: expected 401, got 200",
      "suggested_fix": "Token expiry check is missing in validate_oauth_token"
    }
  ],
  "overall_status": "partial_failure | pass | fail",
  "skipped_reason": "null | string (if user chose to skip failures)",
  "step_status": "complete",
  "timestamp": "ISO8601"
}
```

**Model:** `claude-haiku-4-5-20251001` — mechanical test execution and output parsing; escalates to Sonnet if failures need diagnostic reasoning

---

### 6. `review` (`/review-iterate-commit`)
**Purpose:** Pre-commit review — catch regressions, version issues, linting issues; draft the commit.

**Reads from:** `spec.json` + `tests.json` + `code.json` + `run_tests.json` + live `git diff`

**Claude tasks:**
- Run linting (via `run_bash` tool definition)
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

### 7. `merge` (`/merge`)
**Purpose:** Wrap up — update changelog, docs, Claude context; verify nothing was left behind.

**Reads from:** all prior JSON files

**Claude tasks:**
- Write or append a `CHANGELOG.md` entry
- Update relevant documentation files
- Add/update a `CLAUDE.md` section describing what this change does and where to find it
- Scan for stale TODOs or commented-out code
- Draft PR description
- If `context.json` has a `github_reference`, update `KANBAN.md` — set that story's status to `done`

**Output schema — `merge.json`:**
```json
{
  "changelog_entry": "### vX.Y.Z\n- Added OAuth login...",
  "docs_updated": ["docs/auth.md"],
  "claude_md_section": "string",
  "stale_todos": [],
  "pr_description_draft": "string",
  "kanban_updated": true,
  "kanban_story_closed": "S6.2",
  "step_status": "complete",
  "timestamp": "ISO8601"
}
```

**Model:** `claude-haiku-4-5-20251001`

---

## GitHub Integration

The tool optionally links each workflow run to a specific story in `KANBAN.md`, creating a closed loop between doing the work and tracking it.

### How the loop works

```
1. User invokes `context` step with a GitHub reference (e.g. "Epic 6 / S6.2")
2. Reference is stored in context.json and flows through all subsequent steps
3. merge step reads context.json → updates KANBAN.md, setting S6.2 status to "done"
4. KANBAN.md commit triggers the sync-kanban GHA workflow
5. GHA calls Claude Haiku → regenerates issue body → patches GitHub Issue #6 (checkbox checked)
6. When all stories in an epic are done → issue auto-closes
```

### Reference is optional

If no GitHub reference is provided at invocation, `github_reference` is `null` in `context.json` and the `merge` step skips the KANBAN.md update. The tool works fully without GitHub.

### GHA sync script

`.github/workflows/sync-kanban.yml` triggers on pushes to `main` that touch `KANBAN.md`. It runs `.github/scripts/sync_kanban.py`, which:
1. Regex-parses `KANBAN.md` using the data structure contract defined in `KANBAN.md`
2. Fetches current `epic`-labelled GitHub Issues
3. Calls Claude Haiku to generate updated issue bodies from the parsed epic data
4. Patches each issue via the GitHub API; closes issues where all stories are `done`

Requires `ANTHROPIC_API_KEY` to be set as a repo secret.

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
| code | `claude-sonnet-4-6` | Reasoning about codebase structure and spec together |
| run-tests | `claude-haiku-4-5-20251001` (default) | Mechanical test execution; escalates to Sonnet on failures |
| review | `claude-haiku-4-5-20251001` (default) | Mechanical; escalates to Sonnet on divergence |
| merge | `claude-haiku-4-5-20251001` | Doc formatting |

---

## Open Questions (to resolve before implementation)

1. **Tool scope per step:** Which tools does each step need? All steps likely need `read_file` and `run_bash`. Only `context` needs broad file traversal; `review` needs `git_diff`. Define the minimal tool set per step to avoid unnecessary surface area.

2. **Distribution:** Install via `pip install -e .` from the plugin directory, or publish to PyPI? For open-source sharing, PyPI is better UX. For now, local editable install is fine.

3. **API key:** Read `ANTHROPIC_API_KEY` from env var; fall back to `.env` in the project root. Document this clearly in setup instructions.

4. **Claude Code integration:** Verify how `plugin.yaml` should reference the CLI command so slash commands work correctly from the IDE. This is secondary — solve after the CLI works standalone.

---

## First Steps (Implementation Order)

1. Set up `pyproject.toml` with `anthropic` and `click` (or `typer`) as deps; verify a basic SDK call works
2. Scaffold `state.py` — the state manager is the foundation everything else depends on
3. Define `tools.py` — implement `read_file`, `run_bash`, `git_diff` as Anthropic SDK tool definitions
4. Build `context` step end-to-end — one working step as the template for the rest
5. Write `prompts/context.md` — iterate on the system prompt with real usage before generalizing
6. Add the remaining 6 steps following the same pattern
7. Implement backward navigation and within-step iteration loop
8. Token optimization pass — selective field injection, prompt caching, summarization hook
9. Write setup docs — install instructions, `ANTHROPIC_API_KEY` config, optional Claude Code integration

---

## Verification

- Run `python workflow.py step context` on a real small feature; confirm `context.json` is written with correct schema
- Run `python workflow.py step spec`; confirm it reads only the needed fields from `context.json` and produces valid `spec.json`
- Run `python workflow.py step run-tests` — choose unit-only suite, verify `run_tests.json` captures results; simulate a failure and confirm the branching options appear
- Navigate backward: re-run `context` step, verify all downstream JSONs are marked `pending`
- Test iteration loop: give feedback mid-step, verify Claude refines without writing JSON until approved
- Test CYOA prompts: confirm that after each step, the tool presents numbered choices and waits for user input
- Cost check: run a full workflow end-to-end, inspect Anthropic API logs for model tiers and cache hit rate
