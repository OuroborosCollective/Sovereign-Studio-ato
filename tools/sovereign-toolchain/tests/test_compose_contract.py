from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def test_toolchain_compose_does_not_require_an_external_dotenv_file() -> None:
    content = COMPOSE.read_text(encoding="utf-8")
    assert "env_file:" not in content
    assert "${BROKER_GID" not in content
    assert "${SOVEREIGN_MCP_IMAGE" not in content


def test_toolchain_compose_keeps_the_expected_service_and_archives_mount() -> None:
    content = COMPOSE.read_text(encoding="utf-8")
    assert "services:" in content
    assert "  sovereign-toolchain:" in content
    assert "    build: ." in content
    assert '      - "8000:8000"' in content
    assert "      - ./archives:/archives:ro" in content
