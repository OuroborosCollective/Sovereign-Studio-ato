from __future__ import annotations

from managed_compose import ManagedStack, STACKS


_EXTERNAL_STACKS = {
    "sovereign-bytebase": ManagedStack(
        stack_id="sovereign-bytebase",
        project_name="sovereign-bytebase",
        anchor_container="sovereign-bytebase",
        expected_containers=("sovereign-bytebase",),
        allowed_services=("bytebase",),
        deploy_root="/opt/sovereign-bytebase",
        template_name="sovereign-bytebase",
        allowed_networks=("supabase_default",),
        allowed_bind_roots=("/opt/sovereign-bytebase",),
        allowed_published_ports=("127.0.0.1:32831:8080",),
    ),
    "sovereign-metamcp": ManagedStack(
        stack_id="sovereign-metamcp",
        project_name="sovereign-metamcp",
        anchor_container="sovereign-metamcp",
        expected_containers=("sovereign-metamcp", "sovereign-metamcp-postgres"),
        allowed_services=("metamcp", "postgres"),
        deploy_root="/opt/sovereign-metamcp",
        template_name="sovereign-metamcp",
        allowed_networks=("metamcp-internal", "supabase_default"),
        allowed_bind_roots=("/opt/sovereign-metamcp",),
        allowed_published_ports=("127.0.0.1:32832:12008",),
    ),
}


def install() -> tuple[str, ...]:
    """Register reviewed external control-plane stacks without replacing core definitions."""
    for stack_id, candidate in _EXTERNAL_STACKS.items():
        current = STACKS.get(stack_id)
        if current is not None and current != candidate:
            raise RuntimeError(f"external stack registry conflict: {stack_id}")
        STACKS[stack_id] = candidate
    return tuple(sorted(_EXTERNAL_STACKS))
