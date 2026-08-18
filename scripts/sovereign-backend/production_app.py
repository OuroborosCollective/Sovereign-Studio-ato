"""Production bootstrap for Sovereign backend extensions.

The canonical Flask application remains owned by app.py. Production-only
background sensors and route activators are registered explicitly here so they
cannot silently replace PostgreSQL/Revolver truth ownership.
"""

from app import app, audit, get_agent_runtime_connection, query, require_admin
from omniroute_execution_runtime import register_omniroute_execution_runtime
from omniroute_provider_radar import register_omniroute_provider_radar


def _background_audit(action: str, target_id: str | None, changes: dict) -> None:
    """Give background evidence writers a real Flask system-audit context."""
    with app.app_context():
        audit(action, target_id, changes)


omniroute_provider_radar_service = register_omniroute_provider_radar(
    app,
    require_admin=require_admin,
    query=query,
    audit=_background_audit,
)

omniroute_execution_service = register_omniroute_execution_runtime(
    app,
    require_admin=require_admin,
    query=query,
    get_connection=get_agent_runtime_connection,
    audit=_background_audit,
)

__all__ = [
    "app",
    "omniroute_provider_radar_service",
    "omniroute_execution_service",
]
