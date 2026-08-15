#!/usr/bin/env python3
"""Fail-closed contract for the GitHub-App revision-locked VPS deployment skill."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SCHEMA = "sovereign.github-app-revision-locked-vps-deploy-skill.v1"


def fail(code: str) -> None:
    raise RuntimeError(code)


def text(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        fail(f"REQUIRED_FILE_MISSING:{relative}")
    return path.read_text("utf-8")


def git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    value = result.stdout.strip().lower()
    if result.returncode != 0 or not SHA_RE.fullmatch(value):
        fail("REPOSITORY_HEAD_INVALID")
    return value


def require(value: str, fragment: str, code: str) -> None:
    if fragment not in value:
        fail(f"{code}:{fragment}")


def inspect_contract(root: Path, revision: str) -> dict[str, Any]:
    auth_path = "tools/sovereign-chatgpt-mcp/github_installation_auth.py"
    runtime_path = "tools/sovereign-chatgpt-mcp/runtime.py"
    compose_path = "tools/sovereign-chatgpt-mcp/docker-compose.yml"
    installer_path = "tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh"
    owner_path = "scripts/sovereign-backend/owner_input_runtime.py"
    release_path = "tools/sovereign-chatgpt-mcp/deploy/reconcile-main-release.py"
    workflow_path = ".github/workflows/sovereign-coordinated-release.yml"

    auth = text(root, auth_path)
    runtime = text(root, runtime_path)
    compose = text(root, compose_path)
    installer = text(root, installer_path)
    owner = text(root, owner_path)
    release = text(root, release_path)
    workflow = text(root, workflow_path)

    require(auth, "access_tokens", "APP_INSTALLATION_TOKEN_ENDPOINT_MISSING")
    require(auth, "repositories", "APP_TOKEN_REPOSITORY_SCOPE_MISSING")
    require(auth, "@contextmanager", "APP_TOKEN_CONTEXT_MANAGER_MISSING")
    require(runtime, "Persistentes GITHUB_TOKEN ist im MCP-Container verboten", "PERSISTENT_TOKEN_BAN_MISSING")
    require(runtime, "UnavailableGitHubInstallationAuth", "FAIL_CLOSED_AUTH_MISSING")
    require(compose, "sovereign-github-app-private-key.pem", "READ_ONLY_KEY_MOUNT_MISSING")
    require(compose, ":ro", "READ_ONLY_KEY_MOUNT_NOT_READ_ONLY")
    require(installer, "prepare_mcp_github_app_secret", "INSTALLER_KEY_PROVISIONING_MISSING")
    require(installer, "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID", "INSTALLATION_BINDING_MISSING")
    require(owner, "failed", "OWNER_FAILED_STATUS_MISSING")
    require(release, "_deploy_mcp_from_ci_scope", "REVISION_SCOPED_MCP_DEPLOY_MISSING")
    require(release, "_runtime_readback", "RUNTIME_READBACK_MISSING")
    require(workflow, "branches: [main]", "MAIN_PUSH_TRIGGER_MISSING")
    require(workflow, "independent-target-runtime-readback", "INDEPENDENT_RUNTIME_READBACK_MISSING")
    require(workflow, "publish-production-verdict", "PRODUCTION_VERDICT_MISSING")

    paths = [auth_path, runtime_path, compose_path, installer_path, owner_path, release_path, workflow_path]
    hashes = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in paths
    }
    return {
        "schemaVersion": SCHEMA,
        "ok": True,
        "revision": revision,
        "checkedPaths": paths,
        "checkedPathSha256": hashes,
        "persistentGithubTokenAllowed": False,
        "installationTokenScoped": True,
        "runtimePromotionRequiresIndependentReceipt": True,
        "secretValuesReturned": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    expected = str(args.revision).lower()
    if not SHA_RE.fullmatch(expected):
        fail("EXPECTED_REVISION_INVALID")
    if git_head(root) != expected:
        fail("CHECKOUT_REVISION_MISMATCH")
    payload = inspect_contract(root, expected)
    output = Path(args.output).resolve()
    if root not in output.parents:
        fail("OUTPUT_OUTSIDE_REPOSITORY")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", "utf-8")
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({
            "schemaVersion": SCHEMA,
            "ok": False,
            "failureSha256": hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
            "secretValuesReturned": False,
        }, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        sys.exit(2)
