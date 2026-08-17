"""Production bootstrap for Sovereign backend extensions.

The canonical Flask application remains owned by app.py. Production-only
background sensors are registered explicitly here so they cannot silently become
routing authorities or mutate the legacy app module's truth boundaries.
"""

from app import app, audit, query, require_admin
from omniroute_provider_radar import register_omniroute_provider_radar


omniroute_provider_radar_service = register_omniroute_provider_radar(
    app,
    require_admin=require_admin,
    query=query,
    audit=audit,
)

__all__ = ["app", "omniroute_provider_radar_service"]
