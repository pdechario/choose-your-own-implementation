# STORY_CONTEXT.md — Implementation Context Log

One row per story. Look this file up when you know which files are about to be touched and want to find prior stories that affected those files. Do not traverse this file on session start — use it on-demand.

| # | Keywords | Primary Files | Upstream | Downstream | Notes |
|---|---|---|---|---|---|
| S1.1 | packaging, deps, pyproject, anthropic sdk | pyproject.toml | — | workflow.py, all steps | — |
| S1.2 | cli, entry point, routing, click | workflow.py | pyproject.toml | steps/*.py, tools.py | [see notes](#s12) |

---

## S1.2

`workflow.py` uses Click's `@cli.command()` dispatch pattern — do not switch to Typer without updating the routing logic in S10.1–S10.3, which assume Click's `invoke` API. The tool call loop lives here temporarily; S2.2 moves it to a dedicated module.
