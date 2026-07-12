from __future__ import annotations

import os
from typing import Any, Callable


NATIVE_PROFILES = {"standard", "release"}


def install(android_runtime: Any, operator_runtime: Any, broker: Any) -> None:
    """Route native Android profiles to the allowlisted GitHub Actions workflow.

    The public MCP tool keeps its existing name. Fast checks remain local. Standard
    and release profiles first run the local fast preflight, then dispatch the
    native workflow against the already-published workspace branch. A workspace
    without a Draft PR is blocked before any local Gradle/Java command can run.
    """

    if getattr(android_runtime, "_native_validation_router_installed", False):
        return

    local_run_suite: Callable[[str, str], dict[str, Any]] = android_runtime.run_suite

    def routed_run_suite(workspace_id: str, profile: str = "fast") -> dict[str, Any]:
        selected = str(profile or "fast").strip().lower()
        if selected not in {"fast", *NATIVE_PROFILES}:
            raise ValueError("profile muss fast, standard oder release sein")

        mode = os.getenv("SOVEREIGN_ANDROID_NATIVE_BUILD_MODE", "local").strip().lower()
        if selected == "fast" or mode != "github_actions":
            return local_run_suite(workspace_id, selected)

        preflight = local_run_suite(workspace_id, "fast")
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
        if not isinstance(draft_pr, dict) or not branch:
            return {
                "ok": False,
                "status": "REMOTE_REF_REQUIRED",
                "workspace_id": workspace_id,
                "profile": selected,
                "execution_mode": "github_actions",
                "local_preflight": preflight,
                "blocker": (
                    "Native Android validation requires an already-published workspace branch. "
                    "Create the Draft PR first, then rerun this validation profile."
                ),
                "next_action": "repository_create_draft_pr_then_rerun_android_validation_suite",
            }

        workflow = os.getenv(
            "SOVEREIGN_ANDROID_VALIDATION_WORKFLOW",
            "android-release.yml",
        ).strip()
        dispatch = broker.call(
            "github_workflow_dispatch",
            {"workflow": workflow, "ref": branch, "inputs": {}},
            timeout=60,
        )
        dispatched = bool(dispatch.get("ok"))
        return {
            "ok": dispatched,
            "status": "DISPATCHED" if dispatched else str(dispatch.get("status") or "FAILED"),
            "workspace_id": workspace_id,
            "profile": selected,
            "execution_mode": "github_actions",
            "workflow": workflow,
            "ref": branch,
            "draft_pr": {
                "number": draft_pr.get("number"),
                "head_sha": draft_pr.get("head_sha"),
                "url": draft_pr.get("url"),
            },
            "local_preflight": preflight,
            "dispatch": dispatch,
            "next_action": (
                "inspect_dispatched_workflow_run_and_artifacts"
                if dispatched
                else "inspect_workflow_dispatch_blocker"
            ),
        }

    android_runtime.run_suite = routed_run_suite
    android_runtime._native_validation_router_installed = True
