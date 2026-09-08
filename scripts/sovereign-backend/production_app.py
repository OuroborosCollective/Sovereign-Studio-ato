"""Production bootstrap for Sovereign backend extensions.

The canonical Flask application remains owned by app.py. Production-only
background sensors and route activators are registered explicitly here so they
cannot silently replace PostgreSQL/Revolver truth ownership.
"""

from app import app

# Production bootstrap intentionally registers no OmniRoute services. The live
# LLM truth path is OpenRouter + owner-managed FreeLLMAPI through Sovereign's
# resolver/revolver contracts.

__all__ = ["app"]
