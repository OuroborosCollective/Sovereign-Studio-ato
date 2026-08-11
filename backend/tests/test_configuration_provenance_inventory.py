"""Tests for backend/agent_runtime/configuration_provenance_inventory.py

These tests exercise the real inventory runner (stdlib-only, non-mutating) and
verify it produces a stable, schema-versioned artifact whose surfaced source
kinds match the canonical provenance source order. They never touch the
network and never reveal secret material.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.configuration_provenance_inventory import (  # noqa: E402
    CONFIG_SURFACE_PATHS,
    SCHEMA_VERSION,
    build_inventory,
    main,
)
from agent_runtime.configuration.config_sources import (  # noqa: E402
    ALLOWED_SOURCE_KINDS,
    SOURCE_ORDER,
    SOURCE_PRIORITY,
)


REPO_ROOT = Path("/workspace/project/Sovereign-Studio-ato")


class TestSurfaceCatalogue:
    def test_every_surface_has_allowed_source_kind(self) -> None:
        for entry in CONFIG_SURFACE_PATHS:
            assert entry["sourceKind"] in ALLOWED_SOURCE_KINDS, (
                f"surface {entry['label']} has disallowed sourceKind "
                f"{entry['sourceKind']!r}"
            )

    def test_every_surface_has_truth_class(self) -> None:
        valid = {"canonical-truth", "projection", "documentation", "mirror"}
        for entry in CONFIG_SURFACE_PATHS:
            assert entry["truthClass"] in valid, (
                f"surface {entry['label']} has bad truthClass {entry['truthClass']!r}"
            )

    def test_surfaces_cover_all_source_kinds(self) -> None:
        kinds = {str(e["sourceKind"]) for e in CONFIG_SURFACE_PATHS}
        assert kinds == set(ALLOWED_SOURCE_KINDS), (
            f"missing source kinds in catalogue: {set(ALLOWED_SOURCE_KINDS) - kinds}"
        )


class TestBuildInventory:
    def test_inventory_is_json(self, tmp_path: Path) -> None:
        inv = build_inventory(tmp_path)
        encoded = json.dumps(inv, indent=2, sort_keys=True)
        reparsed = json.loads(encoded)
        assert reparsed["schemaVersion"] == inv["schemaVersion"]

    def test_inventory_lists_all_surfaces(self, tmp_path: Path) -> None:
        (tmp_path / "x.py").write_text("")
        inv = build_inventory(tmp_path)
        assert len(inv["surfaces"]) == len(CONFIG_SURFACE_PATHS)

    def test_schema_version_stable(self, tmp_path: Path) -> None:
        inv = build_inventory(tmp_path)
        assert inv["schemaVersion"] == SCHEMA_VERSION

    def test_source_order_matches_canonical(self, tmp_path: Path) -> None:
        inv = build_inventory(tmp_path)
        assert inv["sourceOrder"] == list(SOURCE_ORDER)
        assert inv["sourcePriority"] == dict(SOURCE_PRIORITY)

    def test_missing_required_surface_reported_as_drift(self, tmp_path: Path) -> None:
        inv = build_inventory(tmp_path)
        assert inv["drift"], "expected drift for an empty repo root"
        details = " ".join(d["detail"] for d in inv["drift"])
        assert "required config surface" in details

    def test_disallowed_source_kind_reported_as_drift(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad = list(CONFIG_SURFACE_PATHS)
        bad.append(
            {
                "label": "bogus",
                "relativePath": "nope.py",
                "sourceKind": "not-a-kind",
                "truthClass": "projection",
                "required": False,
            }
        )
        monkeypatch.setattr(
            "agent_runtime.configuration_provenance_inventory.CONFIG_SURFACE_PATHS",
            bad,
        )
        inv = build_inventory(tmp_path)
        details = " ".join(d["detail"] for d in inv["drift"])
        assert "not an allowed ConfigSourceKind" in details

    def test_snapshot_is_deterministic(self, tmp_path: Path) -> None:
        (tmp_path / "x.py").write_text("")
        a = build_inventory(tmp_path)
        b = build_inventory(tmp_path)
        assert a["snapshotSha256"] == b["snapshotSha256"]
        assert a["snapshotSha256"] != ""

    def test_inventory_against_real_repo_has_no_drift(self) -> None:
        inv = build_inventory(REPO_ROOT)
        assert inv["drift"] == [], (
            f"unexpected drift in canonical repo: {inv['drift']}"
        )
        # Every required surface must be present.
        missing = [
            s["label"] for s in inv["surfaces"] if s["required"] and not s["present"]
        ]
        assert missing == [], f"required surfaces missing: {missing}"

    def test_real_repo_surfaces_are_ordered_by_priority(self) -> None:
        inv = build_inventory(REPO_ROOT)
        present = [s for s in inv["surfaces"] if s["present"]]
        priorities = [s["priority"] for s in present]
        assert priorities == sorted(priorities), (
            "present surfaces are not ordered by canonical priority"
        )

    def test_env_references_exclude_secret_shaped_names(self, tmp_path: Path) -> None:
        scan_dir = tmp_path / "backend" / "agent_runtime"
        scan_dir.mkdir(parents=True)
        secret_file = scan_dir / "app.py"
        secret_file.write_text(
            'os.getenv("API_KEY")\nos.getenv("DB_PASSWORD")\nos.getenv("PUBLIC_URL")\n'
        )
        inv = build_inventory(tmp_path)
        names = {ref["name"] for ref in inv["envReferences"]}
        assert "PUBLIC_URL" in names
        assert "API_KEY" not in names
        assert "DB_PASSWORD" not in names


class TestInventoryScriptCLI:
    def test_main_no_args_emits_valid_json(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import agent_runtime.configuration_provenance_inventory as inv_mod
        from unittest import mock

        with mock.patch.object(
            inv_mod.sys, "argv",
            ["inventory.py", "--repo-root", str(REPO_ROOT)],
        ):
            rc = inv_mod.main()
            captured = capsys.readouterr()
        assert rc == 0
        parsed = json.loads(captured.out)
        assert parsed["schemaVersion"] == SCHEMA_VERSION
        assert parsed["drift"] == []

    def test_strict_mode_returns_1_on_drift(self, tmp_path: Path) -> None:
        import agent_runtime.configuration_provenance_inventory as inv_mod
        from unittest import mock

        with mock.patch.object(
            inv_mod.sys, "argv",
            ["inventory.py", "--repo-root", str(tmp_path), "--strict"],
        ):
            rc = inv_mod.main()
        assert rc == 1

    def test_strict_mode_clean_on_real_repo(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import agent_runtime.configuration_provenance_inventory as inv_mod
        from unittest import mock

        with mock.patch.object(
            inv_mod.sys, "argv",
            ["inventory.py", "--repo-root", str(REPO_ROOT), "--strict"],
        ):
            rc = inv_mod.main()
        assert rc == 0

    def test_write_writes_output_file(self, tmp_path: Path) -> None:
        import agent_runtime.configuration_provenance_inventory as inv_mod
        from unittest import mock

        # Seed one required surface so write succeeds; strict off.
        for entry in CONFIG_SURFACE_PATHS:
            if not entry["required"]:
                continue
            rel = tmp_path / str(entry["relativePath"])
            rel.parent.mkdir(parents=True, exist_ok=True)
            rel.write_text("# seeded\n")

        out = tmp_path / "docs" / "architecture" / "CONFIGURATION_PROVENANCE_INVENTORY.json"
        with mock.patch.object(
            inv_mod.sys, "argv",
            ["inventory.py", "--repo-root", str(tmp_path), "--write"],
        ):
            rc = inv_mod.main()
        assert rc == 0
        assert out.exists()
        written = json.loads(out.read_text())
        assert written["schemaVersion"] == SCHEMA_VERSION
