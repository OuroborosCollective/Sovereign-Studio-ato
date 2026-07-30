"""Sovereign Agent Runtime package.

This package owns the neutral backend contract for Sovereign agent jobs.
The internal sovereign-local-runner produces runtime truth here.
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
from .provider_neutral_runtime import (  # noqa: F401
    ConversationProjection,
    DeterministicTrigger,
    HookDecision,
    HookPipeline,
    HookReceipt,
    PolicyEvaluation,
    PolicyRule,
    ProviderNeutralRuntimeError,
    ProviderNeutralRuntimeKernel,
    ProviderNeutralToolExecution,
    RuntimeContext,
    RuntimeInputEnvelope,
    RuntimeInputPart,
    RuntimePreparation,
    RuntimeStreamEvent,
    ToolAuthorization,
    ToolDescriptor,
    append_stream_event,
    build_stream_event,
    build_text_delta_stream,
    canonical_json,
    canonical_sha256,
    descriptor_from_registry,
    evaluate_tool_policy,
    project_conversation,
    tool_registry_snapshot,
    validate_stream_chain,
)
from .draft_pr_create_gate import (  # noqa: F401
    DraftPrCreateRequest,
    DraftPrCreateResult,
    GitHubApiDraftPrCreator,
    create_draft_pr_for_job,
    draft_pr_create_request_from_job,
    draft_pr_create_signal,
    validate_draft_pr_create_request,
)
from .draft_pr_gate import (  # noqa: F401
    DraftPrPreparationInput,
    DraftPrPreparationResult,
    draft_pr_input_from_job,
    draft_pr_preparation_signal,
    prepare_draft_pr,
)
from .evidence_gate import (  # noqa: F401
    EvidenceGateInput,
    EvidenceGateResult,
    evaluate_agent_evidence,
    evaluate_tool_result_evidence,
    evidence_gate_signal,
    evidence_input_from_tool_result,
)
from .proof_verdict import (  # noqa: F401
    AGENT_REPOSITORY_MUTATION_REQUIREMENTS_V1,
    DEFAULT_PROOF_REQUIREMENT_SETS,
    ProofContractError,
    ProofEnvelope,
    ProofObservation,
    ProofRequirement,
    ProofRequirementSet,
    ProofVerdict,
    build_proof_envelope,
    canonical_proof_sha256,
    canonical_proof_value,
    evaluate_proof,
    observation_from_agent_run_receipt,
)
from .mutation_evidence_layer import (  # noqa: F401
    CANONICAL_MIRROR_OWNERSHIP_REQUIREMENTS_V1,
    FLEET_DEPLOYMENT_REQUIREMENTS_V1,
    GITHUB_MERGE_RELEASE_REQUIREMENTS_V1,
    MCP_REGISTRY_SELF_UPDATE_REQUIREMENTS_V1,
    MUTATION_FAMILY_IDS,
    MUTATION_REQUIREMENT_REGISTRY_SHA256,
    MUTATION_REQUIREMENT_SETS_V1,
    POSTGRES_PGVECTOR_MUTATION_REQUIREMENTS_V1,
    PROVIDER_ROUTING_MUTATION_REQUIREMENTS_V1,
    SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1,
    SOVEREIGN_RESCUE_REPAIR_REQUIREMENTS_V1,
    build_mutation_proof_envelope,
    evaluate_mutation_evidence,
    mutation_requirement_registry_snapshot,
    mutation_requirement_set,
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
    mark_draft_pr_created,
    mark_draft_pr_prepared,
    read_agent_job,
    result_from_stored_job,
    update_agent_job_state,
)
from .pattern_gateway import (  # noqa: F401
    PatternLearningInput,
    PatternLearningResult,
    evaluate_pattern_learning,
    pattern_input_from_job,
    pattern_learning_signal,
    persist_pattern_learning_candidate,
)
from .tool_events import (  # noqa: F401
    append_tool_result_to_job,
    evidence_gate_to_agent_event,
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
from .event_mapping_compat import install_event_mapping_compat as _install_event_mapping_compat

_install_event_mapping_compat()
del _install_event_mapping_compat
