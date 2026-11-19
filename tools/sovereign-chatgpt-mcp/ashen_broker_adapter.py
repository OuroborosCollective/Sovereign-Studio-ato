"""Read-only, SHA-pinned Ashen advisor bridge for the existing Sovereign broker.

The existing Ashen director_bridge.py owns all Unity/Git/Image/MCP readbacks.
This module only validates authorized input and invokes that single owner.
No new network listeners, mutation tools, Unity state, or persistent issue files.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

SHA = re.compile(r"^[0-9a-f]{40}$")
IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
DEPT = re.compile(r"^[a-z][a-z0-9_]{2,48}$")
REPO = "https://github.com/OuroborosCollective/ARPG-ARE-D4SC-LOGIC"
ROOT = Path("/var/lib/unityarpg/.local/share/are-arpg")
MAX_ISSUE_BYTES = 32768

def validate_owner(owner_mode: bool) -> bool:
    if owner_mode is not True:
        raise ValueError("ASHEN_OWNER_REQUIRED")
    return True

def select_departments(values: Any, allowed: set[str],
                       *, full_council: bool = False) -> tuple[str, ...]:
    """Require explicit full-council intent; normal consultations use <=3 specialists."""
    if type(full_council) is not bool or not isinstance(allowed, set) or not isinstance(values, list):
        raise ValueError("ASHEN_INVALID_COUNCIL")
    bound = 28 if full_council else 3
    if not 1 <= len(values) <= bound:
        raise ValueError("ASHEN_COUNCIL_LIMIT")
    seen: set[str] = set()
    for name in values:
        if not isinstance(name, str) or not DEPT.fullmatch(name) or name not in allowed:
            raise ValueError("ASHEN_UNKNOWN_DEPARTMENT")
        if name in seen:
            raise ValueError("ASHEN_DUPLICATE_DEPARTMENT")
        seen.add(name)
    return tuple(values)

def validate_advice(values: Any, source_sha: str, unity_sha: str,
                    *, departments: set[str] | None = None) -> tuple[dict[str, Any], bytes]:
    if not isinstance(values, dict) or set(values) != {
            "department", "expected_source_sha", "expected_unity_sha", "issues"}:
        raise ValueError("ASHEN_INVALID_TOOL_ARGUMENTS")
    for key, pin in (("expected_source_sha", source_sha), ("expected_unity_sha", unity_sha)):
        if not isinstance(pin, str) or not SHA.fullmatch(pin) or values[key] != pin:
            raise ValueError("ASHEN_REVISION_MISMATCH")
    department = values["department"]
    if not isinstance(department, str) or not DEPT.fullmatch(department):
        raise ValueError("ASHEN_INVALID_DEPARTMENT")
    if departments is not None and department not in departments:
        raise ValueError("ASHEN_UNKNOWN_DEPARTMENT")
    issues = values["issues"]
    if not isinstance(issues, list) or not 1 <= len(issues) <= 64:
        raise ValueError("ASHEN_ISSUE_LIST_INVALID")
    seen = set()
    for item in issues:
        if not isinstance(item, dict) or set(item) != {"number", "state", "title", "url"}:
            raise ValueError("ASHEN_ISSUE_SCHEMA")
        n = item["number"]
        if type(n) is not int or n < 1 or n > 10000000 or n in seen:
            raise ValueError("ASHEN_ISSUE_ID")
        seen.add(n)
        if item["state"] not in ("open", "closed"):
            raise ValueError("ASHEN_ISSUE_STATE")
        title = item["title"]
        if not isinstance(title, str) or not 1 <= len(title) <= 300:
            raise ValueError("ASHEN_ISSUE_TITLE")
        if item["url"] != REPO + "/issues/" + str(n):
            raise ValueError("ASHEN_ISSUE_REPOSITORY")
    raw = json.dumps({"issues": issues}, ensure_ascii=True, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_ISSUE_BYTES:
        raise ValueError("ASHEN_ISSUE_BYTE_LIMIT")
    return {"department": department,
            "sourceVerification": "CALLER_SUPPLIED_UNVERIFIED"}, raw

class AshenBrokerAdapter:
    def __init__(self, private_owner_mode: bool):
        self.owner = private_owner_mode

    def _config(self, source: str, unity: str):
        validate_owner(self.owner)
        root_text = os.environ.get("SOVEREIGN_MCP_ASHEN_SOURCE_ROOT", "")
        source_pin = os.environ.get("SOVEREIGN_MCP_ASHEN_SOURCE_SHA", "")
        unity_pin = os.environ.get("SOVEREIGN_MCP_ASHEN_UNITY_SHA", "")
        image_id = os.environ.get("SOVEREIGN_MCP_ASHEN_IMAGE_ID", "")
        if not root_text or not SHA.fullmatch(source_pin) or not SHA.fullmatch(unity_pin) or not IMAGE.fullmatch(image_id):
            raise ValueError("ASHEN_RUNTIME_NOT_CONFIGURED")
        if source != source_pin or unity != unity_pin:
            raise ValueError("ASHEN_REVISION_MISMATCH")
        worktree = Path(root_text).resolve(strict=True)
        if worktree == ROOT or not worktree.is_relative_to(ROOT):
            raise ValueError("ASHEN_UNTRUSTED_SOURCE_PATH")
        return worktree, source_pin, unity_pin, image_id

    def advice(self, values: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(values, dict):
            raise ValueError("ASHEN_INVALID_TOOL_ARGUMENTS")
        worktree, source_sha, unity_sha, image_id = self._config(
            values.get("expected_source_sha"), values.get("expected_unity_sha"))
        catalog_path = worktree / "Tools/Director/neural_catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        if catalog.get("unity") != "6000.6.8f1":
            raise ValueError("ASHEN_UNITY_PIN_MISMATCH")
        departments = {x["id"] for x in catalog["departments"]}
        meta, raw = validate_advice(values, source_sha, unity_sha, departments=departments)
        # Do not trust a checked-out branch name: the bridge checks the actual
        # full commit, clean status, origin, Unity status and Docker image.
        with tempfile.TemporaryDirectory(prefix="ashen-issue-", dir=str(ROOT)) as tmp:
            p = Path(tmp) / "issues.json"
            p.write_bytes(raw)
            p.chmod(0o644)
            argv = [sys.executable,
                    str(worktree / "Tools/Director/neural_hub/director_bridge.py"),
                    "--source", str(worktree), "--source-sha", source_sha,
                    "--unity-sha", unity_sha, "--issues-file", str(p),
                    "--image-id", image_id, "--department", meta["department"]]
            proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  check=False, timeout=100)
        if proc.returncode != 0 or len(proc.stdout) > 262144 or len(proc.stderr) > 262144:
            raise RuntimeError("ASHEN_VERIFIED_BRIDGE_FAILED")
        data = json.loads(proc.stdout.decode("utf-8", "strict"))
        if (data.get("status") != "ADVISORY_ONLY" or data.get("execution") != "NONE"
                or data.get("sourceRevisionClaim") != source_sha
                or data.get("unityWorktreeShaVerified") != unity_sha
                or data.get("department") != meta["department"]
                or data.get("runtimeVerified") is not False
                or data.get("unityRuntimeVerified") is not False
                or data.get("issueDigest") != hashlib.sha256(raw).hexdigest()):
            raise ValueError("ASHEN_UNTRUSTED_PROBE_OUTPUT")
        return {"ok": True, "status": "ADVISORY_ONLY",
                "inputSource": meta["sourceVerification"], "result": data}

    def status(self, values: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(values, dict) or set(values) != {"expected_source_sha", "expected_unity_sha"}:
            raise ValueError("ASHEN_INVALID_TOOL_ARGUMENTS")
        source_root, source_sha, unity_sha, _ = self._config(values["expected_source_sha"],
                                                              values["expected_unity_sha"])
        # Read Git HEAD independently, not just a claimed revision from the caller.
        source_head = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"],
                                     capture_output=True, check=False, timeout=12)
        source_status = subprocess.run(["git", "-C", str(source_root), "status", "--porcelain"],
                                       capture_output=True, check=False, timeout=12)
        source_remote = subprocess.run(["git", "-C", str(source_root), "remote", "get-url", "origin"],
                                       capture_output=True, check=False, timeout=12)
        if (source_head.returncode or source_status.returncode or source_remote.returncode
                or source_head.stdout.decode().strip() != source_sha
                or source_status.stdout
                or source_remote.stdout.decode().strip().rstrip("/").removesuffix(".git").lower() != REPO.lower()):
            raise ValueError("ASHEN_SOURCE_READBACK_MISMATCH")
        config = "/var/lib/unityarpg/.local/share/unity-game-director/project.json"
        director = "/var/lib/unityarpg/.local/share/unity-game-director/scripts/director.py"
        proc = subprocess.run(["runuser", "-u", "unityarpg", "--", sys.executable,
                               director, "--config", config, "project_status"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=False, timeout=35)
        if proc.returncode or len(proc.stdout) > 262144:
            raise RuntimeError("ASHEN_DIRECTOR_STATUS_FAILED")
        data = json.loads(proc.stdout.decode("utf-8", "strict"))
        details = data.get("data") if isinstance(data, dict) else None
        if (data.get("ok") is not True or data.get("action") != "project_status"
                or not isinstance(details, dict)
                or details.get("source_commit_sha") != unity_sha
                or details.get("unity_version") != "6000.6.8f1"):
            raise ValueError("ASHEN_UNITY_REVISION_MISMATCH")
        project_root = Path(str(details.get("project_root", ""))).resolve(strict=True)
        if (not project_root.is_relative_to(Path("/var/lib/unityarpg/workspaces"))
                or details.get("tracked_changes") != []
                or details.get("untracked_game_inputs") != []):
            raise ValueError("ASHEN_UNITY_INPUTS_UNVERIFIED")
        def git_as_owner(*args):
            proc = subprocess.run(["runuser", "-u", "unityarpg", "--", "git",
                                   "-C", str(project_root), *args],
                                  capture_output=True, check=False, timeout=15)
            if proc.returncode or len(proc.stdout) > 262144:
                raise ValueError("ASHEN_GIT_READBACK_FAILED")
            return proc.stdout
        head = git_as_owner("rev-parse", "HEAD").decode().strip()
        remote = git_as_owner("remote", "get-url", "origin").decode().strip()
        if (head != unity_sha or
                remote.rstrip("/").removesuffix(".git").lower() != REPO.lower()):
            raise ValueError("ASHEN_UNITY_GIT_ORIGIN_OR_SHA_MISMATCH")
        porcelain = git_as_owner("status", "--porcelain=v1", "--untracked-files=all")
        return {"ok": True, "status": "DIRECTOR_READ_ONLY", "sourceRevision": source_sha,
                "unityWorktreeSha": unity_sha, "processUser": "unityarpg",
                "worktreeDirty": bool(porcelain), "gitStatusEntries": len(porcelain.splitlines()),
                "gitStatusSha256": hashlib.sha256(porcelain).hexdigest(),
                "runtimeVerified": False, "execution": "NONE"}

    def sources(self, values: dict[str, Any]) -> dict[str, Any]:
        """Inspect pinned, checked-in external source metadata only."""
        if not isinstance(values, dict) or set(values) != {"expected_source_sha", "expected_unity_sha"}:
            raise ValueError("ASHEN_INVALID_TOOL_ARGUMENTS")
        status = self.status(values)
        root, source_sha, _, _ = self._config(values["expected_source_sha"], values["expected_unity_sha"])
        catalog_bytes = (root / "Tools/Director/neural_hub/upstream_sources.json").read_bytes()
        catalog = json.loads(catalog_bytes.decode("utf-8", "strict"))
        entries = catalog.get("sources")
        if not isinstance(entries, list) or not 0 < len(entries) <= 64:
            raise ValueError("ASHEN_SOURCES_CATALOG_INVALID")
        safe = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("ASHEN_SOURCE_INVALID")
            if not isinstance(entry.get("id"), str) or not isinstance(entry.get("repository"), str):
                raise ValueError("ASHEN_SOURCE_INVALID")
            safe.append({
                "id": entry["id"], "repository": entry["repository"],
                "sourceSha": entry.get("sourceSha"),
                "license": entry.get("license"),
                "installedVerified": bool(entry.get("installedVerified") is True),
                "unityBuildVerified": bool(entry.get("unityBuildVerified") is True),
            })
        return {
            "ok": True, "status": "SOURCES_READ_ONLY", "sourceRevision": source_sha,
            "catalogSha256": hashlib.sha256(catalog_bytes).hexdigest(),
            "sourceRevisionVerified": True, "sourceCount": len(safe), "sources": safe,
            "unityWorktreeDirty": status["worktreeDirty"],
            "execution": "NONE", "runtimeVerified": False,
        }

    def consult(self, values: dict[str, Any]) -> dict[str, Any]:
        """Consult only explicitly named departments, never auto-broadcast."""
        if not isinstance(values, dict) or set(values) != {
            "expected_source_sha", "expected_unity_sha", "departments",
            "issues", "full_council"
        }:
            raise ValueError("ASHEN_INVALID_TOOL_ARGUMENTS")
        root, _, _, _ = self._config(values["expected_source_sha"], values["expected_unity_sha"])
        catalog = json.loads((root / "Tools/Director/neural_catalog.json").read_text(encoding="utf-8"))
        if catalog.get("unity") != "6000.6.8f1":
            raise ValueError("ASHEN_UNITY_PIN_MISMATCH")
        allowed = {item["id"] for item in catalog["departments"]}
        departments = select_departments(values["departments"], allowed,
                                         full_council=values["full_council"])
        before = self.status({
            "expected_source_sha": values["expected_source_sha"],
            "expected_unity_sha": values["expected_unity_sha"],
        })
        advisors = []
        snapshot_id = None
        digest = None
        for department in departments:
            result = self.advice({
                "expected_source_sha": values["expected_source_sha"],
                "expected_unity_sha": values["expected_unity_sha"],
                "department": department, "issues": values["issues"],
            })
            r = result["result"]
            if snapshot_id is not None and r["snapshotId"] != snapshot_id:
                raise ValueError("ASHEN_COUNCIL_SNAPSHOT_DRIFT")
            if digest is not None and r["issueDigest"] != digest:
                raise ValueError("ASHEN_COUNCIL_ISSUE_DRIFT")
            snapshot_id, digest = r["snapshotId"], r["issueDigest"]
            advisors.append({
                "department": department, "status": r["advisorStatus"],
                "proposal": r.get("proposal"), "snapshotId": snapshot_id,
            })
        after = self.status({
            "expected_source_sha": values["expected_source_sha"],
            "expected_unity_sha": values["expected_unity_sha"],
        })
        if before != after:
            raise ValueError("ASHEN_COUNCIL_GIT_STATUS_DRIFT")
        return {
            "ok": True, "status": "ADVISORY_ONLY", "execution": "NONE",
            "count": len(advisors), "advisors": advisors,
            "snapshotId": snapshot_id, "issueDigest": digest,
            "inputSource": "CALLER_SUPPLIED_UNVERIFIED",
            "unityWorktreeDirty": after["worktreeDirty"],
            "runtimeVerified": False,
        }
