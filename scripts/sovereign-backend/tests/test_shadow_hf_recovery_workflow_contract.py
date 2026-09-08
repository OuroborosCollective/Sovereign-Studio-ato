from __future__ import annotations

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]


def test_shadow_hf_recovery_workflow_is_exact_revision_and_server_secret_bound():
    workflow = (REPO / ".github" / "workflows" / "sovereign-hf-shadow-recovery.yml").read_text("utf-8")
    dockerfile = (BACKEND / "Dockerfile").read_text("utf-8")
    requirements = (BACKEND / "requirements.txt").read_text("utf-8")

    assert "EXPECTED_REVISION: ${{ github.sha }}" in workflow
    assert "EXPECTED_HF_REVISION: 59b21a247775b2931803f86c4514a8d245eeece8" in workflow
    assert 'org.opencontainers.image.revision' in workflow
    assert 'test "$observed_revision" = "$EXPECTED_REVISION"' in workflow
    assert "{{.State.Running}}" in workflow
    assert "{{.State.Health.Status}}" in workflow
    assert "/health/live" in workflow
    assert "python /app/shadow_inference_hf_recover_cli.py" in workflow
    assert '--expected-hf-revision "$EXPECTED_HF_REVISION"' in workflow
    assert '--candidate-revision "$EXPECTED_REVISION"' in workflow
    assert "--owner-approved" in workflow

    # The runtime resolves Hugging Face credentials from the mounted owner-managed
    # provider pool. GitHub Actions must never receive or interpolate a Hub token.
    assert "HF_TOKEN" not in workflow
    assert "HUGGINGFACE_TOKEN" not in workflow
    assert "secrets.HF" not in workflow

    # Both recovery modules are copied into the immutable backend image and the
    # image already owns the public Hub client dependency.
    assert "COPY *.py ./" in dockerfile
    assert "huggingface_hub" in requirements


def test_shadow_hf_recovery_is_one_shot_path_scoped_not_a_periodic_publisher():
    workflow = (REPO / ".github" / "workflows" / "sovereign-hf-shadow-recovery.yml").read_text("utf-8")

    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert "shadow_inference_hf_recovery.py" in workflow
    assert "shadow_inference_hf_recover_cli.py" in workflow
    assert "schedule:" not in workflow
    assert "workflow_dispatch:" not in workflow
