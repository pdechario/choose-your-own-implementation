# STORY_CONTEXT.md — Implementation Context Log

**Purpose:** This document records implementation decisions, key patterns, and gotchas from completed stories (S1+). When you know which files you're about to modify, look up their story history here to understand prior decisions and avoid breaking changes. Use this to learn what patterns were established and what deferred work exists.

**Note:** For the design specification and what remains to be built, see [DESIGN.md](DESIGN.md).

---

## Quick Navigation

| Line | Section | Purpose |
|------|---------|---------|
| 9 | [Story Index](#story-index) | Look up stories by file impact and status |
| 18+ | [Story Notes](#story-notes) | Detailed notes per story (S1.2, S1.3, etc.) |

---

## Story Index

| # | Keywords | Primary Files | Upstream | Downstream | Notes |
|---|---|---|---|---|---|
| S1.1 | packaging, deps, pyproject, anthropic sdk | pyproject.toml | — | workflow.py, all steps | — |
| S1.2 | cli, entry point, routing, click | workflow.py | pyproject.toml | steps/*.py, tools.py | [see notes](#s12) |
| S1.3 | state, persistence, manifest, backward navigation | state.py | workflow.py | steps/*.py, models.py | [see notes](#s13) |

---

## Story Notes

### S1.2

`workflow.py` uses Click's `@cli.command()` dispatch pattern — do not switch to Typer without updating the routing logic in S10.1–S10.3, which assume Click's `invoke` API. The tool call loop lives here temporarily; S2.2 moves it to a dedicated module.

### S1.3

`state.py` is a thin persistence layer: `load_manifest`, `save_manifest`, `load_step`, `save_step`, `mark_backward_navigation`, `now_iso`. No content interpretation — step files are opaque markdown strings. Decision objects with IDs are a convention (written by step modules, not parsed by state.py); other object types (test failures, etc.) will follow.

**Breaking change:** `workflow.py`'s step module contract changed from `run(client, state)` to `run(client, project_root, manifest)`. All future step implementations (context, spec, tests, etc.) must use the 3-arg signature.

**Design notes:** Uses `copy.deepcopy()` for manifest defaults to prevent mutation bleed across calls. Backward navigation cascades statuses and appends history; impact analysis generation deferred to a later story.
