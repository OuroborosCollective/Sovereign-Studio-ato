"""Sovereign Agent Runtime package.

This package owns the neutral backend contract for Sovereign agent jobs.
OpenHands may be one executor adapter, but the runtime truth is produced here.
"""

from .contracts import (  # noqa: F401
    AGENT_TERMINAL_STATUSES,
    SovereignAgentEvent,
    SovereignAgentJobRequest,
    SovereignAgentJobResult,
    SovereignAgentValidationResult,
    build_blocked_agent_result,
    build_sovereign_agent_job_request,
    can_transition_agent_status,
    normalize_agent_job_result,
    sanitize_agent_text,
    validate_agent_job_request,
    validate_agent_job_result,
)
from .git_workspace import (  # noqa: F401
    GitWorkspaceResult,
    build_git_clone_command,
    clone_repo_into_workspace,
    git_diff_summary,
    git_status_changed_files,
)
from .workspace import (  # noqa: F401
    WorkspaceProvisionResult,
    cleanup_agent_workspace,
    create_agent_workspace,
)
from .workspace_policy import (  # noqa: F401
    WorkspacePolicyError,
    ensure_path_inside_workspace,
    repo_dir_for_workspace,
    safe_workspace_path,
    validate_repo_url_for_workspace,
    validate_workspace_branch,
    validate_workspace_relative_path,
    workspace_root,
)
