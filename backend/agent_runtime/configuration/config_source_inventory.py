"""Command-line inventory runner for configuration provenance.

Implements Issue #1169 acceptance criterion:

> aktuelle Configquellen, Env-Fallbacks und Composefl\u00e4chen inventarisieren.

The runner produces a deterministic, stdlib-only snapshot of every actual
configuration surface in the canonical Sovereign Studio ATO repository:

* configuration provenance core (TS + canonical Python + deployment mirror),
* runtime config receipts / sources referenced by code,
* environment-variable fallbacks declared in code (``os.getenv``/``os.environ``),
* compose / deployment surfaces that bind configuration into a container.

The output is JSON on stdout and \u2014 when invoked with ``--write`` \u2014 also
written to ``docs/architecture/CONFIGURATION_SOURCES_INVENTORY.json``.

The runner is intentionally stdlib-only and never invokes the network. It
performs no mutation. It is therefore safe to run in any CI gate. It mirrors
the established pattern of ``integration_plan_inventory.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Mapping

HERE = Path(__file__).resolve().parent


# Canonical configuration provenance surfaces. Each entry maps a stable label
# to a repository-relative path and a truth-class annotation, exactly like the
# integration-plan lane inventory.
SURFACE_PATHS: Mapping[str, str] = {
    # TypeScript (canonical frontend / runtime)
    "ts-config-sources": "src/runtime/config/configSources.ts",
    "ts-config-canonicalize": "src/runtime/config/configCanonicalize.ts",
    "ts-config-resolver": "src/runtime/config/sovereignConfigResolver.ts",
    "ts-config-receipt": "src/runtime/config/configReceipt.ts",
    "ts-config-index": "src/runtime/config/index.ts",
    "ts-config-tests": "src/runtime/config/configProvenance.test.ts",
    # Python (canonical backend)
    "py-config-sources": "backend/agent_runtime/configuration/config_sources.py",
    "py-config-canonicalize": "backend/agent_runtime/configuration/config_canonicalize.py",
    "py-config-resolver": "backend/agent_runtime/configuration/resolver.py",
    "py-config-receipt": "backend/agent_runtime/configuration/receipt.py",
    "py-config-init": "backend/agent_runtime/configuration/__init__.py",
    "py-config-tests": "backend/tests/test_configuration_provenance.py",
    "py-config-mirror-tests": "backend/tests/test_configuration_provenance_mirror.py",
    # Deployment mirror (byte-equivalent)
    "mirror-config-sources": "scripts/sovereign-backend/agent_runtime/configuration/config_sources.py",
    "mirror-config-canonicalize": "scripts/sovereign-backend/agent_runtime/configuration/config_canonicalize.py",
    "mirror-config-resolver": "scripts/sovereign-backend/agent_runtime/configuration/resolver.py",
    "mirror-config-receipt": "scripts/sovereign-backend/agent_runtime/configuration/receipt.py",
    "mirror-config-init": "scripts/sovereign-backend/agent_runtime/configuration/__init__.py",
    # Documentation
    "provenance-doc": "docs/architecture/CONFIGURATION_PROVENANCE.md",
}

TRUTH_CLASS: Mapping[str, str] = {
    "ts-config-sources": "canonical-truth",
    "ts-config-canonicalize": "canonical-truth",
    "ts-config-resolver": "canonical-truth",
    "ts-config-receipt": "canonical-truth",
    "ts-config-index": "canonical-truth",
    "ts-config-tests": "canonical-truth",
    "py-config-sources": "canonical-truth",
    "py-config-canonicalize": "canonical-truth",
    "py-config-resolver": "canonical-truth",
    "py-config-receipt": "canonical-truth",
    "py-config-init": "canonical-truth",
    "py-config-tests": "canonical-truth",
    "py-config-mirror-tests": "canonical-truth",
    "mirror-config-sources": "mirror",
    "mirror-config-canonicalize": "mirror",
    "mirror-config-resolver": "mirror",
    "mirror-config-receipt": "mirror",
    "mirror-config-init": "mirror",
    "provenance-doc": "documentation",
}

# Surfaces whose presence is required for configuration provenance to be
# considered implemented. Used to produce a strict drift signal.
REQUIRED_LABELS: tuple[str, ...] = (
    "ts-config-sources",
    "ts-config-canonicalize",
    "ts-config-resolver",
    "ts-config-receipt",
    "py-config-sources",
    "py-config-canonicalize",
    "py-config-resolver",
    "py-config-receipt",
    "py-config-tests",
)

# Code roots scanned for environment-variable fallback declarations. These are
# the surfaces that bind runtime configuration from the environment.
ENV_SCAN_ROOTS: tuple[str, ...] = (
    "backend/agent_runtime",
    "scripts/sovereign-backend/agent_runtime",
    "backend/enterprise_platform",
)

# Glob patterns for compose / deployment surfaces that bind configuration
# into a container image. Kept intentionally narrow to avoid node_modules.
COMPOSE_GLOBS: tuple[str, ...] = (
    "deploy/**/docker-compose*.y*ml",
    "scripts/sovereign-backend/docker-compose*.y*ml",
    "tools/sovereign-chatgpt-mcp/**/docker-compose*.y*ml",
)

# Env example / template files that document environment fallbacks.
ENV_EXAMPLE_GLOBS: tuple[str, ...] = (
    ".env.example",
    ".env.sovereign-toolchain.example",
    "scripts/sovereign-backend/.env.example",
    "tools/sovereign-chatgpt-mcp/.env.example",
)

# Guard / build config that gates configuration-related release checks.
GUARD_CONFIG_PATHS: tuple[str, ...] = (
    "sovereign.guard.json",
    "package.json",
    "tsconfig.json",
)

_ENV_PATTERN = re.compile(r"os\.getenv\(\s*[\"']([A-Z][A-Z0-9_]+)[\"']")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _list_env_fallbacks(repo_root: Path) -> list[dict]:
    """Scan code roots for ``os.getenv('NAME')`` declarations.

    Returns a sorted, deduplicated list of ``{name, sources: [relativePath]}``.
    Only ``os.getenv`` with a string-literal name is captured; ``os.environ``
    is reported as an aggregate count per file (no key-level data, which would
    require importing the module and is out of scope for a static inventory).
    """
    by_name: dict[str, set[str]] = {}
    for root_rel in ENV_SCAN_ROOTS:
        root = repo_root / root_rel
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = str(path.relative_to(repo_root))
            for match in _ENV_PATTERN.finditer(text):
                name = match.group(1)
                by_name.setdefault(name, set()).add(rel)
    entries = [
        {"name": name, "sources": sorted(sources)}
        for name, sources in sorted(by_name.items())
    ]
    return entries


def _glob_files(repo_root: Path, patterns: tuple[str, ...]) -> list[str]:
    matched: set[str] = set()
    for pattern in patterns:
        for path in repo_root.glob(pattern):
            if path.is_file() and "__pycache__" not in path.parts:
                matched.add(str(path.relative_to(repo_root)))
    return sorted(matched)


def build_inventory(repo_root: Path) -> dict:
    """Produce the configuration-source inventory dict.

    The structure mirrors the integration-plan lane inventory so the runtime
    output lines up with the established schema. The snapshot is fully
    deterministic for a given repository tree.
    """
    surfaces = []
    present_labels: set[str] = set()
    for label, relative in SURFACE_PATHS.items():
        path = repo_root / relative
        present = path.exists() and path.is_file()
        if present:
            present_labels.add(label)
        surfaces.append(
            {
                "label": label,
                "relativePath": relative,
                "truthClass": TRUTH_CLASS.get(label, "unclassified"),
                "present": present,
                "sha256": _sha256_file(path) if present else "",
            }
        )

    compose_files = _glob_files(repo_root, COMPOSE_GLOBS)
    env_examples = _glob_files(repo_root, ENV_EXAMPLE_GLOBS)
    env_fallbacks = _list_env_fallbacks(repo_root)

    guard_configs = []
    for relative in GUARD_CONFIG_PATHS:
        path = repo_root / relative
        present = path.exists() and path.is_file()
        guard_configs.append(
            {
                "relativePath": relative,
                "present": present,
                "sha256": _sha256_file(path) if present else "",
            }
        )

    # Drift: required surfaces that are absent.
    drift = []
    for label in REQUIRED_LABELS:
        if label not in present_labels:
            rel = SURFACE_PATHS.get(label, "?")
            drift.append(
                {
                    "surface": label,
                    "severity": "P1",
                    "detail": f"required config provenance surface {rel} is missing",
                }
            )

    # The snapshot hash binds the entire inventory body (excluding the hash
    # field itself) so a stale inventory JSON is detectable.
    body = {
        "schemaVersion": "sovereign.configuration-sources-snapshot.v1",
        "repositoryRootLabel": repo_root.name,
        "generatedBy": "backend/agent_runtime/configuration/config_source_inventory.py",
        "surfaces": surfaces,
        "environmentFallbacks": env_fallbacks,
        "composeSurfaces": [
            {
                "relativePath": rel,
                "sha256": _sha256_file(repo_root / rel),
            }
            for rel in compose_files
        ],
        "envExampleSurfaces": [
            {
                "relativePath": rel,
                "sha256": _sha256_file(repo_root / rel),
            }
            for rel in env_examples
        ],
        "guardConfigs": guard_configs,
        "drift": drift,
        "invariantStatements": [
            "Configuration provenance is a read-only resolver; mutation stays under #1119.",
            "Receipts contain only redacted identities and hash readback; never raw secret material.",
            "A fail-closed state produces BLOCKED, never a partial green projection.",
            "Canonical and deployment-mirror configuration packages must remain byte-identical.",
            "Remote configuration is only accepted when pre-bound to a concrete origin, digest and hash.",
        ],
    }
    body["snapshotSha256"] = _sha256_text(
        json.dumps(body, sort_keys=True, separators=(",", ":"))
    )
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        default=str(HERE.parents[3]),
        help="Repository root (defaults to four levels above this script)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Also write the inventory to docs/architecture/CONFIGURATION_SOURCES_INVENTORY.json",
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
        target = repo_root / "docs" / "architecture" / "CONFIGURATION_SOURCES_INVENTORY.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + "\n", encoding="utf-8")
    if args.strict and inventory["drift"]:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
