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
        "github_main_ruleset_apply",
        "github_issue_close",
        "github_update_pr",
        "github_reopen_pr",
        "github_close_pr",
        "github_delete_pr_branch",
        "mcp_self_update_schedule",
        "deploy_verified_release",
        "rollback_release",
        "deploy_managed_compose_stack",
        "memory_gateway_collection_canary",
        "github_knowledge_live_canary",
        "litellm_model_aliases_activate",
        "patchmon_patch_action_apply",
    }
)


def is_mutating_action(action: str) -> bool:
    return str(action or "").strip() in MUTATING_ACTIONS
