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


def test_release_workflows_compare_keystore_apk_and_aab_certificates() -> None:
    for relative in (
        ".github/workflows/android.yml",
        ".github/workflows/android-release.yml",
    ):
        workflow = (REPO_ROOT / relative).read_text("utf-8")

        assert "ANDROID_EXPECTED_SIGNING_CERT_SHA256" in workflow
        assert "APK_CERT_SHA256" in workflow
        assert "AAB_CERT_SHA256" in workflow
        assert 'test "$APK_CERT_SHA256" = "$AAB_CERT_SHA256"' in workflow
        assert 'test "$APK_CERT_SHA256" = "$ANDROID_EXPECTED_SIGNING_CERT_SHA256"' in workflow
        assert "jarsigner -verify -strict" not in workflow
        assert "jarsigner -verify -certs" in workflow
        assert "android-signing-certificate-sha256.txt" in workflow
        assert "signature-diagnostics" in workflow
