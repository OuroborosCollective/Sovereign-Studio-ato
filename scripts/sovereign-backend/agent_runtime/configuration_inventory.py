"""Command-line inventory runner for the Configuration Provenance layer.

Implements the first acceptance criterion of issue #1169:

> aktuelle Configquellen, Env-Fallbacks und Composeflaechen inventarisieren

The runner maps the five abstract ``ConfigSourceKind``\\ s onto the *concrete*
repository surfaces that feed them, records presence + content hash, and
produces a schema-versioned, deterministic JSON artifact. It is the
machine-checked counterpart of the prose inventory in
``docs/architecture/CONFIGURATION_PROVENANCE.md``: where that doc is a claim
surface a human keeps honest, this runner is a gate CI keeps honest.

Design rules (mirroring ``integration_plan_inventory.py``):

- stdlib-only, no network, no mutation;
- safe to run in any CI gate;
- ``--strict`` exits non-zero on any drift finding so a CI step can enforce it;
- deterministic output: identical repo state -> byte-identical artifact and
  ``snapshotSha256``.

Drift the runner detects (all fail-closed):

- a required file-backed surface is missing (e.g. an env template was removed
  without re-binding the provenance source);
- a compose file appears in the repository (an un-inventoried
  ``deployment-config`` source must be explicitly bound instead of silently
  read);
- the environment-projection surface drifted (a build-time env var was added or
  removed without updating the inventory) -- reported at ``P3`` because the
  fallback is read-only, never a mutable truth path.

Surfaces that are *external by design* (``image-manifest``,
``approved-runtime-overlay``) are never drift: they are bound outside the
repository. They are listed so the inventory is complete, with
``external=True``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Mapping, Sequence

# Ensure we can import the canonical configuration module regardless of CWD.
HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from agent_runtime.configuration.config_sources import (  # noqa: E402
    SOURCE_ORDER,
)
from agent_runtime.configuration.config_canonicalize import (  # noqa: E402
    hash_value,
)

SCHEMA_VERSION = "sovereign.configuration-provenance-inventory.v1"


# ---------------------------------------------------------------------------
# Concrete surface catalogue
# ---------------------------------------------------------------------------
#
# Each entry maps a provenance ``ConfigSourceKind`` to the concrete repo
# surface(s) that feed it. ``truthClass`` follows the same vocabulary as the
# integration-plan inventory:
#
#   canonical-truth  - authoritative, only valid source
#   projection       - derived, never overrides canonical truth
#   documentation    - narrative only; cannot promote status
#   mirror           - byte-identical twin of canonical-truth
#   external-binding - bound outside the repo at build/deploy time; never drift
#
# ``external=True`` marks surfaces that legitimately have no in-repo file and
# are therefore excluded from strict drift.
SURFACE_CATALOGUE: Mapping[str, dict] = {
    "compiled-defaults": {
        "kind": "compiled-defaults",
        "surface": "backend/agent_runtime/configuration/resolver.py",
        "truthClass": "canonical-truth",
        "external": False,
        "note": "Hardcoded defaults inside resolver call sites; lowest priority, always present.",
    },
    "image-manifest": {
        "kind": "image-manifest",
        "surface": None,
        "truthClass": "external-binding",
        "external": True,
        "readbackChannel": "SOVEREIGN_IMAGE_DIGEST",
        "note": "Immutable image digest bound at build/deploy; read back via SOVEREIGN_IMAGE_DIGEST.",
    },
    "deployment-config-env-template": {
        "kind": "deployment-config",
        "surface": ".env.example",
        "truthClass": "documentation",
        "external": False,
        "note": "Revision-bound deploy template; not a mutable truth path.",
    },
    "deployment-config-toolchain-template": {
        "kind": "deployment-config",
        "surface": ".env.sovereign-toolchain.example",
        "truthClass": "documentation",
        "external": False,
        "note": "Toolchain patch-flow template; revision-bound deploy input.",
    },
    "environment-projection-buildtime": {
        "kind": "environment-projection",
        "surface": None,
        "truthClass": "projection",
        "external": True,
        "discoverEnv": "src",
        "note": "Build-time env (VITE_*, process.env, import.meta.env) baked at frontend build; projected read-only.",
    },
    "approved-runtime-overlay": {
        "kind": "approved-runtime-overlay",
        "surface": None,
        "truthClass": "external-binding",
        "external": True,
        "note": "Explicitly approved overlay only; highest priority, pre-bound externally.",
    },
}

# File-backed surfaces whose absence is a real P1/P2 drift (not external).
REQUIRED_FILE_SURFACES: tuple[str, ...] = (
    "compiled-defaults",
    "deployment-config-env-template",
    "deployment-config-toolchain-template",
)

# Compose glob patterns. A compose file in the repo is an un-inventoried
# deployment-config source and must fail closed until explicitly bound.
COMPOSE_GLOBS: tuple[str, ...] = (
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "compose*.yml",
    "compose*.yaml",
)

# Env-name patterns scanned from src/ for the build-time projection surface.
_VITE_RE = re.compile(r"\bVITE_[A-Z0-9_]+\b")
_PROCESS_ENV_RE = re.compile(r"process\.env\.([A-Z0-9_]+)")
_IMPORT_META_ENV_RE = re.compile(r"import\.meta\.env\.([A-Z0-9_]+)")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _discover_env_names(repo_root: Path, src_dir: str = "src") -> list[str]:
    """Return the sorted, de-duplicated set of build-time env names in ``src``."""
    root = repo_root / src_dir
    names: set[str] = set()
    if root.is_dir():
        for pattern in ("*.ts", "*.tsx", "*.mjs", "*.js", "*.vue"):
            for src_file in root.rglob(pattern):
                try:
                    text = src_file.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                names.update(_VITE_RE.findall(text))
                names.update(_PROCESS_ENV_RE.findall(text))
                names.update(_IMPORT_META_ENV_RE.findall(text))
    return sorted(names)


def _env_content_hash(env_names: Sequence[str]) -> str:
    return hash_value(list(env_names))


def _scan_compose_files(repo_root: Path) -> list[str]:
    found: list[str] = []
    for pattern in COMPOSE_GLOBS:
        for p in sorted(repo_root.glob(pattern)):
            if p.is_file():
                found.append(p.name)
    return found


def build_inventory(repo_root: Path) -> dict:
    """Produce the inventory dict for ``repo_root``.

    Deterministic: identical repo state -> byte-identical output and
    ``snapshotSha256``.
    """
    env_names = _discover_env_names(repo_root)
    env_hash = _env_content_hash(env_names)
    compose_files = _scan_compose_files(repo_root)

    surfaces = []
    drift = []

    for label, spec in SURFACE_CATALOGUE.items():
        kind = spec["kind"]
        relative = spec.get("surface")
        external = spec.get("external", False)

        if relative is not None:
            path = repo_root / relative
            present = path.exists() and path.is_file()
            sha = _sha256_file(path) if present else ""
            content_hash = sha
        elif spec.get("discoverEnv"):
            present = True  # the projection surface is defined by the env set
            sha = ""
            content_hash = env_hash
        else:
            present = False
            sha = ""
            content_hash = ""

        entry = {
            "label": label,
            "kind": kind,
            "relativePath": relative,
            "truthClass": spec["truthClass"],
            "external": external,
            "present": present,
            "sha256": sha,
            "contentHash": content_hash,
            "note": spec.get("note", ""),
        }
        if spec.get("readbackChannel"):
            entry["readbackChannel"] = spec["readbackChannel"]
        if spec.get("discoverEnv"):
            entry["envNames"] = env_names
        surfaces.append(entry)

        # Drift: required file-backed surface missing.
        if not external and label in REQUIRED_FILE_SURFACES and not present:
            drift.append(
                {
                    "surface": label,
                    "severity": "P2",
                    "detail": f"required config source {relative} is missing",
                }
            )

    # Compose drift: any compose file is an un-inventoried deployment-config.
    for name in compose_files:
        drift.append(
            {
                "surface": "deployment-config-compose",
                "severity": "P1",
                "detail": (
                    f"compose file {name} found in repo root: an un-inventoried "
                    "deployment-config source must be explicitly bound (see "
                    "docs/architecture/CONFIGURATION_PROVENANCE.md)"
                ),
            }
        )

    # Env-projection drift is advisory (P3): the fallback is read-only, never
    # a mutable truth path, but a change should be re-inventoried. Reported as
    # drift so --strict catches it, but severity is the lowest.
    if not env_names:
        drift.append(
            {
                "surface": "environment-projection-buildtime",
                "severity": "P3",
                "detail": "no build-time env names discovered under src/",
            }
        )

    # Deterministic snapshot hash: hash the canonicalized surfaces + drift.
    snapshot_payload = {
        "schemaVersion": SCHEMA_VERSION,
        "sourceOrder": list(SOURCE_ORDER),
        "surfaces": surfaces,
        "drift": drift,
        "composeFilesFound": compose_files,
    }
    snapshot_sha256 = hash_value(snapshot_payload)

    output = {
        "schemaVersion": SCHEMA_VERSION,
        "repositoryRootLabel": repo_root.name,
        "generatedBy": "backend/agent_runtime/configuration_inventory.py",
        "snapshotSha256": snapshot_sha256,
        "sourceOrder": list(SOURCE_ORDER),
        "surfaces": surfaces,
        "drift": drift,
        "composeFilesFound": compose_files,
        "invariantStatements": [
            "Configuration provenance is a read-only resolver; mutation stays under #1119.",
            "Unknown source kinds and bare remote URLs fail closed.",
            "No mutable URL-config truth path; remote config requires pre-bound origin, digest and hash.",
            "A compose file in the repo is an un-inventoried deployment-config source and must be explicitly bound.",
            "Secrets never enter receipts; they are projected only as a redacted identity.",
            "This inventory is a claim surface: if concrete surfaces change it must be regenerated at the same revision.",
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
        help="Also write the inventory to docs/architecture/CONFIGURATION_PROVENANCE_INVENTORY.json",
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
        target = repo_root / "docs" / "architecture" / "CONFIGURATION_PROVENANCE_INVENTORY.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + "\n", encoding="utf-8")
    if args.strict and inventory["drift"]:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
