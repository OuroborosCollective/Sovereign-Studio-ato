from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote

import requests

from self_update import SelfUpdateRuntime

COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
WORKFLOW_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.ya?ml$")
INPUT_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ALLOWED_MERGE_METHODS = {"merge", "squash", "rebase"}
ALLOWED_CLOSE_REASONS = {"redundant", "superseded"}
PROTECTED_BRANCH_NAMES = frozenset({"main", "master"})
SUCCESSFUL_CHECK_CONCLUSIONS = {"success", "neutral", "skipped"}
RERUN_FAILED_CONCLUSIONS = {"failure"}
RERUN_ALL_CONCLUSIONS = {"cancelled", "timed_out", "action_required", "stale"}
MCP_PATH_PREFIX = "tools/sovereign-chatgpt-mcp/"
MCP_WORKFLOW_PATH = ".github/workflows/sovereign-chatgpt-mcp.yml"
SENSITIVE_INPUT_PARTS = {"secret", "token", "password", "passwd", "private", "keystore", "credential"}
OWNER_SCOPED_IGNORABLE_PENDING_CHECKS = frozenset({
    "Android Build Verification",
    "Android standard validation",
})
ANDROID_SURFACE_PREFIXES = (
    "android/",
    ".github/workflows/android",
    "gradle/",
)
ANDROID_SURFACE_FILES = frozenset({
    "capacitor.config.ts",
    "capacitor.config.json",
    "build.gradle",
    "settings.gradle",
    "gradle.properties",
})
MAIN_RULESET_NAME = "Sovereign Main Revision Green Gate"
MAIN_RULESET_REQUIRED_CHECKS = ("Release Gate", "Agent Runtime Tests")


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
        self.private_owner_mode = _enabled("SOVEREIGN_MCP_PRIVATE_OWNER_MODE")
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

    @staticmethod
    def _issue_number(value: int) -> int:
        number = int(value)
        if number < 1:
            raise ValueError("issue_number muss positiv sein")
        return number

    @staticmethod
    def _issue_actor(payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        return {
            "login": str(payload.get("login") or ""),
            "type": str(payload.get("type") or ""),
            "url": str(payload.get("html_url") or ""),
        }

    @classmethod
    def _normalize_issue(cls, payload: dict[str, Any], *, include_body: bool) -> dict[str, Any]:
        labels: list[dict[str, Any]] = []
        for item in payload.get("labels", []) if isinstance(payload.get("labels"), list) else []:
            if isinstance(item, str):
                labels.append({"name": item, "color": "", "description": None})
            elif isinstance(item, dict):
                labels.append(
                    {
                        "name": str(item.get("name") or ""),
                        "color": str(item.get("color") or ""),
                        "description": (
                            str(item.get("description")) if item.get("description") is not None else None
                        ),
                    }
                )
        assignees = [
            actor
            for actor in (
                cls._issue_actor(item)
                for item in payload.get("assignees", []) if isinstance(payload.get("assignees"), list)
            )
            if actor is not None
        ]
        normalized = {
            "number": int(payload.get("number") or 0),
            "title": str(payload.get("title") or ""),
            "state": str(payload.get("state") or ""),
            "stateReason": (
                str(payload.get("state_reason")) if payload.get("state_reason") is not None else None
            ),
            "labels": labels,
            "author": cls._issue_actor(payload.get("user")),
            "assignees": assignees,
            "comments": int(payload.get("comments") or 0),
            "locked": bool(payload.get("locked")),
            "createdAt": str(payload.get("created_at") or ""),
            "updatedAt": str(payload.get("updated_at") or ""),
            "closedAt": str(payload.get("closed_at")) if payload.get("closed_at") is not None else None,
            "url": str(payload.get("html_url") or ""),
        }
        if include_body:
            normalized["body"] = str(payload.get("body") or "")
        return normalized

    def _issue(self, issue_number: int) -> dict[str, Any]:
        number = self._issue_number(issue_number)
        payload = self._request("GET", f"/repos/{self.repository}/issues/{number}")
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub Issue-Antwort ist ungültig")
        if isinstance(payload.get("pull_request"), dict):
            raise ValueError("Die angeforderte Nummer gehört zu einem Pull Request, nicht zu einer Issue")
        return payload

    def list_issues(self, *, limit: int = 20) -> dict[str, Any]:
        selected_limit = max(1, min(int(limit), 50))
        issues: list[dict[str, Any]] = []
        for page in range(1, 11):
            payload = self._request(
                "GET",
                f"/repos/{self.repository}/issues",
                params={
                    "state": "open",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": 100,
                    "page": page,
                },
            )
            if not isinstance(payload, list):
                raise RuntimeError("GitHub Issue-Liste ist ungültig")
            for item in payload:
                if not isinstance(item, dict) or isinstance(item.get("pull_request"), dict):
                    continue
                issues.append(self._normalize_issue(item, include_body=False))
                if len(issues) >= selected_limit:
                    break
            if len(issues) >= selected_limit or len(payload) < 100:
                break
        return {
            "ok": True,
            "status": "ISSUES_VERIFIED",
            "repository": self.repository,
            "queryState": "open",
            "count": len(issues),
            "issues": issues,
            "readbackVerified": True,
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def read_issue(self, *, issue_number: int) -> dict[str, Any]:
        payload = self._issue(issue_number)
        return {
            "ok": True,
            "status": "ISSUE_VERIFIED",
            "repository": self.repository,
            "issue": self._normalize_issue(payload, include_body=True),
            "readbackVerified": True,
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def close_issue(
        self,
        *,
        issue_number: int,
        expected_updated_at: str,
        owner_approved: bool = False,
    ) -> dict[str, Any]:
        blocked = self._require_owner_issue_admin(owner_approved)
        if blocked:
            return blocked
        number = self._issue_number(issue_number)
        expected = str(expected_updated_at or "").strip()
        if not expected or len(expected) > 64:
            raise ValueError("expected_updated_at muss ein bestätigter GitHub-Zeitstempel sein")
        current = self._issue(number)
        current_updated_at = str(current.get("updated_at") or "")
        if current_updated_at != expected:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "ISSUE_STALE_READBACK",
                "blocker": "Issue wurde seit dem bestätigten Readback verändert",
                "issueNumber": number,
                "expectedUpdatedAt": expected,
                "actualUpdatedAt": current_updated_at,
                "readback_verified": True,
            }
        current_state = str(current.get("state") or "")
        current_reason = str(current.get("state_reason") or "")
        if current_state == "closed":
            if current_reason != "completed":
                return {
                    "ok": False,
                    "status": "BLOCKED",
                    "failure_family": "ISSUE_ALREADY_CLOSED_DIFFERENT_REASON",
                    "blocker": "Issue ist bereits mit einem anderen Abschlussgrund geschlossen",
                    "issueNumber": number,
                    "readback_verified": True,
                }
            normalized = self._normalize_issue(current, include_body=False)
            return {
                "ok": True,
                "status": "ISSUE_ALREADY_CLOSED",
                "repository": self.repository,
                "issueNumber": number,
                "title": normalized["title"],
                "state": "closed",
                "stateReason": "completed",
                "expectedUpdatedAt": expected,
                "actualUpdatedAt": normalized["updatedAt"],
                "url": normalized["url"],
                "owner_approved": True,
                "mutationPerformed": False,
                "readback_verified": True,
                "secretValuesReturned": False,
            }
        if current_state != "open":
            return {"ok": False, "status": "BLOCKED", "blocker": "Issue ist nicht offen"}
        self._request(
            "PATCH",
            f"/repos/{self.repository}/issues/{number}",
            json_body={"state": "closed", "state_reason": "completed"},
            expected=(200,),
            timeout=60,
        )
        readback = self._issue(number)
        if str(readback.get("state") or "") != "closed" or str(readback.get("state_reason") or "") != "completed":
            raise RuntimeError("GitHub Issue-Readback bestätigt den Abschluss nicht")
        normalized = self._normalize_issue(readback, include_body=False)
        return {
            "ok": True,
            "status": "ISSUE_CLOSED",
            "repository": self.repository,
            "issueNumber": number,
            "title": normalized["title"],
            "state": "closed",
            "stateReason": "completed",
            "expectedUpdatedAt": expected,
            "actualUpdatedAt": normalized["updatedAt"],
            "url": normalized["url"],
            "owner_approved": True,
            "mutationPerformed": True,
            "readback_verified": True,
            "secretValuesReturned": False,
        }

    def _pull(self, pr_number: int) -> dict[str, Any]:
        payload = self._request("GET", f"/repos/{self.repository}/pulls/{self._pr_number(pr_number)}")
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub PR-Antwort ist ungültig")
        return payload

    def _require_owner_pr_admin(self, owner_approved: bool) -> dict[str, Any] | None:
        if not _enabled("SOVEREIGN_MCP_ENABLE_PR_MERGE"):
            return {"ok": False, "status": "BLOCKED", "blocker": "PR-Administration ist nicht aktiviert"}
        if not self.private_owner_mode or not owner_approved:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "PR-Administration erfordert privaten Owner-Modus und ausdrückliche Owner-Freigabe",
            }
        return None

    def _require_owner_issue_admin(self, owner_approved: bool) -> dict[str, Any] | None:
        if not _enabled("SOVEREIGN_MCP_ENABLE_PR_MERGE"):
            return {"ok": False, "status": "BLOCKED", "blocker": "Issue-Administration ist nicht aktiviert"}
        if not self.private_owner_mode or not owner_approved:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Issue-Administration erfordert privaten Owner-Modus und ausdrückliche Owner-Freigabe",
            }
        return None

    def _default_branch(self) -> str:
        payload = self._request("GET", f"/repos/{self.repository}")
        branch = str(payload.get("default_branch") or "").strip() if isinstance(payload, dict) else ""
        if not branch or not REF_RE.fullmatch(branch) or ".." in branch:
            raise RuntimeError("GitHub lieferte keinen sicheren Default-Branch")
        return branch

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
        if not WORKFLOW_RE.fullmatch(selected):
            raise ValueError("Workflow-Dateiname ist ungültig")
        if selected not in self.allowed_workflows and not self.private_owner_mode:
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

    @staticmethod
    def _touches_android_surface(changed_files: list[str]) -> bool:
        for raw_path in changed_files:
            path = str(raw_path or "").strip().lower()
            if not path:
                continue
            if path in ANDROID_SURFACE_FILES:
                return True
            if any(path.startswith(prefix) for prefix in ANDROID_SURFACE_PREFIXES):
                return True
        return False

    def _mark_ready_for_review(self, *, pull: dict[str, Any], expected_head_sha: str) -> dict[str, Any]:
        node_id = str(pull.get("node_id") or "").strip()
        actual_head = str((pull.get("head") or {}).get("sha") or "").strip().lower()
        if not node_id:
            raise RuntimeError("GitHub lieferte keine Pull-Request-Node-ID für Ready-for-Review")
        if actual_head != expected_head_sha:
            raise RuntimeError("PR-Head änderte sich vor Ready-for-Review")
        payload = self._request(
            "POST",
            "/graphql",
            json_body={
                "query": (
                    "mutation MarkReady($pullRequestId: ID!) { "
                    "markPullRequestReadyForReview(input: {pullRequestId: $pullRequestId}) { "
                    "pullRequest { id isDraft } } }"
                ),
                "variables": {"pullRequestId": node_id},
            },
            expected=(200,),
        )
        if not isinstance(payload, dict) or payload.get("errors"):
            raise RuntimeError("GitHub Ready-for-Review-Mutation ist fehlgeschlagen")
        mutation = (payload.get("data") or {}).get("markPullRequestReadyForReview") or {}
        updated = mutation.get("pullRequest") if isinstance(mutation, dict) else None
        if not isinstance(updated, dict) or updated.get("isDraft") is not False:
            raise RuntimeError("GitHub bestätigte den Draft-Übergang nicht")
        return {"ok": True, "status": "READY_FOR_REVIEW", "node_id": node_id}

    def merge_pr(
        self,
        *,
        pr_number: int,
        expected_head_sha: str,
        merge_method: str = "squash",
        self_update_after_merge: bool = True,
        owner_approved: bool = False,
        mark_ready_if_draft: bool = False,
        allow_unrelated_android_pending: bool = False,
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
        ready_transition: dict[str, Any] = {"ok": True, "status": "NOT_NEEDED"}
        if status["draft"]:
            if not owner_approved or not mark_ready_if_draft:
                return {"ok": False, "status": "BLOCKED", "blocker": "Draft-PR muss zuerst bereit sein", "pr": status}
            pull = self._pull(number)
            ready_transition = self._mark_ready_for_review(pull=pull, expected_head_sha=expected)
            status = self.pr_status(pr_number=number)
            if status["draft"]:
                return {"ok": False, "status": "BLOCKED", "blocker": "GitHub führt den PR weiterhin als Draft", "pr": status}
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

        changed_files = self._changed_files(number)
        checks = status["checks"]
        ignored_pending_checks: list[str] = []
        if not checks["ok"]:
            failed = list(checks.get("failed") or [])
            pending = list(checks.get("pending") or [])
            if failed:
                return {"ok": False, "status": "BLOCKED", "blocker": "PR-Checks enthalten Fehler", "pr": status}
            scoped_override = owner_approved and allow_unrelated_android_pending
            if not scoped_override:
                return {"ok": False, "status": "BLOCKED", "blocker": "PR-Checks sind nicht vollständig grün", "pr": status}
            if self._touches_android_surface(changed_files):
                return {
                    "ok": False,
                    "status": "BLOCKED",
                    "blocker": "Android-Pending-Gates dürfen bei Android-relevanten Änderungen nicht ignoriert werden",
                    "pr": status,
                }
            remaining_pending = [
                name for name in pending if name not in OWNER_SCOPED_IGNORABLE_PENDING_CHECKS
            ]
            if remaining_pending:
                return {
                    "ok": False,
                    "status": "BLOCKED",
                    "blocker": "Nicht freigegebene Pending-Gates verhindern den Merge",
                    "remaining_pending": remaining_pending,
                    "pr": status,
                }
            ignored_pending_checks = [
                name for name in pending if name in OWNER_SCOPED_IGNORABLE_PENDING_CHECKS
            ]
            if not ignored_pending_checks:
                return {"ok": False, "status": "BLOCKED", "blocker": "Keine fachfremden Android-Pending-Gates belegt", "pr": status}

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
            "owner_approved": bool(owner_approved),
            "ready_transition": ready_transition,
            "ignored_pending_checks": ignored_pending_checks,
            "self_update": update_result,
        }

    def apply_main_ruleset(self, *, owner_approved: bool = False) -> dict[str, Any]:
        """Create or reconcile the active main ruleset and verify exact GitHub readback."""
        blocked = self._require_owner_pr_admin(owner_approved)
        if blocked:
            return blocked
        default_branch = self._default_branch()
        if default_branch != "main":
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Repository-Default-Branch ist nicht main",
                "default_branch": default_branch,
            }
        payload = {
            "name": MAIN_RULESET_NAME,
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
            "rules": [
                {"type": "deletion"},
                {"type": "non_fast_forward"},
                {
                    "type": "pull_request",
                    "parameters": {
                        "allowed_merge_methods": ["squash"],
                        "dismiss_stale_reviews_on_push": True,
                        "require_code_owner_review": False,
                        "require_last_push_approval": False,
                        "required_approving_review_count": 0,
                        "required_review_thread_resolution": True,
                    },
                },
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "do_not_enforce_on_create": False,
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [
                            {"context": context} for context in MAIN_RULESET_REQUIRED_CHECKS
                        ],
                    },
                },
            ],
        }
        listed = self._request(
            "GET",
            f"/repos/{self.repository}/rulesets",
            params={"targets": "branch", "includes_parents": "false", "per_page": 100},
        )
        matches = [
            item for item in listed
            if isinstance(item, dict) and str(item.get("name") or "") == MAIN_RULESET_NAME
        ] if isinstance(listed, list) else []
        if len(matches) > 1:
            raise RuntimeError("Mehrere gleichnamige Main-Rulesets gefunden")
        if matches:
            ruleset_id = int(matches[0].get("id") or 0)
            if ruleset_id < 1:
                raise RuntimeError("GitHub lieferte keine gültige Ruleset-ID")
            self._request(
                "PUT",
                f"/repos/{self.repository}/rulesets/{ruleset_id}",
                json_body=payload,
                expected=(200,),
                timeout=60,
            )
            mutation_status = "UPDATED"
        else:
            created = self._request(
                "POST",
                f"/repos/{self.repository}/rulesets",
                json_body=payload,
                expected=(201,),
                timeout=60,
            )
            ruleset_id = int(created.get("id") or 0) if isinstance(created, dict) else 0
            if ruleset_id < 1:
                raise RuntimeError("GitHub bestätigte keine Ruleset-ID")
            mutation_status = "CREATED"
        readback = self._request("GET", f"/repos/{self.repository}/rulesets/{ruleset_id}")
        if not isinstance(readback, dict):
            raise RuntimeError("GitHub Ruleset-Readback ist ungültig")
        if (
            str(readback.get("name") or "") != MAIN_RULESET_NAME
            or str(readback.get("target") or "") != "branch"
            or str(readback.get("enforcement") or "") != "active"
            or readback.get("bypass_actors") not in ([], None)
            or readback.get("conditions") != payload["conditions"]
        ):
            raise RuntimeError("GitHub Ruleset-Readback weicht vom kanonischen Vertrag ab")
        rules = readback.get("rules") if isinstance(readback.get("rules"), list) else []
        required_rule = next((item for item in rules if isinstance(item, dict) and item.get("type") == "required_status_checks"), None)
        contexts = {
            str(item.get("context") or "")
            for item in ((required_rule or {}).get("parameters") or {}).get("required_status_checks", [])
            if isinstance(item, dict)
        }
        if contexts != set(MAIN_RULESET_REQUIRED_CHECKS):
            raise RuntimeError("GitHub bestätigte die erforderlichen Statuschecks nicht vollständig")
        return {
            "ok": True,
            "status": f"RULESET_{mutation_status}",
            "ruleset_id": ruleset_id,
            "name": MAIN_RULESET_NAME,
            "target_ref": "refs/heads/main",
            "enforcement": "active",
            "required_status_checks": list(MAIN_RULESET_REQUIRED_CHECKS),
            "bypass_actors": [],
            "owner_approved": True,
            "readback_verified": True,
            "url": str(((readback.get("_links") or {}).get("html") or {}).get("href") or ""),
        }

    def update_pr(
        self,
        *,
        pr_number: int,
        expected_head_sha: str,
        title: str = "",
        body: str = "",
        owner_approved: bool = False,
    ) -> dict[str, Any]:
        """Update title/body for one exact open PR and verify GitHub readback."""
        blocked = self._require_owner_pr_admin(owner_approved)
        if blocked:
            return blocked
        number = self._pr_number(pr_number)
        expected = str(expected_head_sha or "").strip().lower()
        if not COMMIT_SHA_RE.fullmatch(expected):
            raise ValueError("expected_head_sha muss ein vollständiger Commit-SHA sein")
        clean_title = str(title or "").strip()
        clean_body = str(body or "").strip()
        if not clean_title and not clean_body:
            raise ValueError("title oder body muss gesetzt sein")
        if len(clean_title) > 256 or len(clean_body) > 60_000:
            raise ValueError("PR-Titel oder PR-Beschreibung überschreitet das Limit")

        pull = self._pull(number)
        actual_head = str((pull.get("head") or {}).get("sha") or "").strip().lower()
        if actual_head != expected:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "PR-Head stimmt nicht mit der Bestätigung überein",
                "actual_head_sha": actual_head,
                "expected_head_sha": expected,
            }
        if str(pull.get("state") or "") != "open":
            return {"ok": False, "status": "BLOCKED", "blocker": "Nur ein offener PR darf bearbeitet werden"}

        mutation: dict[str, Any] = {}
        if clean_title:
            mutation["title"] = clean_title
        if clean_body:
            mutation["body"] = clean_body
        payload = self._request(
            "PATCH",
            f"/repos/{self.repository}/pulls/{number}",
            json_body=mutation,
            expected=(200,),
            timeout=60,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("GitHub bestätigte die PR-Aktualisierung nicht")
        readback = self._pull(number)
        readback_head = str((readback.get("head") or {}).get("sha") or "").strip().lower()
        if readback_head != expected or str(readback.get("state") or "") != "open":
            raise RuntimeError("GitHub PR-Readback stimmt nicht mit dem Update-Vertrag überein")
        if clean_title and str(readback.get("title") or "") != clean_title:
            raise RuntimeError("GitHub bestätigte den aktualisierten PR-Titel nicht")
        if clean_body and str(readback.get("body") or "") != clean_body:
            raise RuntimeError("GitHub bestätigte die aktualisierte PR-Beschreibung nicht")
        return {
            "ok": True,
            "status": "UPDATED",
            "pr_number": number,
            "head_sha": expected,
            "title_updated": bool(clean_title),
            "body_updated": bool(clean_body),
            "owner_approved": True,
            "url": str(readback.get("html_url") or payload.get("html_url") or ""),
        }

    def reopen_pr(
        self,
        *,
        pr_number: int,
        expected_head_sha: str,
        owner_approved: bool = False,
    ) -> dict[str, Any]:
        """Reopen one exact closed, unmerged PR and verify GitHub readback."""
        blocked = self._require_owner_pr_admin(owner_approved)
        if blocked:
            return blocked
        number = self._pr_number(pr_number)
        expected = str(expected_head_sha or "").strip().lower()
        if not COMMIT_SHA_RE.fullmatch(expected):
            raise ValueError("expected_head_sha muss ein vollständiger Commit-SHA sein")
        pull = self._pull(number)
        actual_head = str((pull.get("head") or {}).get("sha") or "").strip().lower()
        if actual_head != expected:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "PR-Head stimmt nicht mit der Bestätigung überein",
                "actual_head_sha": actual_head,
                "expected_head_sha": expected,
            }
        state = str(pull.get("state") or "")
        if state == "open":
            return {"ok": True, "status": "ALREADY_OPEN", "pr_number": number, "head_sha": expected}
        if state != "closed" or pull.get("merged_at"):
            return {"ok": False, "status": "BLOCKED", "blocker": "Nur ein geschlossener, ungemergter PR darf wieder geöffnet werden"}
        payload = self._request(
            "PATCH",
            f"/repos/{self.repository}/pulls/{number}",
            json_body={"state": "open"},
            expected=(200,),
            timeout=60,
        )
        if not isinstance(payload, dict) or str(payload.get("state") or "") != "open":
            raise RuntimeError("GitHub bestätigte den wieder geöffneten PR-Zustand nicht")
        readback = self._pull(number)
        if (
            str(readback.get("state") or "") != "open"
            or str((readback.get("head") or {}).get("sha") or "").strip().lower() != expected
        ):
            raise RuntimeError("GitHub PR-Readback stimmt nicht mit dem Reopen-Vertrag überein")
        return {
            "ok": True,
            "status": "REOPENED",
            "pr_number": number,
            "head_sha": expected,
            "owner_approved": True,
            "url": str(readback.get("html_url") or payload.get("html_url") or ""),
        }

    def delete_pr_branch(
        self,
        *,
        pr_number: int,
        expected_head_sha: str,
        owner_approved: bool = False,
    ) -> dict[str, Any]:
        """Delete only a completed PR head branch; primary and base branches are immutable."""
        blocked = self._require_owner_pr_admin(owner_approved)
        if blocked:
            return blocked
        number = self._pr_number(pr_number)
        expected = str(expected_head_sha or "").strip().lower()
        if not COMMIT_SHA_RE.fullmatch(expected):
            raise ValueError("expected_head_sha muss ein vollständiger Commit-SHA sein")
        pull = self._pull(number)
        head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
        base = pull.get("base") if isinstance(pull.get("base"), dict) else {}
        actual_head = str(head.get("sha") or "").strip().lower()
        branch = str(head.get("ref") or "").strip()
        base_branch = str(base.get("ref") or "").strip()
        head_repository = str((head.get("repo") or {}).get("full_name") or "").strip()
        if actual_head != expected:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "PR-Head stimmt nicht mit der Bestätigung überein",
                "actual_head_sha": actual_head,
                "expected_head_sha": expected,
            }
        if str(pull.get("state") or "") != "closed" and not pull.get("merged_at"):
            return {"ok": False, "status": "BLOCKED", "blocker": "Der PR muss vor Branch-Löschung geschlossen oder gemergt sein"}
        if not branch or not REF_RE.fullmatch(branch) or ".." in branch:
            raise RuntimeError("GitHub lieferte keinen sicheren PR-Head-Branch")
        if head_repository != self.repository:
            return {"ok": False, "status": "BLOCKED", "blocker": "Branches aus Fork-Repositories werden nicht gelöscht"}

        default_branch = self._default_branch()
        protected = {name.casefold() for name in PROTECTED_BRANCH_NAMES}
        protected.update({default_branch.casefold(), base_branch.casefold()})
        if branch.casefold() in protected:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "PROTECTED_BRANCH_DELETE_FORBIDDEN",
                "blocker": "main, master, Default-Branch und PR-Basisbranch dürfen niemals gelöscht werden",
                "branch": branch,
                "protected_branches": sorted(protected),
            }

        encoded = quote(branch, safe="")
        ref_path = f"/repos/{self.repository}/git/ref/heads/{encoded}"
        ref = self._request("GET", ref_path)
        ref_sha = str(((ref.get("object") or {}) if isinstance(ref, dict) else {}).get("sha") or "").strip().lower()
        if ref_sha != expected:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Branch-Ref stimmt nicht mit dem bestätigten PR-Head überein",
                "actual_head_sha": ref_sha,
                "expected_head_sha": expected,
            }
        self._request(
            "DELETE",
            f"/repos/{self.repository}/git/refs/heads/{encoded}",
            expected=(204,),
            timeout=60,
        )
        self._request("GET", ref_path, expected=(404,), timeout=30)
        return {
            "ok": True,
            "status": "BRANCH_DELETED",
            "pr_number": number,
            "branch": branch,
            "head_sha": expected,
            "default_branch": default_branch,
            "base_branch": base_branch,
            "protected_primary_branches": sorted(PROTECTED_BRANCH_NAMES),
            "readback_deleted": True,
            "owner_approved": True,
        }

    def close_pr(
        self,
        *,
        pr_number: int,
        expected_head_sha: str,
        closure_reason: str = "redundant",
        owner_approved: bool = False,
    ) -> dict[str, Any]:
        """Close one exact open PR without merging it and verify GitHub readback."""
        if not _enabled("SOVEREIGN_MCP_ENABLE_PR_MERGE"):
            return {"ok": False, "status": "BLOCKED", "blocker": "PR-Administration ist nicht aktiviert"}
        if not self.private_owner_mode or not owner_approved:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "PR-Schließen erfordert privaten Owner-Modus und ausdrückliche Owner-Freigabe",
            }

        number = self._pr_number(pr_number)
        expected = str(expected_head_sha or "").strip().lower()
        if not COMMIT_SHA_RE.fullmatch(expected):
            raise ValueError("expected_head_sha muss ein vollständiger Commit-SHA sein")
        reason = str(closure_reason or "redundant").strip().lower()
        if reason not in ALLOWED_CLOSE_REASONS:
            raise ValueError("closure_reason muss redundant oder superseded sein")

        status = self.pr_status(pr_number=number)
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
        if status["state"] == "closed":
            return {
                "ok": True,
                "status": "ALREADY_CLOSED",
                "pr_number": number,
                "head_sha": expected,
                "closure_reason": reason,
                "owner_approved": True,
            }
        if status["state"] != "open":
            return {"ok": False, "status": "BLOCKED", "blocker": "PR ist nicht offen", "pr": status}

        payload = self._request(
            "PATCH",
            f"/repos/{self.repository}/pulls/{number}",
            json_body={"state": "closed"},
            expected=(200,),
            timeout=60,
        )
        if not isinstance(payload, dict) or str(payload.get("state") or "") != "closed":
            raise RuntimeError("GitHub bestätigte den geschlossenen PR-Zustand nicht")

        readback = self._pull(number)
        readback_head = str((readback.get("head") or {}).get("sha") or "").strip().lower()
        readback_base = str((readback.get("base") or {}).get("ref") or "").strip()
        if (
            str(readback.get("state") or "") != "closed"
            or readback_head != expected
            or readback_base != "main"
        ):
            raise RuntimeError("GitHub PR-Readback stimmt nicht mit dem bestätigten Close-Vertrag überein")
        return {
            "ok": True,
            "status": "CLOSED",
            "pr_number": number,
            "head_sha": expected,
            "closure_reason": reason,
            "owner_approved": True,
            "url": str(readback.get("html_url") or payload.get("html_url") or ""),
            "merge_performed": False,
        }
