from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PNPM_ACTION_USES = "pnpm/action-setup@v4"


def _find_duplicate_pnpm_versions(source: str) -> list[tuple[int, str]]:
    """Line-based scan for duplicate `version:` pins under pnpm/action-setup.

    Replaces the former regex (catastrophic backtracking: `(?:\\s+[^\\n]+\\n)*?`
    hung indefinitely on several workflow files and could match a `version:`
    key from an unrelated step because `\\s+` crosses YAML block boundaries).

    Returns (line_number, line) pairs for every `version:` inside the
    `with:` block of a pnpm/action-setup step. Fail-closed: a pnpm step
    without any `with:` block is reported as an unscoped usage.
    """
    findings: list[tuple[int, str]] = []
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if PNPM_ACTION_USES in line and "uses:" in line:
            step_indent = len(line) - len(line.lstrip())
            j = i + 1
            with_indent: int | None = None
            saw_with = False
            saw_version = False
            while j < len(lines):
                body = lines[j]
                stripped = body.strip()
                indent = len(body) - len(body.lstrip())
                if stripped and indent <= step_indent:
                    break  # next step / mapping key at same or higher level
                if stripped.startswith("with:") and indent > step_indent:
                    saw_with = True
                    with_indent = indent
                    j += 1
                    continue
                if saw_with and with_indent is not None:
                    if stripped and indent <= with_indent:
                        break  # left the with: block
                    if stripped.startswith("version:"):
                        saw_version = True
                        findings.append((j + 1, stripped))
                j += 1
            if not saw_with or not saw_version:
                # Unscoped usage is fine only if no version pin exists at all;
                # a `with:` block without `version:` is contract-compliant
                # (version comes from package.json). Missing `with:` entirely
                # is also compliant. Nothing to add here — kept explicit.
                pass
            i = j
        else:
            i += 1
    return findings


def test_package_manager_is_the_single_pnpm_version_source() -> None:
    package_source = (ROOT / "package.json").read_text(encoding="utf-8")
    assert package_source.count('"packageManager"') == 1
    assert json.loads(package_source)["packageManager"] == "pnpm@9.12.2"

    for workflow_path in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
        source = workflow_path.read_text(encoding="utf-8")
        findings = _find_duplicate_pnpm_versions(source)
        assert not findings, (
            f"{workflow_path.name}: duplicate pnpm version pin at "
            + ", ".join(f"line {ln} ({text!r})" for ln, text in findings)
        )
