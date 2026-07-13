from __future__ import annotations

import os
import re
from typing import Any

import requests

from self_update import SelfUpdateRuntime

COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
INPUT_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ALLOWED_MERGE_METHODS = {"merge", "squash", "rebase"}
SUCCESSFUL_CHECK_CONCLUSIONS = {"success", "neutral", "skipped"}
RERUN_FAILED_CONCLUSIONS = {"failure"}
RERUN_ALL_CONCLUSIONS = {"cancelled", "timed_out", "action_required", "stale"}
MCP_PATH_PREFIX = "tools/sovereign-chatgpt-mcp/"
MCP_WORKFLOW_PATH = ".github/workflows/sovereign-chatgpt-mcp.yml"
SENSITIVE_INPUT_PARTS = {"secret", "token", "password", "passwd", "private", "keystore", "credential"}


def _enabled(name: str) -> bool:
    return os.getenv(name, "0").strip() == "1"


class GitHubAdminRuntime:
    def __init__(self, self_update: SelfUpdateRuntime, session: requests.Session | None = None) -> None:
        self.self_update = self_update
        self.repository = os.getenv(
            "SOVEREIGN_MCP_REPOSITORY",
            "OuroborosCollective/Sovereign-Studio-ato",
        ).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise RuntimeError("SOVEREIGN_MCP_REPOSITORY ist ungültig")
        self.token = os.getenv("GITHUB_TOKEN", "").strip()
        self.session = session or requests.Session()
        self.api_root = "https://api.github.com"
        self.allowed_workflows = {
            item.strip()
            for item in os.getenv(
                "SOVEREIGN_MCP_ALLOWED_WORKFLOWS",
                "android.yml,android-release.yml,sovereign-chatgpt-mcp.yml",
            ).split(",")
            if item.strip()
        }

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("GITHUB_TOKEN fehlt im privaten Broker")
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
        timeout: int = 30,
    ) -> Any:
        try:
            response = self.session.request(
                method,
                f"{self.api_root}{path}",
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"GitHub API ist nicht erreichbar: {exc}") from exc
        if response.status_code not in expected:
            text = response.text[:2000]
            raise RuntimeError(f"GitHub API {method} {path} fehlgeschlagen: HTTP {response.status_code} {text}")
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    @staticmethod
    def _pr_number(value: int) -> int:
        number = int(value)
        if number < 1:
            raise ValueError("pr_number muss positiv sein")
        return number

    @staticmethod
    def _run_id(value: int) -> int:
        run_id = int(value)
        if run_id < 1:
            raise ValueError("run_id muss positiv sein")
        return run_id

    def _pull(self, pr_number: int) -> dict[str, Any]:
        payload = self._request("GET", f"/repos/{self.repository}/pulls/{self._pr_number(pr_number)}")
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub PR-Antwort ist ungültig")
        return payload

    def _check_state(self, head_sha: str) -> dict[str, Any]:
        if not COMMIT_SHA_RE.fullmatch(head_sha):
            raise ValueError("PR-Head ist kein vollständiger Commit-SHA")
        check_payload = self._request(
            "GET",
            f"/repos/{self.repository}/commits/{head_sha}/check-runs",
            params={"per_page": 100},
        )
        status_payload = self._request("GET", f"/repos/{self.repository}/commits/{head_sha}/status")
        check_runs = check_payload.get("check_runs", []) if isinstance(check_payload, dict) else []
        legacy_statuses = status_payload.get("statuses", []) if isinstance(status_payload, dict) else []
        normalized: list[dict[str, Any]] = []
        pending: list[str] = []
        failed: list[str] = []
        for check in check_runs:
            if not isinstance(check, dict):
                continue
            name = str(check.get("name") or "unnamed")
            status = str(check.get("status") or "")
            conclusion = check.get("conclusion")
            normalized.append({"name": name, "status": status, "conclusion": conclusion})
            if status != "completed" or conclusion is None:
                pending.append(name)
            elif str(conclusion) not in SUCCESSFUL_CHECK_CONCLUSIONS:
                failed.append(name)

        legacy_state = str(status_payload.get("state") or "pending") if isinstance(status_payload, dict) else "pending"
        if legacy_state in {"failure", "error"}:
            failed.extend(
                str(item.get("context") or "legacy-status")
                for item in legacy_statuses
                if isinstance(item, dict) and str(item.get("state")) in {"failure", "error"}
            )
        elif legacy_state == "pending" and legacy_statuses:
            pending.extend(
                str(item.get("context") or "legacy-status")
                for item in legacy_statuses
                if isinstance(item, dict) and str(item.get("state")) == "pending"
            )

        has_evidence = bool(normalized or legacy_statuses)
        if not has_evidence and not _enabled("SOVEREIGN_MCP_ALLOW_MERGE_WITHOUT_CHECKS"):
            pending.append("no_check_evidence_reported")
        return {
            "ok": not pending and not failed,
            "head_sha": head_sha,
            "checks": normalized,
            "legacy_state": legacy_state,
            "has_check_evidence": has_evidence,
            "pending": list(dict.fromkeys(pending)),
            "failed": list(dict.fromkeys(failed)),
        }

    def pr_status(self, *, pr_number: int) -> dict[str, Any]:
        pull = self._pull(pr_number)
        head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
        head_sha = str(head.get("sha") or "")
        checks = self._check_state(head_sha)
        return {
            "ok": True,
            "status": "VERIFIED",
            "pr_number": int(pull.get("number") or pr_number),
            "title": str(pull.get("title") or ""),
            "state": str(pull.get("state") or ""),
            "draft": bool(pull.get("draft")),
            "mergeable": pull.get("mergeable"),
            "mergeable_state": str(pull.get("mergeable_state") or "unknown"),
            "head_sha": head_sha,
            "base_ref": str((pull.get("base") or {}).get("ref") or ""),
            "checks": checks,
            "url": str(pull.get("html_url") or ""),
        }

    def rerun_failed_workflows(self, *, pr_number: int) -> dict[str, Any]:
        if not _enabled("SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL"):
            return {"ok": False, "status": "BLOCKED", "blocker": "Workflow-Steuerung ist nicht aktiviert"}
        pull = self._pull(pr_number)
        head_sha = str((pull.get("head") or {}).get("sha") or "")
        if not COMMIT_SHA_RE.fullmatch(head_sha):
            raise ValueError("PR-Head ist kein vollständiger Commit-SHA")
        restarted: list[dict[str, Any]] = []
        for page in range(1, 11):
            payload = self._request(
                "GET",
                f"/repos/{self.repository}/actions/runs",
                params={"head_sha": head_sha, "event": "pull_request", "per_page": 100, "page": page},
            )
            runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
            for run in runs:
                if not isinstance(run, dict):
                    continue
                run_id = int(run.get("id") or 0)
                conclusion = str(run.get("conclusion") or "")
                if run_id < 1:
                    continue
                if conclusion in RERUN_FAILED_CONCLUSIONS:
                    endpoint = f"/repos/{self.repository}/actions/runs/{run_id}/rerun-failed-jobs"
                elif conclusion in RERUN_ALL_CONCLUSIONS:
                    endpoint = f"/repos/{self.repository}/actions/runs/{run_id}/rerun"
                else:
                    continue
                self._request("POST", endpoint, expected=(201, 202), timeout=30)
                restarted.append({"run_id": run_id, "name": str(run.get("name") or ""), "previous_conclusion": conclusion})
            if len(runs) < 100:
                break
        return {
            "ok": True,
            "status": "RERUN_REQUESTED" if restarted else "NOT_NEEDED",
            "pr_number": self._pr_number(pr_number),
            "head_sha": head_sha,
            "restarted": restarted,
        }

    def dispatch_workflow(self, *, workflow: str, ref: str = "main", inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        if not _enabled("SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL"):
            return {"ok": False, "status": "BLOCKED", "blocker": "Workflow-Steuerung ist nicht aktiviert"}
        selected = str(workflow or "").strip()
        if selected not in self.allowed_workflows:
            raise ValueError("Workflow ist nicht freigegeben")
        selected_ref = str(ref or "main").strip()
        if not REF_RE.fullmatch(selected_ref) or ".." in selected_ref:
            raise ValueError("Workflow-Ref ist ungültig")
        clean_inputs: dict[str, str] = {}
        for key, value in (inputs or {}).items():
            name = str(key)
            if not INPUT_KEY_RE.fullmatch(name):
                raise ValueError("Workflow-Input-Name ist ungültig")
            lowered = name.lower()
            if any(part in lowered for part in SENSITIVE_INPUT_PARTS):
                raise ValueError("Secrets dürfen nicht als Workflow-Input übergeben werden")
            text = str(value)
            if len(text) > 500:
                raise ValueError("Workflow-Input ist zu lang")
            clean_inputs[name] = text
        payload = self._request(
            "POST",
            f"/repos/{self.repository}/actions/workflows/{selected}/dispatches",
            json_body={"ref": selected_ref, "inputs": clean_inputs},
            expected=(200,),
        )
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub Workflow-Dispatch-Antwort ist ungültig")
        run_id = int(payload.get("workflow_run_id") or 0)
        run_url = str(payload.get("run_url") or "").strip()
        html_url = str(payload.get("html_url") or "").strip()
        if run_id < 1 or not run_url or not html_url:
            raise RuntimeError("GitHub lieferte keine vollständige Workflow-Run-Evidence")
        return {
            "ok": True,
            "status": "DISPATCHED",
            "workflow": selected,
            "ref": selected_ref,
            "inputs": clean_inputs,
            "run_id": run_id,
            "run_url": run_url,
            "url": html_url,
        }

    def workflow_run_status(self, *, run_id: int) -> dict[str, Any]:
        selected = self._run_id(run_id)
        run = self._request("GET", f"/repos/{self.repository}/actions/runs/{selected}")
        jobs_payload = self._request(
            "GET",
            f"/repos/{self.repository}/actions/runs/{selected}/jobs",
            params={"per_page": 100},
        )
        artifacts_payload = self._request(
            "GET",
            f"/repos/{self.repository}/actions/runs/{selected}/artifacts",
            params={"per_page": 100},
        )
        jobs: list[dict[str, Any]] = []
        for job in jobs_payload.get("jobs", []) if isinstance(jobs_payload, dict) else []:
            if not isinstance(job, dict):
                continue
            failed_steps = [
                str(step.get("name") or "")
                for step in job.get("steps", [])
                if isinstance(step, dict) and str(step.get("conclusion") or "") not in {"", "success", "skipped"}
            ]
            jobs.append(
                {
                    "id": int(job.get("id") or 0),
                    "name": str(job.get("name") or ""),
                    "status": str(job.get("status") or ""),
                    "conclusion": job.get("conclusion"),
                    "failed_steps": failed_steps,
                }
            )
        artifacts: list[dict[str, Any]] = []
        for artifact in artifacts_payload.get("artifacts", []) if isinstance(artifacts_payload, dict) else []:
            if not isinstance(artifact, dict):
                continue
            artifacts.append(
                {
                    "id": int(artifact.get("id") or 0),
                    "name": str(artifact.get("name") or ""),
                    "size_in_bytes": int(artifact.get("size_in_bytes") or 0),
                    "expired": bool(artifact.get("expired")),
                    "created_at": str(artifact.get("created_at") or ""),
                    "updated_at": str(artifact.get("updated_at") or ""),
                }
            )
        run_status = str(run.get("status") or "") if isinstance(run, dict) else ""
        conclusion = run.get("conclusion") if isinstance(run, dict) else None
        completed = run_status == "completed"
        passed = completed and conclusion == "success"
        return {
            "ok": passed,
            "evidence_read": True,
            "validation_complete": completed,
            "passed": passed,
            "status": "PASS" if passed else ("RUNNING" if not completed else "FAIL"),
            "run_id": selected,
            "workflow": str(run.get("name") or "") if isinstance(run, dict) else "",
            "head_sha": str(run.get("head_sha") or "") if isinstance(run, dict) else "",
            "run_status": run_status,
            "conclusion": conclusion,
            "url": str(run.get("html_url") or "") if isinstance(run, dict) else "",
            "jobs": jobs,
            "artifacts": artifacts,
            "next_action": (
                "import_and_inspect_android_artifacts"
                if passed and artifacts
                else ("recheck_workflow_run_status" if not completed else "analyze_failed_workflow_steps")
            ),
        }

    def _changed_files(self, pr_number: int) -> list[str]:
        files: list[str] = []
        for page in range(1, 31):
            payload = self._request(
                "GET",
                f"/repos/{self.repository}/pulls/{self._pr_number(pr_number)}/files",
                params={"per_page": 100, "page": page},
            )
            if not isinstance(payload, list):
                raise RuntimeError("GitHub PR-Dateiliste ist ungültig")
            files.extend(str(item.get("filename") or "") for item in payload if isinstance(item, dict))
            if len(payload) < 100:
                break
        return files

    def merge_pr(
        self,
        *,
        pr_number: int,
        expected_head_sha: str,
        merge_method: str = "squash",
        self_update_after_merge: bool = True,
    ) -> dict[str, Any]:
        if not _enabled("SOVEREIGN_MCP_ENABLE_PR_MERGE"):
            return {"ok": False, "status": "BLOCKED", "blocker": "PR-Merge ist nicht aktiviert"}
        number = self._pr_number(pr_number)
        expected = str(expected_head_sha or "").strip().lower()
        if not COMMIT_SHA_RE.fullmatch(expected):
            raise ValueError("expected_head_sha muss ein vollständiger Commit-SHA sein")
        method = str(merge_method or "squash").strip().lower()
        if method not in ALLOWED_MERGE_METHODS:
            raise ValueError("merge_method muss merge, squash oder rebase sein")

        status = self.pr_status(pr_number=number)
        if status["state"] != "open":
            return {"ok": False, "status": "BLOCKED", "blocker": "PR ist nicht offen", "pr": status}
        if status["draft"]:
            return {"ok": False, "status": "BLOCKED", "blocker": "Draft-PR muss zuerst bereit sein", "pr": status}
        if status["base_ref"] != "main":
            return {"ok": False, "status": "BLOCKED", "blocker": "PR zielt nicht auf main", "pr": status}
        if status["head_sha"] != expected:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "PR-Head stimmt nicht mit der Bestätigung überein",
                "actual_head_sha": status["head_sha"],
                "expected_head_sha": expected,
            }
        if status["mergeable"] is not True:
            return {"ok": False, "status": "BLOCKED", "blocker": "GitHub bestätigt den PR noch nicht als mergefähig", "pr": status}
        if not status["checks"]["ok"]:
            return {"ok": False, "status": "BLOCKED", "blocker": "PR-Checks sind nicht vollständig grün", "pr": status}

        changed_files = self._changed_files(number)
        payload = self._request(
            "PUT",
            f"/repos/{self.repository}/pulls/{number}/merge",
            json_body={"sha": expected, "merge_method": method},
            expected=(200,),
            timeout=60,
        )
        if not isinstance(payload, dict) or not bool(payload.get("merged")):
            raise RuntimeError(str((payload or {}).get("message") or "GitHub meldet keinen erfolgreichen Merge"))
        merge_sha = str(payload.get("sha") or "").lower()
        if not COMMIT_SHA_RE.fullmatch(merge_sha):
            raise RuntimeError("GitHub lieferte keinen vollständigen Merge-Commit")

        touches_mcp = any(path.startswith(MCP_PATH_PREFIX) or path == MCP_WORKFLOW_PATH for path in changed_files)
        update_result: dict[str, Any] = {"ok": True, "status": "NOT_NEEDED"}
        if self_update_after_merge and touches_mcp:
            update_result = self.self_update.schedule(expected_revision=merge_sha, reason=f"merged_pr_{number}")
        return {
            "ok": True,
            "status": "MERGED",
            "pr_number": number,
            "merge_method": method,
            "head_sha": expected,
            "merge_commit_sha": merge_sha,
            "changed_files": changed_files,
            "touches_private_mcp": touches_mcp,
            "self_update": update_result,
        }
