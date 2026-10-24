"""Opt-in, fail-closed NVIDIA OpenShell host preflight for Sovereign agents.

This does NOT switch production tools to OpenShell or attest their isolation.
No installer, credentials, repo mounts or privileged containers are launched.
The only sandbox workload is a fixed negative-egress canary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from typing import Any, Callable

EXPECTED_POLICY_SHA256 = "3240613e20e0107593edeb1ea8c3d3a88fc473e746a28854b839124677f56ca7"
EXPECTED_BOUNDARY_SHA256 = "73843b41eb04e8ef952074f344405cf5bac3c9c051347d7d73761836b7227832"
REQUIRED_DOMAINS = frozenset({"filesystem", "network_l4", "network_rest", "process", "landlock"})
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_CANARY_MARKER = "OPENSHELL_EGRESS_DENIED_BY_PROXY"

# Constant command; never interpolate model or repository input into the shell.
_CANARY_SCRIPT = (
    "set -eu; "
    "command -v curl >/dev/null || exit 91; "
    "if curl -fsS --connect-timeout 3 --max-time 8 "
    "https://api.github.com/zen >/dev/null 2>/tmp/openshell-deny.log; "
    "then exit 92; fi; "
    "grep -Fq '403 from proxy after CONNECT' /tmp/openshell-deny.log "
    "|| exit 93; "
    "printf 'OPENSHELL_EGRESS_DENIED_BY_PROXY\\n'"
)


class OpenShellPreflightError(RuntimeError):
    """An unverified host or policy blocks OpenShell activation."""


def _verified_file(path: Path, expected_sha256: str) -> Path:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise OpenShellPreflightError("policy_missing_or_symlink")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise OpenShellPreflightError("policy_digest_invalid")
    if path.stat().st_size > 65536:
        raise OpenShellPreflightError("policy_file_too_large")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise OpenShellPreflightError("policy_digest_mismatch")
    return path.resolve(strict=True)


def _external(argv: list[str], timeout: int, run: Callable[..., Any]) -> Any:
    # Never capture an ambient application secret or provider route for an agent.
    safe_env = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "XDG_CONFIG_HOME", "SSL_CERT_FILE")
        if key in os.environ
    }
    try:
        return run(
            argv, shell=False, check=False, capture_output=True,
            text=True, timeout=timeout, env=safe_env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OpenShellPreflightError("openshell_binary_missing_or_timed_out") from exc


def prove_policy(
    policy: Path,
    boundary: Path,
    policy_sha256: str,
    boundary_sha256: str,
    expected_version: str,
    *,
    run: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Verify exact file identities and the OpenShell prover boundary result."""
    policy_path = _verified_file(policy, policy_sha256)
    boundary_path = _verified_file(boundary, boundary_sha256)
    if not _VERSION_RE.fullmatch(expected_version):
        raise OpenShellPreflightError("expected_version_required")
    invoke = run or subprocess.run
    for executable in ("openshell", "openshell-prover"):
        result = _external([executable, "--version"], 8, invoke)
        if result.returncode != 0 or str(result.stdout).strip().split()[-1:] != [expected_version]:
            raise OpenShellPreflightError("openshell_version_mismatch")
    result = _external(
        ["openshell-prover", "check", str(policy_path), "--boundary", str(boundary_path), "--output", "json"],
        35,
        invoke,
    )
    if result.returncode != 0:
        raise OpenShellPreflightError("openshell_policy_not_within_boundary")
    try:
        body = json.loads(result.stdout)
        if not isinstance(body, dict):
            raise TypeError("prover result must be an object")
        domains = body["coverage"]["domains"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise OpenShellPreflightError("openshell_prover_invalid_json") from exc
    if (
        body.get("result") != "within_boundary"
        or not isinstance(domains, list)
        or any(not isinstance(domain, str) for domain in domains)
        or not REQUIRED_DOMAINS.issubset(domains)
    ):
        raise OpenShellPreflightError("openshell_prover_incomplete_coverage")
    return {
        "result": "within_boundary",
        "coverage": sorted(set(domains)),
        "policy_sha256": policy_sha256,
        "boundary_sha256": boundary_sha256,
        "openshell_version": expected_version,
        "truth_class": "TESTED_AT_REVISION",
        "runtime_verified": False,
    }


def sandbox_canary(policy: Path, *, run: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Run an explicit non-production negative-egress canary; no live agent switch."""
    policy_path = _verified_file(policy, EXPECTED_POLICY_SHA256)
    sandbox_name = "sovereign-canary-" + secrets.token_hex(8)
    invoke = run or subprocess.run
    command = [
        "openshell", "sandbox", "create", "--name", sandbox_name,
        "--no-auto-providers", "--no-tty", "--no-keep",
        "--policy", str(policy_path), "--", "/bin/sh", "-c", _CANARY_SCRIPT,
    ]
    result = _external(command, 120, invoke)
    if result.returncode != 0 or _CANARY_MARKER not in str(result.stdout).splitlines():
        raise OpenShellPreflightError("openshell_sandbox_network_denial_unverified")
    return {
        "result": "sandbox_canary_completed",
        "sandbox_name": sandbox_name,
        "policy_sha256": EXPECTED_POLICY_SHA256,
        "truth_class": "TESTED_AT_REVISION",
        "runtime_verified": False,  # Requires independent gateway/cleanup readback.
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Sovereign OpenShell canary preflight")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--expected-version", required=True, help="Reviewed CLI/prover release, e.g. 0.1.5")
    parser.add_argument("--apply-canary", action="store_true", help="Create one temporary sandbox; never enable production routing")
    args = parser.parse_args()
    try:
        result = prove_policy(
            args.policy, args.boundary, EXPECTED_POLICY_SHA256,
            EXPECTED_BOUNDARY_SHA256, args.expected_version,
        )
        if args.apply_canary:
            result["canary"] = sandbox_canary(args.policy)
    except OpenShellPreflightError as exc:
        print(json.dumps({"status": "BLOCKED", "reason_code": str(exc)}))
        return 1
    print(json.dumps({"status": "POLICY_PREFLIGHT_ONLY", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
