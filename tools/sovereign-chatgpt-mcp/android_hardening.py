from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
TEXT_LIMIT = 2_000_000
EVIDENCE_LIMIT = 200_000
REQUIRED_ANDROID_FILES = (
    "android/build.gradle",
    "android/app/build.gradle",
    "android/gradle/wrapper/gradle-wrapper.properties",
    "android/app/src/main/AndroidManifest.xml",
    "capacitor.config.ts",
    "package.json",
)
HIGH_RISK_PERMISSIONS = {
    "android.permission.READ_SMS",
    "android.permission.RECEIVE_SMS",
    "android.permission.SEND_SMS",
    "android.permission.READ_CALL_LOG",
    "android.permission.WRITE_CALL_LOG",
    "android.permission.MANAGE_EXTERNAL_STORAGE",
    "android.permission.REQUEST_INSTALL_PACKAGES",
    "android.permission.SYSTEM_ALERT_WINDOW",
    "android.permission.QUERY_ALL_PACKAGES",
    "android.permission.ACCESS_BACKGROUND_LOCATION",
}
LOG_FAMILIES: tuple[tuple[str, str, str, tuple[str, ...], str], ...] = (
    ("gradle_dependency_resolution", "high", "Gradle dependency resolution failed", ("could not resolve all files", "could not find", "failed to resolve"), "Inspect repositories, locked versions and dependency constraints."),
    ("duplicate_classes", "high", "Duplicate Java/Kotlin classes", ("duplicate class", "already defined"), "Use dependencyInsight and remove or exclude the duplicate transitive dependency."),
    ("dex_overflow", "high", "DEX method/reference limit", ("too many field references", "too many method references", "dexindexoverflowexception"), "Enable multidex only when required and reduce dependency surface."),
    ("manifest_merge", "high", "Android manifest merge failure", ("manifest merger failed", "uses-sdk:minSdkVersion", "tools:replace specified"), "Inspect the merged manifest report and resolve the exact conflicting declaration."),
    ("resource_linking", "high", "Android resource linking failure", ("android resource linking failed", "aapt2", "resource .* not found"), "Validate resource names, SDK levels and generated Capacitor resources."),
    ("kotlin_compile", "high", "Kotlin compilation failure", ("compilation error. see log", "e: file://", "kotlin compiler"), "Fix the first compiler error and rerun the same Gradle task."),
    ("java_toolchain", "high", "Java/Gradle toolchain mismatch", ("unsupported class file major version", "invalid source release", "java home supplied is invalid"), "Align JDK, Gradle wrapper and Android Gradle Plugin versions."),
    ("android_sdk_missing", "high", "Android SDK component missing", ("sdk location not found", "failed to find target with hash string", "build-tools .* is missing"), "Install the exact platform/build-tools and set ANDROID_SDK_ROOT."),
    ("release_signing", "critical", "Release signing failure", ("keystore was tampered", "failed to read key", "signingconfig", "keystore file is missing"), "Verify keystore path, alias and credentials without exposing secret values."),
    ("r8_shrinker", "high", "R8/ProGuard shrinker failure", ("missing class", "r8: error", "proguard"), "Use missing_rules.txt and add the narrowest keep/dontwarn rules backed by runtime tests."),
    ("webview_cleartext", "high", "WebView cleartext/network policy failure", ("cleartext communication", "net::err_cleartext_not_permitted"), "Use HTTPS or an explicit debug-only network policy; keep release cleartext disabled."),
    ("tls_network", "high", "TLS or certificate validation failure", ("sslhandshakeexception", "certpathvalidatorexception", "net::err_cert"), "Fix trust chain, hostname or server certificate; never disable certificate validation in release."),
    ("capacitor_bridge", "high", "Capacitor native bridge/plugin failure", ("plugin not implemented", "unable to find implementation", "capacitor/plugin"), "Verify plugin version alignment, cap sync output and native registration."),
    ("web_assets_missing", "critical", "Packaged WebView assets missing", ("no workspace path", "file not found: readme.md", "android webview assets are missing", "err_file_not_found", "android index exists.*fail", "recovery fallback installed.*fail", "sovereign_boot_fallback_v2 missing"), "Rebuild web assets, run cap sync and verify packaged index/assets before release."),
    ("android_crash", "critical", "Android process crash", ("fatal exception", "fatal signal", "process: .* pid:"), "Preserve the first causal stack frame, reproduce, patch and add a regression test."),
    ("android_anr", "critical", "Application not responding", ("anr in ", "input dispatching timed out", "executing service"), "Move blocking work off the main thread and validate startup/interaction timing."),
    ("memory_pressure", "high", "Android memory failure", ("outofmemoryerror", "low memory killer", "failed to allocate", "exit code 137", "signal 9", "\\bkilled\\b"), "Distinguish host build-container pressure from app runtime memory, then rerun on the production GitHub Actions runner."),
)


