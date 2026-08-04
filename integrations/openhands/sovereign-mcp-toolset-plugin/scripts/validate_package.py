#!/usr/bin/env python3
"""Validate the repository-only OpenHands plugin package without network access."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SOURCE_REVISION = "6bd7a99c04642e095919593365325681a9b0a636"
EXPECTED_REGISTRY_SNAPSHOT = "936c05f72a2e4843aa84581524fb4ce24381ddf896bceebaaf8d348458c1d1e4"
EXPECTED_TOOL_FILE_SHA256 = "19cad8b110fe93a85c60d3b541a2c902f264f113898a5974355963514eda3d97"
EXPECTED_SKILL_FILE_SHA256 = "73f0744d7053401a451a4ea0bf8faff46b0cd29bc52bc2cee83adca2248f5b18"
EXPECTED_TOOL_COUNT = 231
EXPECTED_OPERATIONAL_SKILL_COUNT = 44
EXPECTED_OPERATIONAL_UNIQUE_TOOL_COUNT = 50
EXPECTED_GUIDANCE_SKILLS = {
    "data-integrity",
    "deterministic-assurance",
    "mcp-governance",
    "repository-evidence",
    "runtime-operations",
    "security-supply-chain",
    "skill-lifecycle",
    "sovereign-preflight",
}


class ValidationError(RuntimeError):
    """Raised when the package violates its committed isolation contract."""


def load_json(relative_path: str) -> Any:
    path = ROOT / relative_path
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"missing JSON file: {relative_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON in {relative_path}: {exc}") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValidationError(f"missing YAML frontmatter: {path.relative_to(ROOT)}")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValidationError(f"unterminated YAML frontmatter: {path.relative_to(ROOT)}")
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        match = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*):\s*(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip()
    return values


def validate_manifest() -> None:
    manifest = load_json(".plugin/plugin.json")
    required = {"name", "version", "description", "author"}
    missing = sorted(required - set(manifest))
    if missing:
        raise ValidationError(f"plugin manifest missing fields: {missing}")
    if manifest["name"] != "sovereign-mcp-toolset-preview":
        raise ValidationError("unexpected plugin name")
    if manifest["version"] != "0.1.0":
        raise ValidationError("unexpected plugin version")


def validate_boundary() -> None:
    boundary = load_json("package-boundary.json")
    if boundary.get("state") != "repository-only-inactive-preview":
        raise ValidationError("package state is not repository-only inactive preview")
    if boundary.get("sourceRevision") != EXPECTED_SOURCE_REVISION:
        raise ValidationError("source revision drift")
    registry = boundary.get("sourceToolRegistry", {})
    if registry.get("toolCount") != EXPECTED_TOOL_COUNT:
        raise ValidationError("boundary tool count drift")
    if registry.get("snapshotSha256") != EXPECTED_REGISTRY_SNAPSHOT:
        raise ValidationError("boundary registry snapshot drift")
    activation = boundary.get("activation", {})
    if not activation or any(value is not False for value in activation.values()):
        raise ValidationError("one or more activation flags are enabled")
    if boundary.get("allowedRoot") != "integrations/openhands/sovereign-mcp-toolset-plugin":
        raise ValidationError("allowed root drift")


def validate_inactive_mcp_and_hooks() -> None:
    if (ROOT / ".mcp.json").exists():
        raise ValidationError("active .mcp.json is forbidden in this repository package")
    if not (ROOT / ".mcp.json.example").is_file():
        raise ValidationError("missing inactive .mcp.json.example")
    hooks = load_json("hooks/hooks.json")
    if hooks != {"hooks": {}}:
        raise ValidationError("hooks must remain empty and non-executable")


def validate_snapshots() -> None:
    tool_path = ROOT / "references/tool-registry.snapshot.txt"
    if sha256(tool_path) != EXPECTED_TOOL_FILE_SHA256:
        raise ValidationError("tool registry snapshot file hash drift")
    tools = [line.strip() for line in tool_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(tools) != EXPECTED_TOOL_COUNT:
        raise ValidationError(f"expected {EXPECTED_TOOL_COUNT} tool names, found {len(tools)}")
    if len(set(tools)) != len(tools):
        raise ValidationError("duplicate tool names in registry snapshot")
    if tools != sorted(tools):
        raise ValidationError("tool registry snapshot must remain sorted")

    skill_path = ROOT / "references/operational-skills.snapshot.json"
    if sha256(skill_path) != EXPECTED_SKILL_FILE_SHA256:
        raise ValidationError("operational skill snapshot file hash drift")
    snapshot = load_json("references/operational-skills.snapshot.json")
    if snapshot.get("sourceRevision") != EXPECTED_SOURCE_REVISION:
        raise ValidationError("operational skill source revision drift")
    skills = snapshot.get("skills")
    if not isinstance(skills, list) or len(skills) != EXPECTED_OPERATIONAL_SKILL_COUNT:
        raise ValidationError("operational skill count drift")
    unique_tools = {
        tool
        for skill in skills
        if isinstance(skill, dict)
        for tool in skill.get("tools", [])
        if isinstance(tool, str)
    }
    if len(unique_tools) != EXPECTED_OPERATIONAL_UNIQUE_TOOL_COUNT:
        raise ValidationError("operational unique tool count drift")


def validate_guidance_surfaces() -> None:
    skill_files = sorted((ROOT / "skills").glob("*/SKILL.md"))
    observed: set[str] = set()
    for path in skill_files:
        frontmatter = parse_frontmatter(path)
        name = frontmatter.get("name", "")
        description = frontmatter.get("description", "")
        if name != path.parent.name:
            raise ValidationError(f"skill name/path mismatch: {path.relative_to(ROOT)}")
        if not description:
            raise ValidationError(f"skill description missing: {path.relative_to(ROOT)}")
        observed.add(name)
    if observed != EXPECTED_GUIDANCE_SKILLS:
        raise ValidationError(
            f"guidance skill set drift: expected {sorted(EXPECTED_GUIDANCE_SKILLS)}, found {sorted(observed)}"
        )

    agents = sorted((ROOT / "agents").glob("*.md"))
    commands = sorted((ROOT / "commands").glob("*.md"))
    if [path.name for path in agents] != ["sovereign-evidence-operator.md"]:
        raise ValidationError("unexpected agent surface")
    if [path.name for path in commands] != ["sovereign-inventory.md", "sovereign-preflight.md"]:
        raise ValidationError("unexpected command surface")
    for path in [*agents, *commands]:
        if not parse_frontmatter(path).get("description"):
            raise ValidationError(f"description missing: {path.relative_to(ROOT)}")


def validate_forbidden_surfaces() -> None:
    forbidden_names = {
        ".github",
        "Dockerfile",
        "compose.yml",
        "docker-compose.yml",
        "docker-compose.yaml",
        "launcher.py",
        "server.py",
    }
    violations = sorted(
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.name in forbidden_names
    )
    if violations:
        raise ValidationError(f"forbidden production surfaces present: {violations}")

    for path in ROOT.rglob("*"):
        if path.is_symlink():
            raise ValidationError(f"symlinks are forbidden: {path.relative_to(ROOT)}")


def main() -> int:
    checks = [
        validate_manifest,
        validate_boundary,
        validate_inactive_mcp_and_hooks,
        validate_snapshots,
        validate_guidance_surfaces,
        validate_forbidden_surfaces,
    ]
    try:
        for check in checks:
            check()
    except (OSError, ValidationError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "state": "repository-only-inactive-preview",
                "sourceRevision": EXPECTED_SOURCE_REVISION,
                "toolCount": EXPECTED_TOOL_COUNT,
                "operationalSkillCount": EXPECTED_OPERATIONAL_SKILL_COUNT,
                "guidanceSkillCount": len(EXPECTED_GUIDANCE_SKILLS),
                "activeMcpConfig": False,
                "executableHooks": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
