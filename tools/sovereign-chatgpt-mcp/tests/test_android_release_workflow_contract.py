from __future__ import annotations

from pathlib import Path


WORKFLOW_PATH = Path(__file__).resolve().parents[3] / ".github/workflows/android-release.yml"


def test_android_release_pnpm_setup_has_valid_action_inputs() -> None:
    workflow = WORKFLOW_PATH.read_text("utf-8")
    expected_block = """      - name: Setup pnpm
        uses: pnpm/action-setup@v4
        with:
          version: ${{ env.PNPM_VERSION }}
          run_install: false
"""

    assert expected_block in workflow
    assert "uses: pnpm/action-setup@v4\n          run_install: false" not in workflow
