from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release-verification.yml"


def test_runtime_unit_failure_log_is_preserved_without_masking_exit_code() -> None:
    workflow = WORKFLOW.read_text("utf-8")

    assert "set -o pipefail" in workflow
    assert "pnpm run test:unit 2>&1 | tee .security-reports/runtime-unit-tests.log" in workflow
    assert "- name: Upload Runtime Unit Test Report" in workflow
    assert "if: always()" in workflow
    assert "runtime-unit-tests-${{ github.run_id }}-${{ github.run_attempt }}" in workflow
    assert "path: .security-reports/runtime-unit-tests.log" in workflow
