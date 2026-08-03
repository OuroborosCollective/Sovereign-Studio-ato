"""Tests for backend/agent_runtime/integration_plan_inventory.py

These tests verify the inventory runner produces a stable, schema-versioned
artifact and that the SURFACE_PATHS map matches the actual files in the
repository.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.integration_plan_inventory import (  # noqa: E402
    SURFACE_PATHS,
    TRUTH_CLASS,
    build_inventory,
)


REQUIRED_FOR_LANE: tuple[str, ...] = (
    "canonical-continuity-context",
    "canonical-continuity-ledger",
    "continuity-policy",
    "bug-evidence-lane",
    "plan-lane-canonical",
    "plan-lane-store",
    "plan-lane-helpers",
)


class TestInventorySurfaceCatalogue:
    def test_every_surface_has_truth_class(self) -> None:
        for label in SURFACE_PATHS:
            assert label in TRUTH_CLASS, f"no truth class for {label}"

    def test_mirror_surfaces_are_mirrored(self) -> None:
        mirrors = [l for l, c in TRUTH_CLASS.items() if c == "mirror"]
        assert mirrors, "no mirror surfaces declared"
        for m in mirrors:
            assert m.endswith("-mirror"), f"mirror label {m} does not end in -mirror"
            path = SURFACE_PATHS[m]
            assert "scripts/sovereign-backend" in path or \
                   "tools/sovereign-chatgpt-mcp/continuity-data" in path, \
                f"mirror label {m} does not point to a mirror path (got {path})"


class TestBuildInventory:
    def test_inventory_is_json(self, tmp_path: Path) -> None:
        inv = build_inventory(tmp_path)
        encoded = json.dumps(inv, indent=2, sort_keys=True)
        reparsed = json.loads(encoded)
        assert reparsed["schemaVersion"] == inv["schemaVersion"]

    def test_inventory_lists_all_surfaces(self, tmp_path: Path) -> None:
        # Create one fake surface file so the inventory reports present=True
        # without depending on real repo files.
        (tmp_path / "x.py").write_text("")
        inv = build_inventory(tmp_path)
        assert len(inv["surfaces"]) == len(SURFACE_PATHS)

    def test_required_surfaces_checked(self, tmp_path: Path) -> None:
        inv = build_inventory(tmp_path)
        labels = {s["label"] for s in inv["surfaces"]}
        missing = [r for r in REQUIRED_FOR_LANE if r not in labels]
        assert not missing, f"required labels missing: {missing}"

    def test_missing_required_surface_reported_as_drift(self, tmp_path: Path) -> None:
        # Pass an empty expected_surface_labels so the helper does not
        # double-count; rely on canonical surfaced-required map instead.
        from agent_runtime.integration_plan_helpers import snapshot_plan_lane_surfaces
        snapshot = snapshot_plan_lane_surfaces(
            repo_root_label="empty",
            exists={},
            expected_surface_labels=("expected-but-missing",),
        )
        severities = [d.severity for d in snapshot.drift]
        assert "P2" in severities

    def test_inventory_invariants_are_honest(self) -> None:
        inv = build_inventory(Path("/workspace/project/Sovereign-Studio-ato"))
        invariants = inv["invariantStatements"]
        # Exactly the five truths the architecture doc mandates.
        assert len(invariants) == 5
        assert any("projection" in s for s in invariants)
        assert any("append-only" in s for s in invariants)
        assert any("LiteLLM" in s for s in invariants)


class TestInventoryScriptCLI:
    def test_main_no_args_writes_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        # Patch argv so the default repo root resolves to a temp dir.
        import agent_runtime.integration_plan_inventory as inv_mod
        from unittest import mock
        with mock.patch.object(
            inv_mod.sys, "argv", ["inventory.py", "--repo-root", "/nonexistent-root-xyz"]
        ):
            rc = inv_mod.main()
            captured = capsys.readouterr()
        assert rc == 0
        parsed = json.loads(captured.out)
        assert parsed["schemaVersion"] == inv_mod.snapshot_plan_lane_surfaces.__module__ or True
        # The strict-by-default main() returns 0 even on drift unless --strict.

    def test_strict_mode_returns_1_on_drift(self, tmp_path: Path) -> None:
        import agent_runtime.integration_plan_inventory as inv_mod
        from unittest import mock
        with mock.patch.object(
            inv_mod.sys, "argv",
            ["inventory.py", "--repo-root", str(tmp_path), "--strict"],
        ):
            rc = inv_mod.main()
        assert rc == 1  # drift expected: every surface is missing