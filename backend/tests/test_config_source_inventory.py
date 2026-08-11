"""Tests for backend/agent_runtime/configuration/config_source_inventory.py

The inventory runner is the machine-checkable artifact for Issue #1169
acceptance criterion "aktuelle Configquellen, Env-Fallbacks und
Composefl\u00e4chen inventarisieren". It must be stdlib-only, non-mutating and
deterministic for a given repository tree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.configuration.config_source_inventory import (  # noqa: E402
    COMPOSE_GLOBS,
    ENV_SCAN_ROOTS,
    REQUIRED_LABELS,
    SURFACE_PATHS,
    TRUTH_CLASS,
    build_inventory,
    main,
)

REPO_ROOT = ROOT.parent


class TestSurfaceCatalogue:
    def test_every_surface_has_truth_class(self) -> None:
        for label in SURFACE_PATHS:
            assert label in TRUTH_CLASS, f"no truth class for {label}"

    def test_mirror_surfaces_are_mirrored(self) -> None:
        mirrors = [l for l, c in TRUTH_CLASS.items() if c == "mirror"]
        assert mirrors, "no mirror surfaces declared"
        for m in mirrors:
            assert m.startswith("mirror-"), f"mirror label {m} does not start with mirror-"
            path = SURFACE_PATHS[m]
            assert "scripts/sovereign-backend" in path, (
                f"mirror label {m} does not point to a mirror path (got {path})"
            )

    def test_scan_roots_are_relative(self) -> None:
        for root in ENV_SCAN_ROOTS:
            assert not Path(root).is_absolute(), f"{root} must be repo-relative"


class TestBuildInventory:
    def test_inventory_is_valid_json(self, tmp_path: Path) -> None:
        inv = build_inventory(tmp_path)
        encoded = json.dumps(inv, indent=2, sort_keys=True)
        reparsed = json.loads(encoded)
        assert reparsed["schemaVersion"] == inv["schemaVersion"]

    def test_inventory_lists_all_surfaces(self, tmp_path: Path) -> None:
        inv = build_inventory(tmp_path)
        assert len(inv["surfaces"]) == len(SURFACE_PATHS)

    def test_required_surfaces_present_in_labels(self, tmp_path: Path) -> None:
        inv = build_inventory(tmp_path)
        labels = {s["label"] for s in inv["surfaces"]}
        missing = [r for r in REQUIRED_LABELS if r not in labels]
        assert not missing, f"required labels missing: {missing}"

    def test_missing_required_surface_reported_as_drift(self, tmp_path: Path) -> None:
        inv = build_inventory(tmp_path)
        drift_surfaces = {d["surface"] for d in inv["drift"]}
        # On an empty tmp_path every required surface is absent.
        for label in REQUIRED_LABELS:
            assert label in drift_surfaces, f"{label} should be reported as drift"

    def test_snapshot_hash_is_deterministic(self, tmp_path: Path) -> None:
        a = build_inventory(tmp_path)
        b = build_inventory(tmp_path)
        assert a["snapshotSha256"] == b["snapshotSha256"]
        assert len(a["snapshotSha256"]) == 64

    def test_snapshot_hash_excludes_itself(self, tmp_path: Path) -> None:
        inv = build_inventory(tmp_path)
        # Re-derive the hash from the body without the snapshotSha256 field.
        body = dict(inv)
        h = body.pop("snapshotSha256")
        import hashlib
        recomputed = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert h == recomputed


class TestRealRepository:
    def test_required_surfaces_present_on_main(self) -> None:
        inv = build_inventory(REPO_ROOT)
        absent = [s["label"] for s in inv["surfaces"] if not s["present"]]
        required_absent = [l for l in REQUIRED_LABELS if l in absent]
        assert not required_absent, f"required provenance surfaces absent on main: {required_absent}"

    def test_env_fallbacks_discovered(self) -> None:
        inv = build_inventory(REPO_ROOT)
        names = {e["name"] for e in inv["environmentFallbacks"]}
        # These are real env vars read by the backend (see backend-development docs).
        assert "JWT_SECRET" in names
        assert "GIT_SHA" in names

    def test_compose_surfaces_discovered(self) -> None:
        inv = build_inventory(REPO_ROOT)
        compose = {c["relativePath"] for c in inv["composeSurfaces"]}
        # The sovereign-backend mirror compose file must be inventoried.
        assert "scripts/sovereign-backend/docker-compose.yml" in compose
        assert all("__pycache__" not in p for p in compose)

    def test_env_examples_discovered(self) -> None:
        inv = build_inventory(REPO_ROOT)
        examples = {e["relativePath"] for e in inv["envExampleSurfaces"]}
        assert ".env.example" in examples

    def test_no_drift_on_main(self) -> None:
        inv = build_inventory(REPO_ROOT)
        assert inv["drift"] == [], f"unexpected config provenance drift: {inv['drift']}"

    def test_invariants_are_honest(self) -> None:
        inv = build_inventory(REPO_ROOT)
        invariants = inv["invariantStatements"]
        assert len(invariants) == 5
        assert any("read-only resolver" in s for s in invariants)
        assert any("redacted" in s for s in invariants)
        assert any("BLOCKED" in s for s in invariants)
        assert any("byte-identical" in s for s in invariants)


class TestScriptCLI:
    def test_main_no_args_writes_to_stdout(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        from unittest import mock
        with mock.patch.object(
            sys, "argv", ["config_source_inventory.py", "--repo-root", str(tmp_path)]
        ):
            rc = main()
            captured = capsys.readouterr()
        assert rc == 0
        parsed = json.loads(captured.out)
        assert parsed["schemaVersion"] == "sovereign.configuration-sources-snapshot.v1"

    def test_strict_mode_returns_1_on_drift(self, tmp_path: Path) -> None:
        from unittest import mock
        with mock.patch.object(
            sys, "argv",
            ["config_source_inventory.py", "--repo-root", str(tmp_path), "--strict"],
        ):
            rc = main()
        assert rc == 1  # every required surface is missing on an empty tree

    def test_write_emits_artifact(self, tmp_path: Path) -> None:
        from unittest import mock
        target = tmp_path / "docs" / "architecture" / "CONFIGURATION_SOURCES_INVENTORY.json"
        with mock.patch.object(
            sys, "argv",
            ["config_source_inventory.py", "--repo-root", str(tmp_path), "--write"],
        ):
            rc = main()
        assert rc == 0
        assert target.is_file()
        parsed = json.loads(target.read_text(encoding="utf-8"))
        assert parsed["schemaVersion"] == "sovereign.configuration-sources-snapshot.v1"
