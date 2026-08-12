from pathlib import Path
import contextlib
import io
import json
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent_runtime.configuration import config_source_inventory as csi
from agent_runtime.configuration.config_source_inventory import build_inventory


def test_inventory_excludes_retired_litellm_and_secret_shaped_env_names(tmp_path: Path) -> None:
    (tmp_path / "deploy/active").mkdir(parents=True)
    (tmp_path / "deploy/active/docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "deploy/sovereign-litellm").mkdir(parents=True)
    (tmp_path / "deploy/sovereign-litellm/docker-compose.yml").write_text(
        "services: {}\n", encoding="utf-8"
    )

    (tmp_path / "backend/agent_runtime").mkdir(parents=True)
    (tmp_path / "backend/agent_runtime/sample_env.py").write_text(
        'import os\nSAFE_SETTING = os.getenv("SAFE_SETTING")\n'
        'OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")\n'
        'PASSWORD = os.environ["DATABASE_PASSWORD"]\n',
        encoding="utf-8",
    )

    (tmp_path / "src").mkdir()
    (tmp_path / "src/sample.ts").write_text(
        "const safe = import.meta.env.VITE_SAFE_SETTING;\n"
        "const secret = import.meta.env.VITE_SECRET_TOKEN;\n",
        encoding="utf-8",
    )

    inventory = build_inventory(tmp_path)
    compose_paths = {entry["relativePath"] for entry in inventory["composeSurfaces"]}
    env_names = {entry["name"] for entry in inventory["environmentFallbacks"]}

    assert "deploy/active/docker-compose.yml" in compose_paths
    assert "deploy/sovereign-litellm/docker-compose.yml" not in compose_paths
    assert "SAFE_SETTING" in env_names
    assert "VITE_SAFE_SETTING" in env_names
    assert "OPENROUTER_API_KEY" not in env_names
    assert "DATABASE_PASSWORD" not in env_names
    assert "VITE_SECRET_TOKEN" not in env_names


def test_inventory_canonical_and_deployment_mirror_are_byte_identical() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    canonical = repo_root / "backend/agent_runtime/configuration/config_source_inventory.py"
    mirror = repo_root / "scripts/sovereign-backend/agent_runtime/configuration/config_source_inventory.py"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_default_repo_root_resolves_to_actual_repo_root_no_false_drift() -> None:
    # Regression guard: the CLI default --repo-root must resolve to the actual
    # repository root, not one level above it. An off-by-one here made every
    # provenance surface report as missing and `--strict` exit non-zero on a
    # healthy tree (false drift). The existing build_inventory() tests pass
    # explicit paths and so never exercised the default; this invokes main()
    # with no --repo-root and asserts honest, drift-free output.
    repo_root = Path(__file__).resolve().parents[2]

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = csi.main(["--strict"])
    assert rc == 0, "inventory --strict must pass on a healthy repo using the default repo-root"
    inventory = json.loads(buf.getvalue())
    assert inventory["drift"] == [], inventory["drift"]
    # The default must have resolved to the real repo root, so every required
    # provenance surface is present and the required-surface count is non-zero.
    present_required = {s["label"] for s in inventory["surfaces"] if s["present"]}
    assert set(csi.REQUIRED_LABELS) <= present_required
    # Sanity: the resolved root is the repository root, not a parent directory.
    assert Path(csi.HERE.parents[2]).resolve() == repo_root.resolve()
