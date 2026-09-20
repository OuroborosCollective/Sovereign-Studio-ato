"""Production bootstrap for Sovereign backend extensions.

The canonical Flask application remains owned by app.py. Production-only
background sensors and route activators are registered explicitly here so they
cannot silently replace PostgreSQL/Revolver truth ownership.
"""

import os
from pathlib import Path

from app import app, get_agent_runtime_connection
from agent_runtime.repository_execution import start_repository_reconciler
from agent_runtime.cag_self_healing_runtime import start_cag_self_healing_reconciler

# Production bootstrap intentionally registers no OmniRoute services. The live
# LLM truth path is OpenRouter + owner-managed FreeLLMAPI through Sovereign's
# resolver/revolver contracts.
#
# Repository A2A reconciliation is production runtime ownership, not request
# ownership. Gunicorn does not use --preload, so each worker starts one bounded
# scanner; persisted external_ref CAS remains the exclusive effect boundary.
_workspace_root = (
    Path(os.environ["SOVEREIGN_AGENT_WORKSPACE_ROOT"])
    if os.getenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", "").strip()
    else None
)
start_repository_reconciler(
    get_connection=get_agent_runtime_connection,
    workspace_root=_workspace_root,
)
start_cag_self_healing_reconciler(
    get_connection=get_agent_runtime_connection,
    workspace_root=_workspace_root,
)

__all__ = ["app"]
