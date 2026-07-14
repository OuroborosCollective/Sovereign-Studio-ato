#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


NO_AUTH_PROFILE = "sample_mcp_remote_no_auth"
EXPECTED_OAUTH_SUMMARY = (
    "HTTP 404 from "
    "http://127.0.0.1:8090/.well-known/oauth-protected-resource/mcp"
)
REQUIRED_PASS_CHECKS = {
    "config_source",
    "profile_load",
    "tunnel_id",
    "control_plane_api_key",
    "mcp_target",
    "mcp_server_reachable",
    "health_listener",
    "ui",
}


class DoctorContractError(ValueError):
    pass


def _checks_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_checks = payload.get("checks")
    if not isinstance(raw_checks, list):
        raise DoctorContractError("checks must be a list")

    checks: dict[str, dict[str, Any]] = {}
    for raw_check in raw_checks:
        if not isinstance(raw_check, dict):
            raise DoctorContractError("each check must be an object")
        check_id = raw_check.get("id")
        status = raw_check.get("status")
        if not isinstance(check_id, str) or not check_id:
            raise DoctorContractError("each check needs an id")
        if check_id in checks:
            raise DoctorContractError("check ids must be unique")
        if status not in {"PASS", "FAIL", "SKIP"}:
            raise DoctorContractError("check status is invalid")
        checks[check_id] = raw_check
    return checks


def validate_report(
    payload: dict[str, Any],
    doctor_exit_code: int,
    profile_sample: str,
) -> str:
    checks = _checks_by_id(payload)
    result = payload.get("result")
    raw_failed = payload.get("failed_checks", [])
    if not isinstance(raw_failed, list) or not all(
        isinstance(item, str) for item in raw_failed
    ):
        raise DoctorContractError("failed_checks must be a string list")
    failed_checks = list(raw_failed)

    actual_failures = sorted(
        check_id
        for check_id, check in checks.items()
        if check.get("status") == "FAIL"
    )
    if sorted(failed_checks) != actual_failures:
        raise DoctorContractError("failed_checks do not match check statuses")

    if doctor_exit_code == 0:
        if result != "ok" or failed_checks:
            raise DoctorContractError("successful doctor result is inconsistent")
        return "doctor_result_ok"

    if doctor_exit_code != 2:
        raise DoctorContractError("unexpected doctor exit code")
    if profile_sample != NO_AUTH_PROFILE:
        raise DoctorContractError("failed doctor is not using the no-auth profile")
    if result != "fail" or failed_checks != ["oauth_metadata"]:
        raise DoctorContractError("doctor has failures beyond expected OAuth absence")

    missing_passes = sorted(
        check_id
        for check_id in REQUIRED_PASS_CHECKS
        if checks.get(check_id, {}).get("status") != "PASS"
    )
    if missing_passes:
        raise DoctorContractError("required doctor checks did not pass")

    oauth_check = checks.get("oauth_metadata")
    if oauth_check is None:
        raise DoctorContractError("OAuth metadata check is missing")
    if oauth_check.get("status") != "FAIL":
        raise DoctorContractError("OAuth metadata status is inconsistent")
    if oauth_check.get("summary") != EXPECTED_OAUTH_SUMMARY:
        raise DoctorContractError("OAuth metadata failure is not the expected 404")

    return "no_auth_oauth_metadata_expected_absent"


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(
            "tunnel doctor contract blocked: invalid validator arguments",
            file=sys.stderr,
        )
        return 1

    report_path = Path(argv[1])
    try:
        doctor_exit_code = int(argv[2])
        payload = json.loads(report_path.read_text("utf-8-sig"))
        if not isinstance(payload, dict):
            raise DoctorContractError("doctor report must be an object")
        verdict = validate_report(payload, doctor_exit_code, argv[3])
    except (DoctorContractError, OSError, UnicodeError, ValueError):
        print("tunnel doctor contract blocked: report validation failed", file=sys.stderr)
        return 1

    print(f"tunnel doctor contract verified: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
