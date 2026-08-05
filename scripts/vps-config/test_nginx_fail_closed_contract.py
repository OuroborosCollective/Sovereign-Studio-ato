from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "scripts/vps-config/nginx/openhands.arelorian.de.conf"
SETUP_PATH = ROOT / "scripts/vps-config/setup-nginx.sh"


def _embedded_nginx_config(setup_script: str) -> str:
    start_marker = "cat > \"$CONFIG_FILE\" << 'NGINXCONF'\n"
    end_marker = "\nNGINXCONF\n"
    assert setup_script.count(start_marker) == 1
    start = setup_script.index(start_marker) + len(start_marker)
    end = setup_script.index(end_marker, start)
    return setup_script[start:end].strip()


def test_committed_and_generated_nginx_servers_are_identical_and_fail_closed() -> None:
    committed = CONFIG_PATH.read_text(encoding="utf-8")
    generated = _embedded_nginx_config(SETUP_PATH.read_text(encoding="utf-8"))
    committed_servers = committed[committed.index("server {") :].strip()

    assert generated == committed_servers
    assert "proxy_pass" not in generated
    assert "127.0.0.1:3000" not in generated
    assert generated.count("return 403;") == 2
    assert 'add_header X-Sovereign-Fail-Closed "issue#1196-proxy-drift" always;' in generated
    assert "return 301 https://$host$request_uri;" in generated


def test_setup_message_does_not_claim_openhands_is_available() -> None:
    setup_script = SETUP_PATH.read_text(encoding="utf-8")

    assert "OpenHands admin should be available" not in setup_script
    assert "deliberately fail-closed with HTTP 403" in setup_script
