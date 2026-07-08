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
)
