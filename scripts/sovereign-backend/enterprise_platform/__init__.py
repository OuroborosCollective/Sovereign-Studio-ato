"""Sovereign enterprise platform package with a lazy Flask transport import."""

from .service import EnterprisePlatformService


def register_enterprise_platform_routes(*args, **kwargs):
    """Load Flask transport only when the production app registers HTTP routes."""
    from .routes import register_enterprise_platform_routes as register

    return register(*args, **kwargs)


__all__ = ["EnterprisePlatformService", "register_enterprise_platform_routes"]
