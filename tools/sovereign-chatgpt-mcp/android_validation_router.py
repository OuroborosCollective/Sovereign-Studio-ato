from __future__ import annotations

import os
from typing import Any, Callable


NATIVE_PROFILES = {"standard", "release"}


def install(android_runtime: Any, operator_runtime: Any, broker: Any) -> None:
    """Route native Android profiles to the allowlisted GitHub Actions workflow.

    The public MCP tool keeps its existing name. Fast checks remain local. In
    github_actions mode, standard and release run a secrets-free local preflight
    and then dispatch the native workflow against an already-published workspace
    branch. A workspace without a Draft PR is blocked before any Gradle/Java
    command can run in the lightweight MCP container.
    """

    if getattr(android_runtime, "_native_validation_router_installed", False):
        return

    local_run_suite: Callable[[str, str], dict[str, Any]] = android_runtime.run_suite

    def dispatch_preflight(workspace_id: str) -> dict[str, Any]:
        repo = operator_runtime._repo(workspace_id)
        checks: list[dict[str, Any]] = []
        for name, argv in (
            ("git_diff_check", ["git", "diff", "--check"]),
            ("typecheck", ["pnpm", "run", "type-check"]),
        ):
            result = operator_runtime._run(argv, cwd=repo, timeout=1800)
            operator_runtime._record_check(
                workspace_id,
                f"android:dispatch-preflight:{name}",
                result,
            )
            checks.append({"name": name, **result})

        static_scan = android_runtime.scan(workspace_id)
        ok = all(bool(item.get("ok")) for item in checks) and bool(static_scan.get("ok"))
        return {
            "ok": ok,
            "status": "PASS" if ok else "FAIL",
            "workspace_id": workspace_id,
            "profile": "dispatch-preflight",
            "commands": checks,
            "static_scan": static_scan,
            "signing_secrets_required_locally": False,
        }

    def routed_run_suite(workspace_id: str, profile: str = "fast") -> dict[str, Any]:
        selected = str(profile or "fast").strip().lower()
        if selected not in {"fast", *NATIVE_PROFILES}:
            raise ValueError("profile muss fast, standard oder release sein")

        if selected == "fast":
            return local_run_suite(workspace_id, selected)

        preflight = dispatch_preflight(workspace_id)
        if not bool(preflight.get("ok")):
            return {
                "ok": False,
                "status": "LOCAL_PREFLIGHT_FAILED",
                "workspace_id": workspace_id,
                "profile": selected,
                "execution_mode": "github_actions",
                "local_preflight": preflight,
                "next_action": "fix_first_local_preflight_failure_then_rerun_same_profile",
            }

        metadata = operator_runtime._read_metadata(workspace_id)
        draft_pr = metadata.get("draft_pr")
        branch = str(metadata.get("branch") or "").strip()
        direct_main_enabled = os.getenv("SOVEREIGN_MCP_ENABLE_MAIN_PUSH", "0").strip() == "1"
        if isinstance(draft_pr, dict) and branch:
            remote_ref = branch
            draft_pr_evidence: dict[str, Any] | None = {
                "number": draft_pr.get("number"),
                "head_sha": draft_pr.get("head_sha"),
                "url": draft_pr.get("url"),
            }
        elif direct_main_enabled and str(metadata.get("base_branch") or "") == "main":
            remote_ref = "main"
            draft_pr_evidence = None
        else:
            return {
                "ok": False,
                "status": "REMOTE_REF_REQUIRED",
                "workspace_id": workspace_id,
                "profile": selected,
                "execution_mode": "github_actions",
                "local_preflight": preflight,
                "blocker": (
                    "Native Android validation requires a published Draft-PR branch or explicitly enabled direct-main mode."
                ),
                "next_action": "publish_remote_ref_then_rerun_android_validation_suite",
            }

        workflow = os.getenv(
            "SOVEREIGN_ANDROID_VALIDATION_WORKFLOW",
            "android.yml",
        ).strip()
        dispatch = broker.call(
            "github_workflow_dispatch",
            {"workflow": workflow, "ref": remote_ref, "inputs": {"validation_profile": selected}},
            timeout=60,
        )
        dispatched = bool(dispatch.get("ok"))
        run_id = int(dispatch.get("run_id") or 0)
        dispatch_evidence_complete = dispatched and run_id > 0 and bool(dispatch.get("url"))
        return {
            "ok": dispatch_evidence_complete,
            "status": "DISPATCHED" if dispatch_evidence_complete else str(dispatch.get("status") or "FAILED"),
            "workspace_id": workspace_id,
            "profile": selected,
            "execution_mode": "github_actions",
            "workflow": workflow,
            "ref": remote_ref,
            "draft_pr": draft_pr_evidence,
            "local_preflight": preflight,
            "dispatch": dispatch,
            "run_id": run_id if run_id > 0 else None,
            "url": str(dispatch.get("url") or ""),
            "next_action": (
                "inspect_dispatched_workflow_run_and_artifacts"
                if dispatch_evidence_complete
                else "inspect_workflow_dispatch_blocker"
            ),
        }

    android_runtime.run_suite = routed_run_suite
    android_runtime._native_validation_router_installed = True
