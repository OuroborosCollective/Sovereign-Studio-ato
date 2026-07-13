from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_main_android_validation_cannot_silently_skip_release_signing() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "android.yml").read_text("utf-8")

    assert "default: release" in workflow
    assert (
        "VALIDATION_PROFILE: ${{ github.event_name == 'pull_request' && 'standard' "
        "|| (inputs.validation_profile || 'release') }}"
    ) in workflow
    assert "Enforce signed production profile on main" in workflow
    assert "github.ref == 'refs/heads/main' && env.VALIDATION_PROFILE != 'release'" in workflow
    assert "Main production validation must use the release profile" in workflow
    assert "- name: Prepare Android signing key" in workflow
    assert "- name: Build signed release APK and AAB" in workflow
    assert "- name: Verify signed release artifacts" in workflow
    assert "Signed APK/AAB required" in workflow
