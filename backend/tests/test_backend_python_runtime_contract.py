from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_backend_test_requirements_extend_production_runtime() -> None:
    requirements = read("backend/requirements-test.txt")
    assert "-r ../scripts/sovereign-backend/requirements.txt" in requirements
    assert "pytest>=9.1.1,<10" in requirements
    assert "openai-agents==0.18.2" in read("scripts/sovereign-backend/requirements.txt")


def test_shared_backend_python_action_installs_and_verifies_one_contract() -> None:
    action = read(".github/actions/setup-backend-python/action.yml")
    assert "backend/requirements-test.txt" in action
    assert "scripts/sovereign-backend/requirements.txt" in action
    assert "python -m pip install --requirement backend/requirements-test.txt" in action
    assert "python -m pip check" in action
    assert "python scripts/check-backend-python-runtime.py" in action


def test_backend_workflows_use_shared_action_without_manual_flask_lists() -> None:
    ci = read(".github/workflows/ci.yml")
    backend = read(".github/workflows/sovereign-agent-backend.yml")

    assert ci.count("uses: ./.github/actions/setup-backend-python") >= 2
    assert backend.count("uses: ./.github/actions/setup-backend-python") >= 1
    assert "pip install pytest cryptography pyjwt psycopg2-binary flask" not in ci
    assert "pip install -r scripts/sovereign-backend/requirements.txt pytest" not in backend


def test_local_backend_runner_uses_same_dependency_and_canary_contract() -> None:
    runner = read("scripts/run-backend-tests.sh")
    assert "backend/requirements-test.txt" in runner
    assert "scripts/check-backend-python-runtime.py" in runner
    assert "-m pip check" in runner
    assert "-m pytest" in runner


def test_runtime_canary_checks_flask_live_path_and_security_dependencies() -> None:
    canary = read("scripts/check-backend-python-runtime.py")
    for dependency in (
        '"flask": "flask"',
        '"flask-cors": "flask_cors"',
        '"psycopg2-binary": "psycopg2"',
        '"cryptography": "cryptography"',
        '"PyJWT": "jwt"',
        '"pypdf": "pypdf"',
        '"webauthn": "webauthn"',
        '"openai-agents": "agents"',
        '"pytest": "pytest"',
    ):
        assert dependency in canary
    assert "Flask.test_client unavailable" in canary
    assert "BACKEND_PYTHON_RUNTIME=PASS" in canary
