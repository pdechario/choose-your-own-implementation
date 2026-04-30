import tempfile
from pathlib import Path

import state


def test_load_manifest_default():
    """Test load_manifest returns default when no file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        manifest = state.load_manifest(root)
        assert manifest["current_step"] == "context"
        assert all(v == "pending" for v in manifest["step_statuses"].values())
        assert manifest["history"] == []


def test_save_and_load_manifest():
    """Test save_manifest and subsequent load."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        manifest = state.load_manifest(root)
        state.save_manifest(root, manifest)
        manifest2 = state.load_manifest(root)
        assert manifest == manifest2


def test_invalid_manifest_status():
    """Test that invalid step_status value is rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        manifest = state.load_manifest(root)
        manifest["step_statuses"]["context"] = "invalid"
        try:
            state.save_manifest(root, manifest)
            assert False, "Should have raised StateError"
        except state.StateError as e:
            assert "invalid" in str(e).lower()


def test_save_and_load_step():
    """Test save_step and load_step with valid content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        content = """# Context

D1: First decision.
D2: Second decision.

## Informed By

- spec:D1 — reference upstream
"""
        state.save_step(root, "context", content)
        loaded = state.load_step(root, "context")
        assert "First decision" in loaded
        assert loaded == content


def test_load_nonexistent_step():
    """Test that loading a nonexistent step returns empty string."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        content = state.load_step(root, "merge")
        assert content == ""


def test_mark_backward_navigation():
    """Test mark_backward_navigation updates statuses correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        state.mark_backward_navigation(root, "spec")
        manifest = state.load_manifest(root)

        assert manifest["step_statuses"]["spec"] == "in_progress"
        assert manifest["step_statuses"]["tests"] == "pending"
        assert manifest["step_statuses"]["code"] == "pending"
        assert manifest["step_statuses"]["run-tests"] == "pending"
        assert manifest["step_statuses"]["review"] == "pending"
        assert manifest["step_statuses"]["merge"] == "pending"
        assert manifest["step_statuses"]["context"] == "pending"
        assert manifest["current_step"] == "spec"
        assert len(manifest["history"]) == 1
        assert manifest["history"][0]["event"] == "step_revised"


def test_default_manifest_isolation():
    """Test that mutating a returned default does not affect subsequent loads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        manifest1 = state.load_manifest(root)
        manifest1["step_statuses"]["context"] = "in_progress"

        manifest2 = state.load_manifest(root)
        assert manifest2["step_statuses"]["context"] == "pending"


def test_now_iso_format():
    """Test now_iso returns properly formatted ISO8601."""
    iso = state.now_iso()
    assert iso.endswith("Z")
    assert "T" in iso
    assert len(iso) > 20
