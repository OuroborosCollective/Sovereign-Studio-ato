from __future__ import annotations

import json
import zipfile
from pathlib import Path

import android_hardening
from android_hardening import AndroidHardeningRuntime


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, "utf-8")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(
        repo,
        "package.json",
        json.dumps(
            {
                "scripts": {"type-check": "true"},
                "dependencies": {"@capacitor/core": "^6.2.1"},
                "devDependencies": {"@capacitor/android": "^6.2.1", "@capacitor/cli": "6.2.1"},
            }
        ),
    )
    _write(repo, "capacitor.config.ts", "export default { server: { allowNavigation: ['*'] } };\n")
    _write(repo, "android/build.gradle", "classpath 'com.android.tools.build:gradle:8.3.0'\n")
    _write(
        repo,
        "android/app/build.gradle",
        """
android {
  namespace "com.example.app"
  compileSdk 35
  defaultConfig {
    applicationId "com.example.app"
    targetSdkVersion 35
    minSdkVersion 23
  }
  signingConfigs { release {} }
  buildTypes {
    release {
      signingConfig signingConfigs.release
      minifyEnabled true
      shrinkResources true
    }
  }
}
""",
    )
    _write(repo, "android/variables.gradle", "ext { compileSdkVersion = 35; targetSdkVersion = 35; minSdkVersion = 23 }\n")
    _write(repo, "android/gradle/wrapper/gradle-wrapper.properties", "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.4-bin.zip\n")
    _write(
        repo,
        "android/app/src/main/AndroidManifest.xml",
        """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
<uses-permission android:name="android.permission.QUERY_ALL_PACKAGES" />
<application android:allowBackup="false" android:usesCleartextTraffic="${usesCleartextTraffic}">
<activity android:name=".MainActivity" android:exported="true" />
</application></manifest>""",
    )
    _write(repo, "android/app/proguard-rules.pro", "-keep class com.getcapacitor.** { *; }\n")
    _write(repo, "android/app/src/main/assets/public/index.html", "<html><body>missing fallback</body></html>\n")
    _write(
        repo,
        ".github/workflows/android-release.yml",
        """name: Android
steps:
  - run: pnpm install --no-frozen-lockfile
  - run: cat .env
  - run: ./gradlew assembleRelease --stacktrace
  - run: sha256sum app-release.apk
""",
    )
    return repo


