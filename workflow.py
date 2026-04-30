from __future__ import annotations

import importlib
import sys
from pathlib import Path

import anthropic
import click
from dotenv import load_dotenv

import state

load_dotenv()

STEPS = [
    "context",
    "spec",
    "tests",
    "code",
    "run-tests",
    "review",
    "merge",
]

_MODULE_MAP: dict[str, str] = {
    "context": "context",
    "spec": "spec",
    "tests": "tests",
    "code": "code",
    "run-tests": "run_tests",
    "review": "review",
    "merge": "merge",
}


@click.group()
def cli() -> None:
    """choose-your-own-implementation workflow tool.

    Guide software development through a 7-step spec-driven workflow.
    """


@cli.command()
@click.argument("name", metavar="<step-name>")
def step(name: str) -> None:
    """Run a workflow step by name.

    Valid steps (in order): context, spec, tests, code, run-tests, review, merge
    """
    if name not in _MODULE_MAP:
        click.echo(
            f"Unknown step '{name}'. Valid steps: {', '.join(STEPS)}",
            err=True,
        )
        sys.exit(1)

    module_name = _MODULE_MAP[name]

    try:
        step_module = importlib.import_module(f"steps.{module_name}")
    except ModuleNotFoundError:
        click.echo(f"Step '{name}' is not implemented yet.", err=True)
        sys.exit(1)

    client = anthropic.Anthropic()
    project_root = Path.cwd()

    try:
        manifest = state.load_manifest(project_root)
    except state.StateError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    step_module.run(client, project_root, manifest)


if __name__ == "__main__":
    cli()
