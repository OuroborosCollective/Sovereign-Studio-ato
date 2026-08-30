from __future__ import annotations

import json
from pathlib import Path
import subprocess

from managed_compose import ManagedComposeRuntime, STACKS


def test_sovereign_backend_template_is_bounded_and_hostinger_visible() -> None:
    root = Path(__file__).resolve().parents[1]
    template = (root / "templates" / "sovereign-backend" / "docker-compose.yml").read_text("utf-8")
    installer = (root / "deploy" / "install-on-vps.sh").read_text("utf-8")

    assert 'image: "${SOVEREIGN_BACKEND_IMAGE:?immutable backend image is required}"' in template
    assert "container_name: sovereign-backend" in template
    assert "127.0.0.1:8788:8787" in template
    assert "external: true" in template
    assert "network_mode: host" not in template
    assert ":latest" not in template
    assert "/var/run/docker.sock" not in template
    assert 'BACKEND_TEMPLATE_SOURCE="$SOURCE_DIR/templates/sovereign-backend"' in installer
    assert 'templates/sovereign-backend/docker-compose.yml' in installer


def test_backend_managed_policy_matches_live_network_and_broker_contract() -> None:
    stack = STACKS["sovereign-backend"]

    assert {
        "supabase_default",
        "areloria_arelorian-network",
        "sovereign-private",
        "traefik-public",
    }.issubset(set(stack.allowed_networks))
    assert "/run/sovereign-chatgpt-broker" in stack.allowed_bind_roots
    assert stack.allowed_published_ports == ("127.0.0.1:8788:8787",)


def test_backend_transport_requires_compose_identity_and_loopback_binding() -> None:
    runtime = ManagedComposeRuntime()
    state = {
        "present": True,
        "running": True,
        "project": "sovereign-backend",
        "service": "sovereign-backend",
        "networks": [
            "supabase_default",
            "areloria_arelorian-network",
            "sovereign-private",
            "traefik-public",
        ],
        "publishedPorts": {
            "8787/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8788"}],
        },
        "imageReference": (
            "ghcr.io/ouroboroscollective/sovereign-backend@"
            "sha256:" + "a" * 64
        ),
        "mounts": [{
            "destination": "/run/sovereign-chatgpt-broker",
            "rw": False,
        }],
        "privileged": False,
    }

    assert runtime._backend_transport_ready(state) is True
    state["project"] = ""
    assert runtime._backend_transport_ready(state) is False


def test_backend_render_uses_public_compose_runtime_env(tmp_path: Path) -> None:
    stack = STACKS["sovereign-backend"]
    deploy_root = tmp_path / "deploy"
    deploy_root.mkdir()
    runtime_env = deploy_root / "compose-runtime.env"
    runtime_env.write_text(
        "SOVEREIGN_BACKEND_IMAGE=example.invalid/backend@sha256:" + "a" * 64 + "\n"
        "SOVEREIGN_BACKEND_IMAGE_DIGEST=sha256:" + "a" * 64 + "\n"
        "SOVEREIGN_BACKEND_SOURCE_REVISION=" + "b" * 40 + "\n"
        "SOVEREIGN_BACKEND_ENV_FILE=/run/secrets/sovereign-backend.env\n"
        "SOVEREIGN_BACKEND_MANAGED_ENV_FILE=/opt/sovereign-chatgpt-tools/backend-runtime.env\n"
        "SOVEREIGN_MCP_BROKER_GID=10001\n"
        "SOVEREIGN_TRAEFIK_DOCKER_NETWORK=traefik-public\n",
        "utf-8",
    )
    stack = type(stack)(**{**stack.__dict__, "deploy_root": str(deploy_root)})
    commands: list[list[str]] = []

    rendered = {
        "services": {
            "sovereign-backend": {
                "image": "example.invalid/backend@sha256:" + "a" * 64,
                "networks": {
                    "supabase_default": None,
                    "areloria_arelorian-network": None,
                    "sovereign-private": None,
                    "traefik-public": None,
                },
                "volumes": [
                    {"type": "bind", "source": "/opt/secure", "target": "/opt/secure"},
                    {
                        "type": "bind",
                        "source": "/run/sovereign-chatgpt-broker",
                        "target": "/run/sovereign-chatgpt-broker",
                    },
                ],
                "ports": [{
                    "host_ip": "127.0.0.1",
                    "published": 8788,
                    "target": 8787,
                }],
            },
        },
        "networks": {
            "supabase_default": {},
            "areloria_arelorian-network": {},
            "sovereign-private": {},
            "traefik-public": {},
        },
    }

    def runner(argv, **kwargs):
        commands.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps(rendered), "")

    runtime = ManagedComposeRuntime(runner=runner, template_root=str(tmp_path / "templates"))
    _path, temporary, _rendered = runtime._render_template(
        stack,
        [("docker-compose.yml", b"services: {}\n")],
    )
    temporary.cleanup()

    command = commands[0]
    env_index = command.index("--env-file")
    assert command[env_index + 1] == str(runtime_env)
    assert _rendered == rendered
