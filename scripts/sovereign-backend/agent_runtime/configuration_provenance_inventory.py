"""Command-line inventory runner for Configuration Provenance.

Implements Issue #1169 acceptance criterion 1:

> Aktuelle Configquellen, Env-Fallbacks und Compose-Flaechen inventarisieren.

The runner inventories every real configuration surface in the canonical
Sovereign Studio ATO repository and maps each surface to a provenance
``ConfigSourceKind`` (compiled-defaults, image-manifest, deployment-config,
environment-projection, approved-runtime-overlay). It records, per surface,
whether the surface exists, its sha256, and the truth class it carries.

The output is JSON on stdout and - when invoked with ``--write`` - also written
to ``docs/architecture/CONFIGURATION_PROVENANCE_INVENTORY.json``.

The runner is intentionally stdlib-only and never invokes the network. It
performs no mutation. It is therefore safe to run in any CI gate. It mirrors
the established ``integration_plan_inventory.py`` contract: a non-mutating,
deterministic, stdlib-only snapshot plus a truth-class annotated drift report.

This inventory is a *projection*. It does not prove deployed registry parity
or runtime state. It only records which configuration surfaces exist in the
repository and which provenance source kind each surface corresponds to, so
the Configuration Provenance resolver has a complete, reviewable map of the
sources it must bind.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

# Ensure we can import the canonical configuration module regardless of CWD.
# This script lives at backend/agent_runtime/, so backend/ must be importable
# for the ``agent_runtime.configuration`` package to resolve.
HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent_runtime.configuration.config_sources import (  # noqa: E402
    ALLOWED_SOURCE_KINDS,
    SOURCE_ORDER,
    SOURCE_PRIORITY,
    default_priority_for,
    is_allowed_source_kind,
)


# Each known config surface is mapped to:
#  - relativePath: the path inside the repository
#  - sourceKind:   the provenance ConfigSourceKind it contributes to
#  - truthClass:   canonical-truth | projection | documentation | mirror
#  - required:     whether the provenance contract requires it to exist
#
# The sourceKind assignment follows the resolution order in config_sources.py.
CONFIG_SURFACE_PATHS: list[dict[str, object]] = [
    # compiled-defaults: shipped, immutable defaults baked into the image.
    {
        "label": "env-example",
        "relativePath": ".env.example",
        "sourceKind": "compiled-defaults",
        "truthClass": "documentation",
        "required": True,
    },
    {
        "label": "env-sovereign-toolchain-example",
        "relativePath": ".env.sovereign-toolchain.example",
        "sourceKind": "compiled-defaults",
        "truthClass": "documentation",
        "required": True,
    },
    # image-manifest: the deployed, digest-bound image surface.
    {
        "label": "backend-compose",
        "relativePath": "scripts/sovereign-backend/docker-compose.yml",
        "sourceKind": "image-manifest",
        "truthClass": "projection",
        "required": True,
    },
    {
        "label": "litellm-compose",
        "relativePath": "deploy/sovereign-litellm/docker-compose.yml",
        "sourceKind": "image-manifest",
        "truthClass": "projection",
        "required": False,
    },
    # deployment-config: revision-bound deployment configuration.
    {
        "label": "mcp-compose",
        "relativePath": "tools/sovereign-chatgpt-mcp/docker-compose.yml",
        "sourceKind": "deployment-config",
        "truthClass": "projection",
        "required": False,
    },
    # environment-projection: the projected environment surface (Vite).
    {
        "label": "vite-env-projection-src",
        "relativePath": "src/runtime/config/configSources.ts",
        "sourceKind": "environment-projection",
        "truthClass": "canonical-truth",
        "required": True,
    },
    {
        "label": "vite-env-projection-resolver",
        "relativePath": "src/runtime/config/sovereignConfigResolver.ts",
        "sourceKind": "environment-projection",
        "truthClass": "canonical-truth",
        "required": True,
    },
    {
        "label": "vite-env-projection-receipt",
        "relativePath": "src/runtime/config/configReceipt.ts",
        "sourceKind": "environment-projection",
        "truthClass": "canonical-truth",
        "required": True,
    },
    {
        "label": "vite-env-projection-index",
        "relativePath": "src/runtime/config/index.ts",
        "sourceKind": "environment-projection",
        "truthClass": "canonical-truth",
        "required": True,
    },
    # approved-runtime-overlay: the canonical backend overlay + provenance core.
    {
        "label": "provenance-config-sources",
        "relativePath": "backend/agent_runtime/configuration/config_sources.py",
        "sourceKind": "approved-runtime-overlay",
        "truthClass": "canonical-truth",
        "required": True,
    },
    {
        "label": "provenance-canonicalize",
        "relativePath": "backend/agent_runtime/configuration/config_canonicalize.py",
        "sourceKind": "approved-runtime-overlay",
        "truthClass": "canonical-truth",
        "required": True,
    },
    {
        "label": "provenance-resolver",
        "relativePath": "backend/agent_runtime/configuration/resolver.py",
        "sourceKind": "approved-runtime-overlay",
        "truthClass": "canonical-truth",
        "required": True,
    },
    {
        "label": "provenance-receipt",
        "relativePath": "backend/agent_runtime/configuration/receipt.py",
        "sourceKind": "approved-runtime-overlay",
        "truthClass": "canonical-truth",
        "required": True,
    },
    {
        "label": "provenance-tests",
        "relativePath": "backend/tests/test_configuration_provenance.py",
        "sourceKind": "approved-runtime-overlay",
        "truthClass": "canonical-truth",
        "required": True,
    },
    {
        "label": "provenance-mirror-tests",
        "relativePath": "backend/tests/test_configuration_provenance_mirror.py",
        "sourceKind": "approved-runtime-overlay",
        "truthClass": "mirror",
        "required": True,
    },
    {
        "label": "provenance-architecture-doc",
        "relativePath": "docs/architecture/CONFIGURATION_PROVENANCE.md",
        "sourceKind": "approved-runtime-overlay",
        "truthClass": "documentation",
        "required": True,
    },
    {
        "label": "provenance-inventory-runner",
        "relativePath": "backend/agent_runtime/configuration_provenance_inventory.py",
        "sourceKind": "approved-runtime-overlay",
        "truthClass": "projection",
        "required": True,
    },
]


SCHEMA_VERSION = "configuration-provenance-inventory/v1"
INVENTORY_OUTPUT_REL = "docs/architecture/CONFIGURATION_PROVENANCE_INVENTORY.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class EnvReference:
    """A single environment-variable reference discovered in the repository."""

    name: str
    files: tuple[str, ...]


_ENV_RE = re.compile(r"\bos\.(?:getenv|environ(?:\.get)?)\(?[\"']([A-Z][A-Z0-9_]+)[\"']")
_VITE_ENV_RE = re.compile(r"\bVITE_[A-Z][A-Z0-9_]+")


def _scan_env_references(
    repo_root: Path,
) -> tuple[EnvReference, ...]:
    """Discover backend env-var reads and Vite env projections.

    Only non-secret names are recorded. Secret-shaped names (keys, tokens,
    secrets, passwords, peppers) are filtered out of the inventory so the
    provenance map never carries secret material.
    """
    secret_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PEPPER")
    refs: dict[str, set[str]] = {}

    scan_dirs = [
        repo_root / "backend" / "agent_runtime",
        repo_root / "scripts" / "sovereign-backend",
        repo_root / "src",
    ]

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in _ENV_RE.finditer(text):
                name = match.group(1)
                if any(m in name for m in secret_markers):
                    continue
                rel = str(path.relative_to(repo_root))
                refs.setdefault(name, set()).add(rel)
        for path in scan_dir.rglob("*.ts"):
            if "node_modules" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in _VITE_ENV_RE.finditer(text):
                name = match.group(0)
                if any(m in name for m in secret_markers):
                    continue
                rel = str(path.relative_to(repo_root))
                refs.setdefault(name, set()).add(rel)

    return tuple(
        EnvReference(name=name, files=tuple(sorted(files)))
        for name, files in sorted(refs.items())
    )


def build_inventory(repo_root: Path) -> dict:
    """Produce the configuration provenance inventory dict.

    The inventory is deterministic for a given repository tree: the same set of
    files and bytes always produces the same ``snapshotSha256``.
    """
    surfaces = []
    drift = []
    for entry in CONFIG_SURFACE_PATHS:
        label = str(entry["label"])
        relative = str(entry["relativePath"])
        source_kind = str(entry["sourceKind"])
        truth_class = str(entry["truthClass"])
        required = bool(entry["required"])

        path = repo_root / relative
        present = path.exists() and path.is_file()
        sha = _sha256_file(path) if present else ""

        if not is_allowed_source_kind(source_kind):
            drift.append(
                {
                    "surface": label,
                    "severity": "P0",
                    "detail": (
                        f"sourceKind {source_kind!r} is not an allowed "
                        f"ConfigSourceKind"
                    ),
                }
            )

        if required and not present:
            drift.append(
                {
                    "surface": label,
                    "severity": "P0",
                    "detail": f"required config surface {relative} is missing",
                }
            )

        surfaces.append(
            {
                "label": label,
                "relativePath": relative,
                "sourceKind": source_kind,
                "priority": default_priority_for(source_kind)
                if is_allowed_source_kind(source_kind)
                else -1,
                "truthClass": truth_class,
                "required": required,
                "present": present,
                "sha256": sha,
            }
        )

    env_references = _scan_env_references(repo_root)

    # Validate that every surfaced sourceKind appears in the canonical order.
    surfaced_kinds = sorted(
        {str(s["sourceKind"]) for s in surfaces if s["present"]},
        key=lambda k: SOURCE_PRIORITY.get(k, 999),
    )
    order_findings: list[dict[str, object]] = []
    expected_order = list(SOURCE_ORDER)
    if surfaced_kinds != [k for k in expected_order if k in set(surfaced_kinds)]:
        order_findings.append(
            {
                "surface": "source-order",
                "severity": "P1",
                "detail": (
                    "surfaced source kinds are not ordered by canonical priority"
                ),
            }
        )

    output = {
        "schemaVersion": SCHEMA_VERSION,
        "repositoryRootLabel": repo_root.name,
        "generatedBy": "backend/agent_runtime/configuration_provenance_inventory.py",
        "sourceOrder": list(SOURCE_ORDER),
        "sourcePriority": dict(SOURCE_PRIORITY),
        "allowedSourceKinds": sorted(ALLOWED_SOURCE_KINDS),
        "surfaces": surfaces,
        "envReferences": [
            {"name": ref.name, "files": list(ref.files)} for ref in env_references
        ],
        "drift": drift + order_findings,
        "invariantStatements": [
            "Configuration provenance is read-only resolution + provenance; mutation runs through #1119.",
            "Secrets are projected only as redacted identities and never appear in this inventory.",
            "The inventory is a projection of repository surfaces, not proof of deployed registry parity or runtime state.",
            "A container may start only with a fully validated, reproducible configuration; RunEnvelope and PatchMon read back the same redacted config-fingerprint.",
            "Drift against an expected binding invalidates the resolution (CONTRADICTED), blocking prior run/permission bindings and active action plans.",
        ],
    }

    canonical = json.dumps(output, sort_keys=True, separators=(",", ":"))
    output["snapshotSha256"] = _sha256_bytes(canonical.encode("utf-8"))
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
        help=(
            "Also write the inventory to "
            "docs/architecture/CONFIGURATION_PROVENANCE_INVENTORY.json"
        ),
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
        target = repo_root / INVENTORY_OUTPUT_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + "\n", encoding="utf-8")
    if args.strict and inventory["drift"]:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
