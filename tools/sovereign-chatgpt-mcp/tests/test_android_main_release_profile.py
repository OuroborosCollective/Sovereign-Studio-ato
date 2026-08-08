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


def test_android_release_targets_api_36_with_compatible_toolchain() -> None:
    variables = (REPO_ROOT / "android" / "variables.gradle").read_text("utf-8")
    build_gradle = (REPO_ROOT / "android" / "build.gradle").read_text("utf-8")
    wrapper = (REPO_ROOT / "android" / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text("utf-8")
    manifest = (REPO_ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text("utf-8")

    assert "compileSdkVersion = 36" in variables
    assert "targetSdkVersion = 36" in variables
    assert "com.android.tools.build:gradle:8.9.1" in build_gradle
    assert "gradle-8.11.1-bin.zip" in wrapper
    assert 'tools:targetApi="36"' in manifest

    for relative in (
        ".github/workflows/android.yml",
        ".github/workflows/android-release.yml",
    ):
        workflow = (REPO_ROOT / relative).read_text("utf-8")
        assert "ANDROID_COMPILE_SDK: 36" in workflow
        assert "ANDROID_BUILD_TOOLS: 36.0.0" in workflow
        assert "compileSdk / targetSdk | 36 / 36" in workflow
