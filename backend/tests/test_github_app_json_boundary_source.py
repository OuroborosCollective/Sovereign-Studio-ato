from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SOURCE = REPO_ROOT / "backend" / "github_app.py"
DEPLOY_SOURCE = REPO_ROOT / "scripts" / "sovereign-backend" / "github_app.py"


def _source(path: Path) -> str:
    return path.read_text("utf-8")


def test_github_app_post_routes_require_json_objects_in_both_runtime_surfaces() -> None:
    for path in (BACKEND_SOURCE, DEPLOY_SOURCE):
        source = _source(path)
        assert source.count("request.get_json(silent=True)") >= 2
        assert '"blocker": "github_app_webhook_payload_invalid"' in source
        assert '"blocker": "github_app_credit_payload_invalid"' in source
        assert 'payload = request.get_json() or {}' not in source
        assert 'body = request.get_json() or {}' not in source


def test_deployment_mirror_keeps_newer_github_app_identity_evidence() -> None:
    backend_source = _source(BACKEND_SOURCE)
    deploy_source = _source(DEPLOY_SOURCE)

    assert "def github_app_identity_evidence()" not in backend_source
    assert "def github_app_identity_evidence()" in deploy_source
    assert "github_app_identity_mismatch" in deploy_source
