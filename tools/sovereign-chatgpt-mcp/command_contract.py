from __future__ import annotations

MUTATING_ACTIONS = frozenset(
    {
        "host_worker_canary",
        "resolve_backend_image",
        "apply_verified_migration",
        "postgres_admin_sql",
        "git_push_main",
        "github_rerun_failed_workflows",
        "github_workflow_dispatch",
        "github_merge_pr",
        "mcp_self_update_schedule",
        "deploy_verified_release",
        "rollback_release",
        "deploy_managed_compose_stack",
    }
)


def is_mutating_action(action: str) -> bool:
    return str(action or "").strip() in MUTATING_ACTIONS
