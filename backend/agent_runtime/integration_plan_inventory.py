"""Command-line inventory runner for the Integration Plan Lane.

Implements Issue #1112 implementation step 1:

> 1. Bestehende Continuity-, Plan-, Goal- und Evidence-Fl\u00e4chen
>    inventarisieren.

The runner produces a snapshot (and a *truth-class annotated* drift
report) of every existing Plan-, Continuity-, Memory-, Evidence-, Goal-
and Long-Run surface in the canonical Sovereign Studio ATO repository.
The output is JSON on stdout and \u2014 when invoked with ``--write`` \u2014 also
written to ``docs/architecture/INTEGRATION_PLAN_LANE_INVENTORY.json``.

The runner is intentionally stdlib-only and never invokes the network.
It performs no mutation. It is therefore safe to run in any CI gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Mapping

# Ensure we can import the canonical lane module regardless of CWD.
HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from agent_runtime.integration_plan_helpers import (  # noqa: E402
    snapshot_plan_lane_surfaces,
)


# Canonical surface map. Mirrors the same labels used by the
# ``snapshot_plan_lane_surfaces`` function so the runtime output lines
# up byte-for-byte with the helpers test fixtures.
SURFACE_PATHS: Mapping[str, str] = {
    # Continuity
    "canonical-continuity-context": "docs/sovereign-continuity/CONTEXT.md",
    "canonical-continuity-ledger": "docs/sovereign-continuity/LEDGER.jsonl",
    "continuity-mirror": "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl",
    "continuity-policy": "tools/sovereign-chatgpt-mcp/config/sovereign-continuity-policy.json",
    "continuity-validator": "tools/sovereign-chatgpt-mcp/continuity.py",
    "continuity-tests": "tools/sovereign-chatgpt-mcp/tests/test_continuity.py",
    # Existing evidence lanes
    "bug-evidence-lane": "backend/agent_runtime/bug_evidence_lane.py",
    "bug-evidence-tests": "backend/tests/test_bug_evidence_lane.py",
    "evidence-gate": "backend/agent_runtime/evidence_gate.py",
    "mutation-evidence-layer": "backend/agent_runtime/mutation_evidence_layer.py",
    "evidence-collectors": "backend/agent_runtime/evidence_collectors.py",
    "provider-routing-evidence-gate": "backend/agent_runtime/provider_routing_evidence_gate.py",
    "rescue-evidence-gate": "backend/agent_runtime/rescue_evidence_gate.py",
    "deployment-evidence-gate": "backend/agent_runtime/mcp_fleet_deployment_evidence_gate.py",
    "pgvector-evidence-gate": "backend/agent_runtime/postgres_pgvector_evidence_gate.py",
    "github-write-evidence-gate": "backend/agent_runtime/github_write_evidence_gate.py",
    # The new plan lane
    "plan-lane-canonical": "backend/agent_runtime/integration_plan_lane.py",
    "plan-lane-store": "backend/agent_runtime/integration_plan_store.py",
    "plan-lane-helpers": "backend/agent_runtime/integration_plan_helpers.py",
    "plan-lane-tests": "backend/tests/test_integration_plan_lane.py",
    "plan-store-tests": "backend/tests/test_integration_plan_store.py",
    "plan-helpers-tests": "backend/tests/test_integration_plan_helpers.py",
    "plan-lane-inventory-runner": "backend/agent_runtime/integration_plan_inventory.py",
    # Mirror copy
    "plan-lane-canonical-mirror": "scripts/sovereign-backend/agent_runtime/integration_plan_lane.py",
    "plan-lane-store-mirror": "scripts/sovereign-backend/agent_runtime/integration_plan_store.py",
    "plan-lane-helpers-mirror": "scripts/sovereign-backend/agent_runtime/integration_plan_helpers.py",
    # Docs
    "plan-lane-architecture-doc": "docs/architecture/INTEGRATION_PLAN_LANE.v1.md",
    "current-state-doc": "docs/CURRENT_STATE_2026-08-03.md",
    "agents-md": "AGENTS.md",
    # Memory + Goal surfaces
    "agents-memory": ".agents/memory/MEMORY.md",
}


# Truth-class annotation per surface (Issue #1112 \u00a7 Abgrenzung).
# Each surface is classified as one of:
# - canonical-truth:    authoritative and the only valid source.
# - projection:         derived from canonical-truth and never overrides it.
# - documentation:      narrative only; cannot promote status to verified.
# - mirror:             byte-identical twin of canonical-truth.
TRUTH_CLASS: Mapping[str, str] = {
    "canonical-continuity-context": "canonical-truth",
    "canonical-continuity-ledger": "canonical-truth",
    "continuity-mirror": "mirror",
    "continuity-policy": "canonical-truth",
    "continuity-validator": "canonical-truth",
    "continuity-tests": "canonical-truth",
    "bug-evidence-lane": "canonical-truth",
    "bug-evidence-tests": "canonical-truth",
    "evidence-gate": "canonical-truth",
    "mutation-evidence-layer": "canonical-truth",
    "evidence-collectors": "canonical-truth",
    "provider-routing-evidence-gate": "canonical-truth",
    "rescue-evidence-gate": "canonical-truth",
    "deployment-evidence-gate": "canonical-truth",
    "pgvector-evidence-gate": "canonical-truth",
    "github-write-evidence-gate": "canonical-truth",
    "plan-lane-canonical": "projection",
    "plan-lane-store": "projection",
    "plan-lane-helpers": "projection",
    "plan-lane-tests": "projection",
    "plan-store-tests": "projection",
    "plan-helpers-tests": "projection",
    "plan-lane-inventory-runner": "projection",
    "plan-lane-canonical-mirror": "mirror",
    "plan-lane-store-mirror": "mirror",
    "plan-lane-helpers-mirror": "mirror",
    "plan-lane-architecture-doc": "documentation",
    "current-state-doc": "documentation",
    "agents-md": "documentation",
    "agents-memory": "canonical-truth",
}


def _sha256_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_inventory(
    repo_root: Path,
    *,
    required_labels: tuple[str, ...] = (
        "canonical-continuity-context",
        "canonical-continuity-ledger",
        "continuity-policy",
        "bug-evidence-lane",
        "plan-lane-canonical",
        "plan-lane-store",
        "plan-lane-helpers",
    ),
) -> dict:
    """Produce the inventory dict; mirrors ``snapshot_plan_lane_surfaces``."""
    exists_map = {}
    file_hashes = {}
    for label, relative in SURFACE_PATHS.items():
        p = repo_root / relative
        exists_map[label] = p.exists()
        if p.exists() and p.is_file():
            file_hashes[label] = _sha256_file(p)
        else:
            file_hashes[label] = ""

    snapshot = snapshot_plan_lane_surfaces(
        repo_root_label=str(repo_root.name),
        exists={label: v for label, v in exists_map.items() if label in {
            "canonical-continuity-context",
            "canonical-continuity-ledger",
            "continuity-policy",
            "bug-evidence-lane",
            "bug-evidence-tests",
            "plan-lane-canonical",
            "plan-lane-store",
            "plan-lane-tests",
            "plan-store-tests",
            "plan-lane-helpers",
        }},
        expected_surface_labels=required_labels,
    )

    # Build the wire-format output: enumerate EVERY surface in SURFACE_PATHS,
    # augmented with helper-detected drift for the small canonical set.
    surfaces = []
    for label, relative in SURFACE_PATHS.items():
        path = repo_root / relative
        present = path.exists() and path.is_file()
        surfaces.append(
            {
                "label": label,
                "relativePath": relative,
                "truthClass": TRUTH_CLASS.get(label, "unclassified"),
                "present": present,
                "sha256": file_hashes.get(label, ""),
            }
        )

    # Combined drift: any present=False surface is a drift finding; merge in
    # the helper's own findings for the canonical subset.
    drift = []
    for s in surfaces:
        if not s["present"]:
            drift.append(
                {
                    "surface": s["label"],
                    "severity": "P1",
                    "detail": f"required surface {s['relativePath']} is missing",
                }
            )
    drift.extend(f.to_dict() for f in snapshot.drift)

    output = {
        "schemaVersion": snapshot.schema_version,
        "repositoryRootLabel": snapshot.repository_root_label,
        "generatedBy": "backend/agent_runtime/integration_plan_inventory.py",
        "snapshotSha256": snapshot.snapshot_sha256,
        "surfaces": surfaces,
        "drift": drift,
        "invariantStatements": [
            "Plan status is a projection, not truth.",
            "Runtime / CI / deployment / database state remain canonical and cannot be replaced by the plan lane.",
            "Continuity ledgers remain append-only and byte-equal across canonical and mirror.",
            "No second agent runtime, queue, memory store or MCP registry may exist alongside canonical surfaces.",
            "LiteLLM is not a supported plan lane runtime or fallback path.",
        ],
        "openSourceFolders": [
            "backend/agent_runtime/",
            "backend/tests/",
            "tools/sovereign-chatgpt-mcp/",
            "scripts/sovereign-backend/",
            "docs/architecture/",
            "docs/sovereign-continuity/",
        ],
    }
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        default=str(HERE.parent.parent),
        help="Repository root (defaults to two levels above this script)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Also write the inventory to docs/architecture/INTEGRATION_PLAN_LANE_INVENTORY.json",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any drift finding is reported",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    inventory = build_inventory(repo_root)
    payload = json.dumps(inventory, indent=2, sort_keys=True)
    print(payload)
    if args.write:
        target = repo_root / "docs" / "architecture" / "INTEGRATION_PLAN_LANE_INVENTORY.json"
        target.write_text(payload + "\n", encoding="utf-8")
    if args.strict and inventory["drift"]:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())