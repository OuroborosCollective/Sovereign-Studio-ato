from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/android-release.yml"
PACKAGE_JSON_PATH = REPOSITORY_ROOT / "package.json"


def test_android_release_pnpm_setup_uses_the_repository_package_manager_pin() -> None:
    workflow = WORKFLOW_PATH.read_text("utf-8")
    package_json = json.loads(PACKAGE_JSON_PATH.read_text("utf-8"))
    expected_block = """      - name: Setup pnpm
        uses: pnpm/action-setup@v4
        with:
          run_install: false
"""

    assert package_json["packageManager"] == "pnpm@9.12.2"
    assert expected_block in workflow
    assert "version: ${{ env.PNPM_VERSION }}" not in workflow
