from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "deploy" / "validate-tunnel-doctor-report.py"
NO_AUTH_PROFILE = "sample_mcp_remote_no_auth"
EXPECTED_OAUTH_SUMMARY = (
    "HTTP 404 from "
    "http://127.0.0.1:8090/.well-known/oauth-protected-resource/mcp"
)


def base_checks() -> list[dict[str, str]]:
    return [
        {"id": "config_source", "status": "PASS", "summary": "profile"},
        {"id": "profile_load", "status": "PASS", "summary": "loaded"},
        {"id": "tunnel_id", "status": "PASS", "summary": "sensitive-marker"},
        {"id": "control_plane_api_key", "status": "PASS", "summary": "configured"},
        {"id": "mcp_target", "status": "PASS", "summary": "loopback"},
        {"id": "mcp_server_reachable", "status": "PASS", "summary": "HTTP 406"},
        {
            "id": "oauth_metadata",
            "status": "FAIL",
            "summary": EXPECTED_OAUTH_SUMMARY,
        },
        {"id": "health_listener", "status": "PASS", "summary": "ephemeral"},
        {"id": "ui", "status": "PASS", "summary": "ephemeral"},
        {"id": "codex_plugin", "status": "SKIP", "summary": "not installed"},
    ]


def run_validator(
    tmp_path: Path,
    payload: dict[str, object],
    *,
    doctor_exit_code: int,
    profile_sample: str = NO_AUTH_PROFILE,
) -> subprocess.CompletedProcess[str]:
    report = tmp_path / "doctor.json"
    report.write_text(json.dumps(payload), "utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            str(report),
            str(doctor_exit_code),
            profile_sample,
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def test_accepts_expected_metadata_404_only_for_no_auth_profile(tmp_path: Path) -> None:
    result = run_validator(
        tmp_path,
        {
            "result": "fail",
            "failed_checks": ["oauth_metadata"],
            "checks": base_checks(),
        },
        doctor_exit_code=2,
    )

    assert result.returncode == 0
    assert "no_auth_oauth_metadata_expected_absent" in result.stdout
    assert "sensitive-marker" not in result.stdout
    assert "sensitive-marker" not in result.stderr


def test_accepts_fully_successful_doctor_report(tmp_path: Path) -> None:
    checks = base_checks()
    checks[6] = {"id": "oauth_metadata", "status": "SKIP", "summary": "not required"}
    result = run_validator(
        tmp_path,
        {"result": "ok", "checks": checks},
        doctor_exit_code=0,
    )

    assert result.returncode == 0
    assert "doctor_result_ok" in result.stdout


@pytest.mark.parametrize(
    ("doctor_exit_code", "profile_sample", "oauth_summary", "extra_failure"),
    [
        (2, "sample_mcp_with_dcr", EXPECTED_OAUTH_SUMMARY, None),
        (
            2,
            NO_AUTH_PROFILE,
            "HTTP 500 from http://127.0.0.1:8090/.well-known/oauth-protected-resource/mcp",
            None,
        ),
        (1, NO_AUTH_PROFILE, EXPECTED_OAUTH_SUMMARY, None),
        (2, NO_AUTH_PROFILE, EXPECTED_OAUTH_SUMMARY, "health_listener"),
    ],
)
def test_rejects_any_broader_or_inconsistent_doctor_failure(
    tmp_path: Path,
    doctor_exit_code: int,
    profile_sample: str,
    oauth_summary: str,
    extra_failure: str | None,
) -> None:
    checks = base_checks()
    checks[6]["summary"] = oauth_summary
    failed_checks = ["oauth_metadata"]
    if extra_failure is not None:
        for check in checks:
            if check["id"] == extra_failure:
                check["status"] = "FAIL"
        failed_checks.append(extra_failure)

    result = run_validator(
        tmp_path,
        {
            "result": "fail",
            "failed_checks": failed_checks,
            "checks": checks,
        },
        doctor_exit_code=doctor_exit_code,
        profile_sample=profile_sample,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "tunnel doctor contract blocked: report validation failed\n"
    )