@dataclass(frozen=True)
class Finding:
    family: str
    severity: str
    title: str
    evidence: str
    path: str = ""
    release_blocking: bool = False
    auto_fixable: bool = False
    strategy: str = ""


class AndroidHardeningRuntime:
    def __init__(
        self,
        repo_resolver: Callable[[str], Path],
        command_runner: Callable[..., dict[str, Any]],
        record_check: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._repo_resolver = repo_resolver
        self._command_runner = command_runner
        self._record_check = record_check

    def _repo(self, workspace_id: str) -> Path:
        return self._repo_resolver(workspace_id).resolve()

    @staticmethod
    def _read(path: Path) -> str:
        if not path.is_file():
            return ""
        if path.stat().st_size > TEXT_LIMIT:
            raise ValueError(f"Datei ist zu groß für Android-Analyse: {path.name}")
        return path.read_text("utf-8", errors="replace")

    @staticmethod
    def _number(pattern: str, text: str) -> int | None:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _version(pattern: str, text: str) -> str:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return match.group(1) if match else ""

    @staticmethod
    def _tool(name: str) -> dict[str, Any]:
        path = shutil.which(name)
        return {"available": bool(path), "path": path or ""}

    def inventory(self, workspace_id: str) -> dict[str, Any]:
        repo = self._repo(workspace_id)
        app_gradle = self._read(repo / "android/app/build.gradle")
        root_gradle = self._read(repo / "android/build.gradle")
        variables = self._read(repo / "android/variables.gradle")
        wrapper = self._read(repo / "android/gradle/wrapper/gradle-wrapper.properties")
        package_text = self._read(repo / "package.json")
        package = json.loads(package_text) if package_text else {}
        dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
        capacitor_versions = {
            name: str(dependencies.get(name, ""))
            for name in ("@capacitor/core", "@capacitor/android", "@capacitor/cli")
        }
        capacitor_majors = sorted(
            {
                int(match.group(1))
                for value in capacitor_versions.values()
                if (match := re.search(r"(\d+)", value))
            }
        )
        compile_sdk = self._number(r"compileSdk(?:Version)?\s*(?:=\s*)?(\d+)", app_gradle + "\n" + variables)
        target_sdk = self._number(r"targetSdkVersion\s*(?:=\s*)?(\d+)", app_gradle + "\n" + variables)
        min_sdk = self._number(r"minSdkVersion\s*(?:=\s*)?(\d+)", app_gradle + "\n" + variables)
        application_id = self._version(r"applicationId\s+[\"']([^\"']+)", app_gradle)
        namespace = self._version(r"namespace\s+[\"']([^\"']+)", app_gradle)
        agp = self._version(r"com\.android\.tools\.build:gradle:([^\"'\s]+)", root_gradle)
        gradle = self._version(r"gradle-([0-9][0-9.]+)-(?:all|bin)\.zip", wrapper)
        android_roots = [
            str(path.relative_to(repo))
            for path in (repo / "android", repo / "sovereign-studio-rn/android")
            if path.is_dir()
        ]
        return {
            "ok": True,
            "status": "INVENTORIED",
            "workspace_id": workspace_id,
            "stack": {
                "capacitor": (repo / "capacitor.config.ts").is_file(),
                "react_native_surface": (repo / "sovereign-studio-rn/package.json").is_file(),
                "android_roots": android_roots,
            },
            "android": {
                "application_id": application_id,
                "namespace": namespace,
                "compile_sdk": compile_sdk,
                "target_sdk": target_sdk,
                "min_sdk": min_sdk,
                "agp": agp,
                "gradle": gradle,
            },
            "capacitor_versions": capacitor_versions,
            "capacitor_majors": capacitor_majors,
            "files": {path: (repo / path).is_file() for path in REQUIRED_ANDROID_FILES},
            "toolchain": {
                name: self._tool(name)
                for name in ("node", "pnpm", "java", "javac", "adb", "sdkmanager", "apksigner", "zipalign")
            },
            "android_sdk_root_present": bool(
                os.getenv("ANDROID_SDK_ROOT") or os.getenv("ANDROID_HOME") or Path("/opt/android-sdk").is_dir()
            ),
        }

    @staticmethod
    def _finding(
        family: str,
        severity: str,
        title: str,
        evidence: str,
        *,
        path: str = "",
        release_blocking: bool | None = None,
        auto_fixable: bool = False,
        strategy: str = "",
    ) -> Finding:
        blocking = severity in {"critical", "high"} if release_blocking is None else release_blocking
        return Finding(family, severity, title, evidence[:2000], path, blocking, auto_fixable, strategy)

    def scan(self, workspace_id: str) -> dict[str, Any]:
        repo = self._repo(workspace_id)
        findings: list[Finding] = []
        inventory = self.inventory(workspace_id)
        android = inventory["android"]
        required_target = int(os.getenv("SOVEREIGN_ANDROID_REQUIRED_TARGET_SDK", "35"))

        for path, exists in inventory["files"].items():
            if not exists:
                findings.append(self._finding("android_project_structure", "critical", "Required Android file missing", path, path=path, strategy="Restore or regenerate the Android platform from the committed Capacitor contract."))

        app_gradle = self._read(repo / "android/app/build.gradle")
        root_gradle = self._read(repo / "android/build.gradle")
        manifest = self._read(repo / "android/app/src/main/AndroidManifest.xml")
        capacitor = self._read(repo / "capacitor.config.ts")
        workflow_path = (
            ".github/workflows/android.yml"
            if (repo / ".github/workflows/android.yml").is_file()
            else ".github/workflows/android-release.yml"
        )
        workflow = self._read(repo / workflow_path)
        package_text = self._read(repo / "package.json")
        proguard = self._read(repo / "android/app/proguard-rules.pro")
        release_html_fix = self._read(repo / "scripts/release-html-runtime-fix.mjs")
        copy_dist_to_android = self._read(repo / "scripts/copy-dist-to-android.mjs")
        android_asset_pipeline_configured = (
            "release-html-runtime-fix.mjs" in package_text
            and "copy-dist-to-android.mjs" in package_text
            and "SOVEREIGN_BOOT_FALLBACK_V2" in release_html_fix
            and "android/app/src/main/assets/public" in copy_dist_to_android
        )

        if android["compile_sdk"] is None or int(android["compile_sdk"]) < required_target:
            findings.append(self._finding("android_sdk_policy", "high", "compileSdk below configured release baseline", f"compileSdk={android['compile_sdk']}, required>={required_target}", path="android/app/build.gradle", strategy="Align compileSdk and installed Android platform with the release baseline."))
        if android["target_sdk"] is None or int(android["target_sdk"]) < required_target:
            findings.append(self._finding("android_sdk_policy", "high", "targetSdk below configured release baseline", f"targetSdk={android['target_sdk']}, required>={required_target}", path="android/variables.gradle", strategy="Raise targetSdk and test behavior changes on real devices/emulators."))
        if android["min_sdk"] is None:
            findings.append(self._finding("android_sdk_policy", "high", "minSdk is not detectable", "No minSdkVersion found", strategy="Declare one source of truth for minSdk."))

        majors = inventory["capacitor_majors"]
        if len(majors) != 1:
            findings.append(self._finding("capacitor_dependency_drift", "high", "Capacitor package major versions drift", json.dumps(inventory["capacitor_versions"], sort_keys=True), path="package.json", strategy="Align core, android and CLI to one tested major, then run cap sync and native tests."))
        if re.search(r"allowNavigation\s*:\s*\[\s*['\"]\*['\"]\s*\]", capacitor):
            findings.append(self._finding("webview_navigation_security", "critical", "Capacitor allows wildcard navigation", "allowNavigation=['*']", path="capacitor.config.ts", auto_fixable=True, strategy="Replace wildcard navigation with the exact trusted origin allowlist."))
        if re.search(r"android:usesCleartextTraffic\s*=\s*[\"']true[\"']", manifest):
            findings.append(self._finding("webview_cleartext", "critical", "Release manifest permits cleartext traffic", "android:usesCleartextTraffic=true", path="android/app/src/main/AndroidManifest.xml", strategy="Use a release-false manifest placeholder and debug-only override."))
        if manifest and 'android:allowBackup="false"' not in manifest:
            findings.append(self._finding("android_backup_exposure", "high", "Application backup is not explicitly disabled", "android:allowBackup=\"false\" missing", path="android/app/src/main/AndroidManifest.xml", auto_fixable=True, strategy="Disable backup or define audited backup/data extraction rules."))
        exported_components = re.findall(r"<(activity|service|receiver|provider)\b([^>]*)>", manifest, re.IGNORECASE)
        for component, attrs in exported_components:
            if "<intent-filter" in attrs and "android:exported" not in attrs:
                findings.append(self._finding("android_component_export", "high", f"{component} with intent filter lacks explicit exported state", attrs[:500], path="android/app/src/main/AndroidManifest.xml", strategy="Declare android:exported explicitly based on the real external contract."))
        permissions = set(re.findall(r"<uses-permission[^>]+android:name=[\"']([^\"']+)", manifest))
        for permission in sorted(permissions & HIGH_RISK_PERMISSIONS):
            findings.append(self._finding("android_permission_risk", "high", "High-risk Android permission declared", permission, path="android/app/src/main/AndroidManifest.xml", release_blocking=False, strategy="Prove the user-facing feature, runtime request flow and Play policy justification or remove it."))

        if "minifyEnabled true" not in app_gradle or "shrinkResources true" not in app_gradle:
            findings.append(self._finding("android_release_optimization", "medium", "Release shrinking is incomplete", "Expected minifyEnabled=true and shrinkResources=true", path="android/app/build.gradle", release_blocking=False, strategy="Enable both only with release smoke tests and audited keep rules."))
        if "signingConfig signingConfigs.release" not in app_gradle:
            findings.append(self._finding("android_release_signing", "critical", "Release build is not wired to release signing", "signingConfig signingConfigs.release missing", path="android/app/build.gradle", strategy="Wire release signing from external secrets and verify with apksigner."))
        if not proguard.strip() or "com.getcapacitor" not in proguard:
            findings.append(self._finding("r8_capacitor_contract", "high", "Capacitor R8 keep contract is missing", "No Capacitor keep rule detected", path="android/app/proguard-rules.pro", strategy="Add only required Capacitor/plugin reflection keep rules and validate a minified release."))

        dynamic_dependency = re.search(r"(?:implementation|api|classpath)\s+[\"'][^\"']+:(?:\+|latest\.(?:release|integration))['\"]", root_gradle + "\n" + app_gradle, re.IGNORECASE)
        if dynamic_dependency:
            findings.append(self._finding("gradle_reproducibility", "high", "Dynamic Gradle dependency version", dynamic_dependency.group(0), path="android/app/build.gradle", strategy="Pin the dependency and let dependency update tooling propose reviewed upgrades."))
        if "pnpm install --no-frozen-lockfile" in workflow:
            findings.append(self._finding("ci_dependency_reproducibility", "high", "Android release CI ignores the committed lockfile", "pnpm install --no-frozen-lockfile", path=".github/workflows/android-release.yml", auto_fixable=True, strategy="Use pnpm install --frozen-lockfile so release artifacts match reviewed dependencies."))
        if re.search(r"\bcat\s+\.env\b", workflow):
            findings.append(self._finding("ci_secret_exposure", "critical", "Android workflow prints an environment file", "cat .env", path=".github/workflows/android-release.yml", auto_fixable=True, strategy="Remove environment-file output and emit only non-secret boolean evidence."))
        if "--stacktrace" not in workflow:
            findings.append(self._finding("android_build_evidence", "medium", "Release Gradle task does not retain stacktrace evidence", "--stacktrace missing", path=".github/workflows/android-release.yml", release_blocking=False, strategy="Enable bounded stacktrace evidence and upload reports on failure."))
        if "apksigner verify" not in workflow and "jarsigner -verify" not in workflow:
            findings.append(self._finding("android_artifact_signature", "high", "Release workflow does not verify produced APK signature", "No apksigner/jarsigner verification step", path=".github/workflows/android-release.yml", strategy="Run apksigner verify --verbose --print-certs and retain non-secret evidence."))
        if "zipalign -c" not in workflow:
            findings.append(self._finding("android_artifact_alignment", "medium", "Release workflow does not verify APK alignment", "zipalign -c missing", path=".github/workflows/android-release.yml", release_blocking=False, strategy="Verify the final APK with the installed build-tools zipalign."))
        if "sha256sum" not in workflow:
            findings.append(self._finding("android_artifact_integrity", "high", "Release artifacts have no checksum evidence", "sha256sum missing", path=".github/workflows/android-release.yml", strategy="Generate checksums after signing and verify them before publishing."))
        if (
            "SOVEREIGN_BOOT_FALLBACK_V2" not in self._read(repo / "android/app/src/main/assets/public/index.html")
            and not android_asset_pipeline_configured
        ):
            findings.append(self._finding("android_webview_boot", "critical", "Packaged Android index lacks recovery fallback", "SOVEREIGN_BOOT_FALLBACK_V2 missing and no verified generation pipeline", path="android/app/src/main/assets/public/index.html", strategy="Rebuild/sync the real web bundle and preserve the verified boot fallback."))
        if "android:debuggable=\"true\"" in manifest or "debuggable true" in app_gradle:
            findings.append(self._finding("android_debug_release", "critical", "Debuggable configuration appears in release sources", "debuggable=true", strategy="Keep debuggable enabled only in the debug build type."))
        if "1.0.0-dev" in app_gradle:
            findings.append(self._finding("android_versioning", "medium", "Release versionName has a development fallback", "1.0.0-dev", path="android/app/build.gradle", release_blocking=False, strategy="Require explicit release version inputs in release tasks."))
        if len(inventory["stack"]["android_roots"]) > 1:
            findings.append(self._finding("android_surface_drift", "medium", "Multiple Android application roots detected", ", ".join(inventory["stack"]["android_roots"]), release_blocking=False, strategy="Declare the shipping surface and run separate gates for Capacitor and React Native roots."))

        findings.sort(key=lambda item: (SEVERITY_ORDER.get(item.severity, 99), item.family, item.path))
        counts = {severity: sum(1 for item in findings if item.severity == severity) for severity in SEVERITY_ORDER}
        blockers = [item for item in findings if item.release_blocking]
        return {
            "ok": not blockers,
            "status": "RELEASE_READY" if not blockers else "BLOCKED",
            "workspace_id": workspace_id,
            "inventory": inventory,
            "counts": counts,
            "release_blockers": len(blockers),
            "findings": [asdict(item) for item in findings],
            "next_action": "run_android_validation_suite_then_fix_highest_evidence_family" if findings else "build_and_verify_signed_artifacts",
        }

    def analyze_evidence(self, evidence: str) -> dict[str, Any]:
        text = str(evidence or "")
        encoded = text.encode("utf-8")
        if not text.strip():
            raise ValueError("Android-Evidence darf nicht leer sein")
        if len(encoded) > EVIDENCE_LIMIT:
            raise ValueError("Android-Evidence überschreitet das Limit")
        lowered = text.lower()
        matches: list[dict[str, Any]] = []
        for family, severity, title, signatures, strategy in LOG_FAMILIES:
            hit = next((signature for signature in signatures if re.search(signature, lowered, re.IGNORECASE)), "")
            if hit:
                matches.append({
                    "family": family,
                    "severity": severity,
                    "title": title,
                    "matched_signature": hit,
                    "strategy": strategy,
                })
        matches.sort(key=lambda item: SEVERITY_ORDER.get(str(item["severity"]), 99))
        return {
            "ok": bool(matches),
            "status": "CLASSIFIED" if matches else "UNKNOWN_FAILURE_FAMILY",
            "evidence_sha256": hashlib.sha256(encoded).hexdigest(),
            "families": matches,
            "next_action": "correlate_with_android_failure_family_scan_and_patch_first_causal_family",
        }

    def repair_plan(self, workspace_id: str, evidence: str = "") -> dict[str, Any]:
        scan = self.scan(workspace_id)
        runtime = self.analyze_evidence(evidence) if evidence.strip() else {"families": []}
        ordered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for family in runtime.get("families", []):
            name = str(family["family"])
            if name not in seen:
                ordered.append({**family, "source": "runtime_evidence"})
                seen.add(name)
        for finding in scan["findings"]:
            name = str(finding["family"])
            if name not in seen:
                ordered.append({**finding, "source": "repository_scan"})
                seen.add(name)
        return {
            "ok": True,
            "status": "PLANNED",
            "workspace_id": workspace_id,
            "ordered_families": ordered,
            "rules": {
                "fix_first_causal_failure": True,
                "small_exact_patches": True,
                "production_logic_changes_require_regression_test": True,
                "rerun_same_family_after_fix": True,
                "max_engine_extension_cycles": 2,
                "release_requires_zero_critical_and_high_blockers": True,
            },
        }

    def run_suite(self, workspace_id: str, profile: str = "fast") -> dict[str, Any]:
        repo = self._repo(workspace_id)
        selected = str(profile or "fast").strip().lower()
        commands: dict[str, list[tuple[str, list[str], Path]]] = {
            "fast": [
                ("git_diff_check", ["git", "diff", "--check"], repo),
                ("typecheck", ["pnpm", "run", "type-check"], repo),
                ("web_build", ["pnpm", "run", "build:web"], repo),
                ("android_static_readiness", ["node", "scripts/check-android-release-readiness.mjs"], repo),
            ],
            "standard": [
                ("git_diff_check", ["git", "diff", "--check"], repo),
                ("typecheck", ["pnpm", "run", "type-check"], repo),
                ("unit_tests", ["pnpm", "run", "test:unit"], repo),
                ("web_build", ["pnpm", "run", "build:web"], repo),
                ("capacitor_sync", ["pnpm", "exec", "cap", "sync", "android"], repo),
                ("android_static_readiness", ["node", "scripts/check-android-release-readiness.mjs"], repo),
                ("gradle_lint_test", ["./gradlew", "lintRelease", "testReleaseUnitTest", "--no-daemon", "--stacktrace"], repo / "android"),
            ],
            "release": [
                ("git_diff_check", ["git", "diff", "--check"], repo),
                ("release_verify", ["pnpm", "run", "verify:release"], repo),
                ("capacitor_sync", ["pnpm", "exec", "cap", "sync", "android"], repo),
                ("android_static_readiness", ["node", "scripts/check-android-release-readiness.mjs"], repo),
                ("gradle_release", ["./gradlew", "bundleRelease", "assembleRelease", "--no-daemon", "--stacktrace"], repo / "android"),
            ],
        }
        if selected not in commands:
            raise ValueError("profile muss fast, standard oder release sein")
        results: list[dict[str, Any]] = []
        for name, argv, cwd in commands[selected]:
            if not cwd.is_dir():
                result = {"ok": False, "exit_code": 127, "stdout": "", "stderr": f"Arbeitsverzeichnis fehlt: {cwd}"}
            elif argv[0] == "./gradlew" and not (cwd / "gradlew").is_file():
                result = {"ok": False, "exit_code": 127, "stdout": "", "stderr": "Gradle wrapper fehlt"}
            else:
                result = self._command_runner(argv, cwd=cwd, timeout=3600)
            entry = {"name": name, **result}
            results.append(entry)
            if self._record_check is not None:
                self._record_check(workspace_id, f"android:{selected}:{name}", result)
        static_scan = self.scan(workspace_id)
        ok = all(bool(item.get("ok")) for item in results) and bool(static_scan["ok"])
        return {
            "ok": ok,
            "status": "PASS" if ok else "FAIL",
            "workspace_id": workspace_id,
            "profile": selected,
            "commands": results,
            "static_scan": static_scan,
            "next_action": "inspect_first_failed_command_and_highest_severity_family" if not ok else "inspect_signed_artifacts",
        }

    def inspect_artifact(self, workspace_id: str, artifact_path: str) -> dict[str, Any]:
        repo = self._repo(workspace_id)
        candidate = (repo / artifact_path).resolve()
        if repo not in candidate.parents or not candidate.is_file():
            raise FileNotFoundError("Android-Artefakt fehlt oder liegt außerhalb des Workspace")
        if candidate.suffix.lower() not in {".apk", ".aab"}:
            raise ValueError("Nur APK- oder AAB-Artefakte sind zulässig")
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        with zipfile.ZipFile(candidate) as archive:
            names = archive.namelist()
            if candidate.suffix.lower() == ".apk":
                required = {"AndroidManifest.xml", "classes.dex", "resources.arsc"}
                present = {name for name in required if name in names}
                signed_v1 = any(name.upper().startswith("META-INF/") and name.upper().endswith((".RSA", ".DSA", ".EC")) for name in names)
                abis = sorted({parts[1] for name in names if name.startswith("lib/") and len((parts := name.split("/"))) > 2})
            else:
                required = {"base/manifest/AndroidManifest.xml"}
                present = {name for name in required if name in names}
                signed_v1 = any(name.upper().startswith("META-INF/") for name in names)
                abis = sorted({parts[3] for name in names if name.startswith("base/lib/") and len((parts := name.split("/"))) > 4})
        missing = sorted(required - present)
        verification: list[dict[str, Any]] = []
        verification_gaps: list[str] = []
        suffix = candidate.suffix.lower()
        if suffix == ".apk":
            apksigner = shutil.which("apksigner")
            zipalign = shutil.which("zipalign")
            if apksigner:
                verification.append({"tool": "apksigner", **self._command_runner([apksigner, "verify", "--verbose", "--print-certs", str(candidate)], cwd=repo, timeout=120)})
            else:
                verification_gaps.append("apksigner unavailable: APK signing is not cryptographically verified")
            if zipalign:
                verification.append({"tool": "zipalign", **self._command_runner([zipalign, "-c", "-P", "16", "4", str(candidate)], cwd=repo, timeout=120)})
            else:
                verification_gaps.append("zipalign unavailable: APK alignment is not verified")
        else:
            jarsigner = shutil.which("jarsigner")
            if jarsigner:
                verification.append({"tool": "jarsigner", **self._command_runner([jarsigner, "-verify", "-strict", "-certs", str(candidate)], cwd=repo, timeout=120)})
            else:
                verification_gaps.append("jarsigner unavailable: AAB signing is not cryptographically verified")

        signature_tools = {"apksigner"} if suffix == ".apk" else {"jarsigner"}
        signature_verified = any(
            item.get("tool") in signature_tools and bool(item.get("ok"))
            for item in verification
        )
        alignment_verified = suffix != ".apk" or any(
            item.get("tool") == "zipalign" and bool(item.get("ok"))
            for item in verification
        )
        ok = (
            not missing
            and signature_verified
            and alignment_verified
            and all(bool(item.get("ok")) for item in verification)
        )
        status = "VERIFIED" if ok else ("INCOMPLETE_EVIDENCE" if not missing and verification_gaps else "FAILED")
        return {
            "ok": ok,
            "status": status,
            "path": artifact_path,
            "bytes": candidate.stat().st_size,
            "sha256": digest,
            "required_entries": sorted(required),
            "missing_entries": missing,
            "archive_entries": len(names),
            "abis": abis,
            "v1_signature_material_present": signed_v1,
            "signature_verified": signature_verified,
            "alignment_verified": alignment_verified,
            "verification_gaps": verification_gaps,
            "tool_verification": verification,
        }
