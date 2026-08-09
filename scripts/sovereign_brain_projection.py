#!/usr/bin/env python3
"""Validate and refresh the Sovereign Git-native project-brain projection.

This module intentionally has no third-party dependencies. It treats BRAIN.md and
brain/*.md as a DERIVED_PROJECTION over canonical repository sources. It never
claims CI, deployment, database, container, MCP, or runtime truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = "sovereign.brain-projection.v1"
TRUTH_CLASS = "DERIVED_PROJECTION"

DEFAULT_SOURCE_PATHS = (
    "AGENTS.md",
    "docs/CURRENT_STATE_2026-08-03.md",
    "docs/SOVEREIGN_PRODUCT_TRUTH.md",
    "docs/sovereign-continuity/CONTEXT.md",
    ".github/workflows/sovereign-continuity-gate.yml",
)

DEFAULT_PAGE_PATHS = (
    "BRAIN.md",
    "brain/architecture.md",
    "brain/current-state.md",
    "brain/decisions.md",
    "brain/runtime-truth.md",
    "brain/workflows.md",
    "brain/roadmap.md",
    "brain/continuity.md",
)

REQUIRED_PAGE_MARKERS = (
    "truth_class: DERIVED_PROJECTION",
    "runtime_verified: false",
    "## compiled_truth",
    "## timeline",
)

FORBIDDEN_PAGE_MARKERS = (
    "truth_class: RUNTIME_VERIFIED",
    "runtime_verified: true",
    "deployment_verified: true",
    "ci_verified: true",
)


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry(root: Path, relative_path: str) -> dict[str, str]:
    data = (root / relative_path).read_bytes()
    return {
        "path": relative_path,
        "git_blob_sha1": git_blob_sha1(data),
        "sha256": sha256(data),
    }


def build_manifest(
    root: Path,
    source_paths: Iterable[str] = DEFAULT_SOURCE_PATHS,
    page_paths: Iterable[str] = DEFAULT_PAGE_PATHS,
) -> dict[str, object]:
    sources = [_entry(root, path) for path in source_paths]
    pages = [_entry(root, path) for path in page_paths]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "truthClass": TRUTH_CLASS,
        "runtimeVerified": False,
        "purpose": "Git-native derived projection for coding-agent orientation",
        "truthBoundary": {
            "canonicalTruthSourcesRemainExternal": True,
            "continuityGithubWorkflowAdvisoryOnly": True,
            "technicalCompletionRequiresIndependentReadback": True,
        },
        "sources": sources,
        "pages": pages,
    }


def write_manifest(root: Path) -> Path:
    manifest_path = root / "brain" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(root)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _validate_page(relative_path: str, text: str) -> list[str]:
    errors: list[str] = []
    for marker in REQUIRED_PAGE_MARKERS:
        if marker not in text:
            errors.append(f"PAGE_REQUIRED_MARKER_MISSING:{relative_path}:{marker}")
    for marker in FORBIDDEN_PAGE_MARKERS:
        if marker in text:
            errors.append(f"PAGE_FORBIDDEN_TRUTH_CLAIM:{relative_path}:{marker}")
    return errors


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = root / "brain" / "manifest.json"
    if not manifest_path.exists():
        return ["MANIFEST_MISSING:brain/manifest.json"]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"MANIFEST_INVALID:{exc}"]

    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("MANIFEST_SCHEMA_MISMATCH")
    if manifest.get("truthClass") != TRUTH_CLASS:
        errors.append("MANIFEST_TRUTH_CLASS_MISMATCH")
    if manifest.get("runtimeVerified") is not False:
        errors.append("MANIFEST_RUNTIME_CLAIM_FORBIDDEN")

    boundary = manifest.get("truthBoundary")
    if not isinstance(boundary, dict):
        errors.append("MANIFEST_TRUTH_BOUNDARY_MISSING")
    else:
        if boundary.get("canonicalTruthSourcesRemainExternal") is not True:
            errors.append("MANIFEST_CANONICAL_SOURCE_BOUNDARY_MISSING")
        if boundary.get("continuityGithubWorkflowAdvisoryOnly") is not True:
            errors.append("MANIFEST_CONTINUITY_ADVISORY_BOUNDARY_MISSING")
        if boundary.get("technicalCompletionRequiresIndependentReadback") is not True:
            errors.append("MANIFEST_READBACK_BOUNDARY_MISSING")

    for group_name in ("sources", "pages"):
        entries = manifest.get(group_name)
        if not isinstance(entries, list):
            errors.append(f"MANIFEST_{group_name.upper()}_INVALID")
            continue
        for item in entries:
            if not isinstance(item, dict):
                errors.append(f"MANIFEST_{group_name.upper()}_ENTRY_INVALID")
                continue
            relative_path = item.get("path")
            if not isinstance(relative_path, str) or not relative_path:
                errors.append(f"MANIFEST_{group_name.upper()}_PATH_INVALID")
                continue
            path = root / relative_path
            if not path.is_file():
                errors.append(f"FILE_MISSING:{relative_path}")
                continue
            data = path.read_bytes()
            if git_blob_sha1(data) != item.get("git_blob_sha1"):
                errors.append(f"GIT_BLOB_HASH_MISMATCH:{relative_path}")
            expected_sha256 = item.get("sha256")
            if expected_sha256 is not None:
                if not isinstance(expected_sha256, str) or sha256(data) != expected_sha256:
                    errors.append(f"SHA256_MISMATCH:{relative_path}")
            if group_name == "pages":
                errors.extend(_validate_page(relative_path, data.decode("utf-8")))

    root_brain = root / "BRAIN.md"
    if root_brain.is_file():
        root_text = root_brain.read_text(encoding="utf-8")
        for page in DEFAULT_PAGE_PATHS[1:]:
            if page not in root_text:
                errors.append(f"BRAIN_INDEX_LINK_MISSING:{page}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("check", "refresh"),
        nargs="?",
        default="check",
        help="check the committed projection or refresh only its hash manifest",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the parent of scripts/)",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    if args.command == "refresh":
        path = write_manifest(root)
        print(f"refreshed {path.relative_to(root)}")

    errors = validate(root)
    if errors:
        for error in errors:
            print(error)
        return 1

    print("SOVEREIGN_BRAIN_PROJECTION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
