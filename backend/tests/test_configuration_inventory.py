"""Tests for backend/agent_runtime/configuration_inventory.py.

Issue #1169 acceptance criterion 1: config sources, env fallbacks and compose
surfaces must be inventoried. These tests exercise the real live-path runner
(not a copy of its logic) and cover success, missing-required-surface drift,
compose drift detection, external-by-design exclusion, strict mode, and
determinism.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _find_repo_root() -> Path:
    """Walk up from this test file until we find the dir containing
    backend/agent_runtime and scripts/sovereign-backend. Works identically
    whether the test runs from backend/tests/ or scripts/sovereign-backend/tests/."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "backend" / "agent_runtime").is_dir() and (
            parent / "scripts" / "sovereign-backend"
        ).is_dir():
            return parent
    # Fallback: assume two levels up (canonical location).
    return here.parents[2]


REPO_ROOT = _find_repo_root()
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent_runtime.configuration_inventory import (  # noqa: E402
    COMPOSE_GLOBS,
    REQUIRED_FILE_SURFACES,
    SCHEMA_VERSION,
    SURFACE_CATALOGUE,
    build_inventory,
)


SCHEMA_EXPECTED = "sovereign.configuration-provenance-inventory.v1"
SOURCE_ORDER_EXPECTED = (
    "compiled-defaults",
    "image-manifest",
    "deployment-config",
    "environment-projection",
    "approved-runtime-overlay",
)


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal repo layout so file-backed surfaces are present."""
    (tmp_path / "backend" / "agent_runtime" / "configuration").mkdir(parents=True, exist_ok=True)
    (tmp_path / "backend" / "agent_runtime" / "configuration" / "resolver.py").write_text(
        "# defaults\n"
    )
    (tmp_path / ".env.example").write_text("APP_URL=\n")
    (tmp_path / ".env.sovereign-toolchain.example").write_text("REPO_FULL_NAME=\n")
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "main.ts").write_text("const a = import.meta.env.VITE_FOO;\n")
    return tmp_path


class TestCatalogue:
    def test_schema_version_is_stable(self) -> None:
        assert SCHEMA_VERSION == SCHEMA_EXPECTED

    def test_every_kind_mapped(self) -> None:
        kinds = {s["kind"] for s in SURFACE_CATALOGUE.values()}
        assert set(kinds) == set(SOURCE_ORDER_EXPECTED)

    def test_required_surfaces_are_not_external(self) -> None:
        for label in REQUIRED_FILE_SURFACES:
            spec = SURFACE_CATALOGUE[label]
            assert not spec["external"], f"{label} is required but marked external"
            assert spec["surface"] is not None, f"{label} has no file surface"


class TestBuildInventory:
    def test_inventory_is_json_serializable(self, tmp_path: Path) -> None:
        inv = build_inventory(_make_repo(tmp_path))
        encoded = json.dumps(inv, indent=2, sort_keys=True)
        reparsed = json.loads(encoded)
        assert reparsed["schemaVersion"] == inv["schemaVersion"]

    def test_inventory_lists_all_catalogue_surfaces(self, tmp_path: Path) -> None:
        inv = build_inventory(_make_repo(tmp_path))
        labels = {s["label"] for s in inv["surfaces"]}
        assert labels == set(SURFACE_CATALOGUE.keys())

    def test_zero_drift_on_minimal_repo(self, tmp_path: Path) -> None:
        inv = build_inventory(_make_repo(tmp_path))
        assert inv["drift"] == [], inv["drift"]

    def test_deterministic_snapshot_hash(self, tmp_path: Path) -> None:
        a = build_inventory(_make_repo(tmp_path))
        b = build_inventory(_make_repo(tmp_path))
        assert a["snapshotSha256"] == b["snapshotSha256"]

    def test_external_surfaces_present_is_false_but_no_drift(self, tmp_path: Path) -> None:
        inv = build_inventory(_make_repo(tmp_path))
        external = [s for s in inv["surfaces"] if s["external"]]
        assert external, "no external surfaces declared"
        for s in external:
            if s["label"] == "environment-projection-buildtime":
                continue  # projection surface is "present" by env-set definition
            assert s["present"] is False
        assert not any(
            d for d in inv["drift"] if d["surface"] in {
                "image-manifest", "approved-runtime-overlay"
            }
        )

    def test_env_names_discovered(self, tmp_path: Path) -> None:
        inv = build_inventory(_make_repo(tmp_path))
        env_surface = next(
            s for s in inv["surfaces"] if s["label"] == "environment-projection-buildtime"
        )
        assert "VITE_FOO" in env_surface["envNames"]
        assert env_surface["contentHash"]


class TestDrift:
    def test_missing_required_surface_is_drift(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        (root / ".env.example").unlink()
        inv = build_inventory(root)
        drift_surfaces = {d["surface"] for d in inv["drift"]}
        assert "deployment-config-env-template" in drift_surfaces

    def test_missing_compiled_defaults_is_drift(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        (root / "backend" / "agent_runtime" / "configuration" / "resolver.py").unlink()
        inv = build_inventory(root)
        assert any(d["surface"] == "compiled-defaults" for d in inv["drift"])

    def test_compose_file_is_p1_drift(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        (root / "docker-compose.yml").write_text("services: {}\n")
        inv = build_inventory(root)
        compose_drift = [d for d in inv["drift"] if d["surface"] == "deployment-config-compose"]
        assert compose_drift, "compose file not flagged as drift"
        assert compose_drift[0]["severity"] == "P1"

    def test_compose_glob_variants_all_detected(self, tmp_path: Path) -> None:
        # at least the documented globs are real patterns
        assert "docker-compose*.yml" in COMPOSE_GLOBS
        assert "compose*.yaml" in COMPOSE_GLOBS

    def test_no_env_names_is_p3_drift(self, tmp_path: Path) -> None:
        root = _make_repo(tmp_path)
        (root / "src" / "main.ts").write_text("const a = 1;\n")
        inv = build_inventory(root)
        env_drift = [d for d in inv["drift"] if d["surface"] == "environment-projection-buildtime"]
        assert env_drift
        assert env_drift[0]["severity"] == "P3"


class TestStrictMode:
    def test_strict_returns_zero_when_no_drift(self, tmp_path: Path) -> None:
        import agent_runtime.configuration_inventory as inv_mod
        from unittest import mock
        with mock.patch.object(
            inv_mod.sys, "argv",
            ["config_inventory.py", "--repo-root", str(_make_repo(tmp_path)), "--strict"],
        ):
            assert inv_mod.main() == 0

    def test_strict_returns_one_on_drift(self, tmp_path: Path) -> None:
        import agent_runtime.configuration_inventory as inv_mod
        from unittest import mock
        with mock.patch.object(
            inv_mod.sys, "argv",
            ["config_inventory.py", "--repo-root", str(tmp_path), "--strict"],
        ):
            assert inv_mod.main() == 1  # empty tmp_path -> required surfaces missing

    def test_main_writes_artifact(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        import agent_runtime.configuration_inventory as inv_mod
        from unittest import mock
        root = _make_repo(tmp_path)
        with mock.patch.object(
            inv_mod.sys, "argv",
            ["config_inventory.py", "--repo-root", str(root), "--write"],
        ):
            assert inv_mod.main() == 0
        written = json.loads((root / "docs" / "architecture" / "CONFIGURATION_PROVENANCE_INVENTORY.json").read_text())
        assert written["schemaVersion"] == SCHEMA_EXPECTED
        # stdout should also carry the same payload
        out = json.loads(capsys.readouterr().out)
        assert out["snapshotSha256"] == written["snapshotSha256"]


class TestRealRepo:
    """Run the runner against the actual checked-out repository."""

    def test_real_repo_zero_drift(self) -> None:
        inv = build_inventory(REPO_ROOT)
        assert inv["drift"] == [], f"unxpected drift against main: {inv['drift']}"

    def test_real_repo_artifact_matches_runner(self) -> None:
        artifact_path = REPO_ROOT / "docs" / "architecture" / "CONFIGURATION_PROVENANCE_INVENTORY.json"
        assert artifact_path.exists(), "checked-in inventory artifact missing"
        artifact = json.loads(artifact_path.read_text())
        live = build_inventory(REPO_ROOT)
        assert artifact["snapshotSha256"] == live["snapshotSha256"], (
            "checked-in CONFIGURATION_PROVENANCE_INVENTORY.json is stale relative to the repo; "
            "regenerate with: python backend/agent_runtime/configuration_inventory.py --write"
        )
