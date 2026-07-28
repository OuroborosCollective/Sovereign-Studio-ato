"""Evidence-gated N+1 domain foundation."""


def register_n_plus_one_routes(*args, **kwargs):
    """Load Flask wiring only when the application registers the domain."""
    from .routes import register_n_plus_one_routes as register

    return register(*args, **kwargs)


__all__ = ["register_n_plus_one_routes"]