def _runtime(repo: Path, calls: list[list[str]] | None = None) -> AndroidHardeningRuntime:
    def run(argv, *, cwd, timeout=0, env=None):
        if calls is not None:
            calls.append(list(argv))
        return {"ok": True, "exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 1}

    return AndroidHardeningRuntime(lambda _workspace_id: repo, run)


def test_inventory_detects_capacitor_android_contract(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _runtime(repo).inventory("job-test")

    assert result["stack"]["capacitor"] is True
    assert result["android"]["application_id"] == "com.example.app"
    assert result["android"]["compile_sdk"] == 35
    assert result["android"]["target_sdk"] == 35
    assert result["android"]["min_sdk"] == 23
    assert result["android"]["agp"] == "8.3.0"
    assert result["android"]["gradle"] == "8.4"
    assert result["capacitor_majors"] == [6]


def test_scan_reports_security_reproducibility_and_boot_families(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _runtime(repo).scan("job-test")
    families = {finding["family"] for finding in result["findings"]}

    assert result["status"] == "BLOCKED"
    assert "webview_navigation_security" in families
    assert "ci_dependency_reproducibility" in families
    assert "ci_secret_exposure" in families
    assert "android_webview_boot" in families
    assert "android_artifact_signature" in families
    assert "android_permission_risk" in families


def test_runtime_evidence_classifies_first_causal_android_families(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _runtime(repo).analyze_evidence(
        "Manifest merger failed with multiple errors. FATAL EXCEPTION: main java.lang.IllegalStateException"
    )
    families = [item["family"] for item in result["families"]]

    assert result["status"] == "CLASSIFIED"
    assert "manifest_merge" in families
    assert "android_crash" in families
    assert len(result["evidence_sha256"]) == 64


def test_runtime_evidence_classifies_web_assets_and_exit_137(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _runtime(repo).analyze_evidence(
        "Android index exists FAIL; SOVEREIGN_BOOT_FALLBACK_V2 missing; Vite process was Killed with exit code 137"
    )
    families = [item["family"] for item in result["families"]]

    assert result["status"] == "CLASSIFIED"
    assert "web_assets_missing" in families
    assert "memory_pressure" in families


def test_scan_accepts_verified_generated_asset_pipeline_without_committed_bundle(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    package = json.loads((repo / "package.json").read_text("utf-8"))
    package["scripts"]["build:web"] = (
        "vite build && node scripts/release-html-runtime-fix.mjs "
        "&& node scripts/copy-dist-to-android.mjs"
    )
    (repo / "package.json").write_text(json.dumps(package), "utf-8")
    _write(
        repo,
        "scripts/release-html-runtime-fix.mjs",
        "const marker = 'SOVEREIGN_BOOT_FALLBACK_V2';\n",
    )
    _write(
        repo,
        "scripts/copy-dist-to-android.mjs",
        "const target = 'android/app/src/main/assets/public';\n",
    )

    result = _runtime(repo).scan("job-test")
    families = {finding["family"] for finding in result["findings"]}

    assert "android_webview_boot" not in families


def test_repair_plan_prioritizes_runtime_evidence_before_static_findings(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _runtime(repo).repair_plan("job-test", "FATAL EXCEPTION: main")

    assert result["status"] == "PLANNED"
    assert result["ordered_families"][0]["family"] == "android_crash"
    assert result["ordered_families"][0]["source"] == "runtime_evidence"
    assert result["rules"]["rerun_same_family_after_fix"] is True


def test_fast_suite_runs_static_checks_without_node_dependencies(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    calls: list[list[str]] = []
    result = _runtime(repo, calls).run_suite("job-test", "fast")

    assert [item["name"] for item in result["commands"]] == [
        "git_diff_check",
        "android_static_readiness",
    ]
    assert calls == [
        ["git", "diff", "--check"],
        ["node", "scripts/check-android-release-readiness.mjs"],
    ]
    assert not any("pnpm" in argv for call in calls for argv in call)
    assert result["execution_mode"] == "local_static_only"
    assert result["node_dependency_execution_local"] is False
    assert result["remote_ci_required"] is True
    assert result["remote_checks_required"] == [
        "typecheck",
        "unit_tests",
        "web_build",
        "capacitor_sync",
        "gradle_lint_test",
    ]
    assert result["static_scan"]["release_blockers"] > 0
    assert result["status"] == "FAIL"


def test_apk_artifact_inspection_uses_real_zip_entries_and_checksum(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(android_hardening.shutil, "which", lambda name: f"/usr/bin/{name}")
    artifact = repo / "android/app/build/outputs/apk/release/app-release.apk"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex")
        archive.writestr("resources.arsc", b"resources")
        archive.writestr("lib/arm64-v8a/libexample.so", b"native")

    result = _runtime(repo).inspect_artifact(
        "job-test",
        "android/app/build/outputs/apk/release/app-release.apk",
    )

    assert result["status"] == "VERIFIED"
    assert result["missing_entries"] == []
    assert result["abis"] == ["arm64-v8a"]
    assert result["signature_verified"] is True
    assert result["alignment_verified"] is True
    assert [item["tool"] for item in result["tool_verification"]] == ["apksigner", "zipalign"]
    assert len(result["sha256"]) == 64


def test_apk_artifact_inspection_never_claims_verified_without_native_tools(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(android_hardening.shutil, "which", lambda _name: None)
    artifact = repo / "android/app/build/outputs/apk/release/app-release.apk"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex")
        archive.writestr("resources.arsc", b"resources")

    result = _runtime(repo).inspect_artifact(
        "job-test",
        "android/app/build/outputs/apk/release/app-release.apk",
    )

    assert result["ok"] is False
    assert result["status"] == "INCOMPLETE_EVIDENCE"
    assert result["signature_verified"] is False
    assert result["alignment_verified"] is False
    assert len(result["verification_gaps"]) == 2
