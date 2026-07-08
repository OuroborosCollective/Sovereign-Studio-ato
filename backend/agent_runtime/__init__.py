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
from .job_lifecycle import (  # noqa: F401
    SovereignAgentLifecycleResult,
    create_sovereign_agent_job,
    generate_agent_job_id,
)
from .job_store import (  # noqa: F401
    StoredSovereignAgentJob,
    append_agent_event,
    create_agent_job_record,
    list_agent_jobs,
    read_agent_job,
    result_from_stored_job,
    update_agent_job_state,
)
from .tool_events import (  # noqa: F401
    append_tool_result_to_job,
    predictive_tool_signal,
    tool_result_to_agent_events,
)
from .tool_policy import (  # noqa: F401
    ToolPolicyResult,
    normalize_tool_path,
    resolve_repo_tool_path,
    validate_repo_ready,
    validate_shell_command,
    validate_tool_path,
    validate_workspace_ready,
)
from .tool_runner import (  # noqa: F401
    run_agent_job_tool,
)
from .tools import (  # noqa: F401
    ToolEvent,
    ToolResult,
    blocked_tool_result,
    collect_git_diff_summary,
    collect_git_status,
    done_tool_result,
    failed_tool_result,
    read_workspace_file,
    run_workspace_shell_command,
    run_workspace_test_command,
    write_workspace_file,
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
