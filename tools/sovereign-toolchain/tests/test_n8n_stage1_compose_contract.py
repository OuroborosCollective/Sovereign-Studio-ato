from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "sovereign-toolchain" / "adapters" / "n8n-sovereign-stage1.compose.yml"


def source() -> str:
    return COMPOSE.read_text("utf-8")


def test_reverse_proxy_contract_uses_current_n8n_variables() -> None:
    text = source()
    assert "N8N_PROXY_HOPS=1" in text
    assert "N8N_WEBHOOK_URL=https://" in text
    assert "N8N_EDITOR_BASE_URL=https://" in text
    assert "N8N_SECURE_COOKIE=true" in text
    assert "WEBHOOK_URL=" not in text.replace("N8N_WEBHOOK_URL=", "")
    assert "N8N_RUNNERS_ENABLED=" not in text


def test_editor_port_is_not_published_on_all_interfaces() -> None:
    text = source()
    assert '"127.0.0.1:5678:5678"' in text
    assert '"5678"' not in text
    assert "0.0.0.0:5678" not in text


def test_all_runtime_images_require_explicit_immutable_refs() -> None:
    text = source()
    assert ":latest" not in text
    assert "image: ${N8N_IMAGE_REF:?" in text
    assert text.count("image: ${N8N_SANDBOX_API_IMAGE_REF:?") == 2
    assert "image: ${N8N_SANDBOX_RUNNER_IMAGE_REF:?" in text
    assert "SANDBOX_RUNNER_DOCKER_SANDBOX_IMAGE=${N8N_SANDBOX_INNER_IMAGE_REF:?" in text


def test_sandbox_services_are_health_gated_and_not_host_published() -> None:
    text = source()
    assert "condition: service_completed_successfully" in text
    assert text.count("condition: service_healthy") >= 2
    assert "http://127.0.0.1:8080/healthz" in text
    assert "http://127.0.0.1:8080/readyz" in text
    assert "8080:8080" not in text
    assert "9090:9090" not in text
    assert "9091:9091" not in text


def test_stage1_dind_boundary_is_explicitly_transitional() -> None:
    text = source()
    assert "privileged: true" in text
    assert "Do not inject" in text
    assert "Sysbox or Firecracker" in text
