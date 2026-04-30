from __future__ import annotations

import copy
import os
from datetime import datetime
from pathlib import Path

import yaml

STEPS = ["context", "spec", "tests", "code", "run-tests", "review", "merge"]

WORKFLOW_FILENAME = {
    "context": "context",
    "spec": "spec",
    "tests": "tests",
    "code": "code",
    "run-tests": "run_tests",
    "review": "review",
    "merge": "merge",
}

_DEFAULT_MANIFEST = {
    "current_step": "context",
    "step_statuses": {step: "pending" for step in STEPS},
    "history": [],
}


class StateError(Exception):
    pass


def _manifest_path(project_root: Path) -> Path:
    return project_root / ".claude" / "workflow" / "manifest.yaml"


def _step_path(project_root: Path, step_name: str) -> Path:
    if step_name not in WORKFLOW_FILENAME:
        raise StateError(f"Unknown step '{step_name}'")
    filename = WORKFLOW_FILENAME[step_name]
    return project_root / ".claude" / "workflow" / f"{filename}.md"


def _ensure_dirs(project_root: Path) -> None:
    (project_root / ".claude" / "workflow").mkdir(parents=True, exist_ok=True)


def _validate_manifest(manifest: dict) -> None:
    if "current_step" not in manifest:
        raise StateError("manifest.yaml: missing required field 'current_step'")
    if manifest["current_step"] not in STEPS:
        raise StateError(
            f"manifest.yaml: current_step '{manifest['current_step']}' is not a valid step"
        )

    if "step_statuses" not in manifest:
        raise StateError("manifest.yaml: missing required field 'step_statuses'")
    statuses = manifest["step_statuses"]
    if not isinstance(statuses, dict):
        raise StateError("manifest.yaml: step_statuses must be a dict")

    expected_steps = set(STEPS)
    actual_steps = set(statuses.keys())
    if expected_steps != actual_steps:
        raise StateError(
            f"manifest.yaml: step_statuses must have exactly these steps: {', '.join(sorted(STEPS))}"
        )

    valid_status_values = {"pending", "in_progress", "complete"}
    for step, status in statuses.items():
        if status not in valid_status_values:
            raise StateError(
                f"manifest.yaml: step_statuses['{step}'] = '{status}' is invalid; "
                f"expected one of: {', '.join(sorted(valid_status_values))}"
            )

    if "history" not in manifest:
        raise StateError("manifest.yaml: missing required field 'history'")
    if not isinstance(manifest["history"], list):
        raise StateError("manifest.yaml: history must be a list")




def load_manifest(project_root: Path) -> dict:
    path = _manifest_path(project_root)
    if not path.exists():
        return copy.deepcopy(_DEFAULT_MANIFEST)

    try:
        with open(path) as f:
            manifest = yaml.safe_load(f)
    except Exception as e:
        raise StateError(f"Failed to load manifest.yaml: {e}")

    if manifest is None:
        return copy.deepcopy(_DEFAULT_MANIFEST)

    _validate_manifest(manifest)
    return manifest


def save_manifest(project_root: Path, manifest: dict) -> None:
    _validate_manifest(manifest)
    _ensure_dirs(project_root)

    path = _manifest_path(project_root)
    tmp_path = path.with_suffix(".yaml.tmp")

    try:
        with open(tmp_path, "w") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp_path, path)
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        raise StateError(f"Failed to save manifest.yaml: {e}")


def load_step(project_root: Path, step_name: str) -> str:
    path = _step_path(project_root, step_name)
    if not path.exists():
        return ""

    try:
        with open(path) as f:
            content = f.read()
    except Exception as e:
        raise StateError(f"Failed to load {path.name}: {e}")

    return content


def save_step(project_root: Path, step_name: str, content: str) -> None:
    _ensure_dirs(project_root)

    path = _step_path(project_root, step_name)
    tmp_path = path.with_suffix(".md.tmp")

    try:
        with open(tmp_path, "w") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        raise StateError(f"Failed to save {path.name}: {e}")


def mark_backward_navigation(project_root: Path, target_step: str) -> None:
    if target_step not in STEPS:
        raise StateError(f"Unknown step '{target_step}'")

    manifest = load_manifest(project_root)
    target_idx = STEPS.index(target_step)

    manifest["step_statuses"][target_step] = "in_progress"
    for i in range(target_idx + 1, len(STEPS)):
        manifest["step_statuses"][STEPS[i]] = "pending"

    manifest["current_step"] = target_step

    history_entry = {
        "event": "step_revised",
        "step": target_step,
        "timestamp": now_iso(),
    }
    manifest["history"].append(history_entry)
    save_manifest(project_root, manifest)


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"
