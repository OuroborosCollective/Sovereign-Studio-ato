from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_package_manager_is_the_single_pnpm_version_source() -> None:
    package_source = (ROOT / "package.json").read_text(encoding="utf-8")
    assert package_source.count('"packageManager"') == 1
    assert json.loads(package_source)["packageManager"] == "pnpm@9.12.2"

    duplicate_version = re.compile(
        r"uses:\s*pnpm/action-setup@v4\s*\n\s+with:\s*\n(?:\s+[^\n]+\n)*?\s+version:",
        re.MULTILINE,
    )
    for workflow_path in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
        source = workflow_path.read_text(encoding="utf-8")
        assert not duplicate_version.search(source), workflow_path.name
