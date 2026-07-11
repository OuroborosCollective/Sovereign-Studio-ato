#!/usr/bin/env python3
"""Apply the urgent, deterministic repository-containment patch.

This script deliberately avoids knowing any leaked credential value. It removes
password-based SSH examples generically, disables the unfinished embedded runner,
repairs the repository workspace bootstrap, and removes temporary patch payloads.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DOC_PATHS = (
    ROOT / "AGENTS_BEST_PRACTICES.md",
    ROOT / "AGENTS_KNOWLEDGE.md",
    ROOT / "AGENTS_SKILLS.md",
    ROOT / "scripts/sovereign-backend/migrations/AGENTS_MIGRATION_SKILL.md",
)
RUNNER_PATH = ROOT / "scripts/sovereign-backend/agent_runtime/sovereign_local_runner.py"
GIT_WORKSPACE_PATHS = (
    ROOT / "backend/agent_runtime/git_workspace.py",
    ROOT / "scripts/sovereign-backend/agent_runtime/git_workspace.py",
)
PAYLOAD_DIR = ROOT / ".github/patch-payload"
INCIDENT_PATH = ROOT / "docs/security/2026-07-11-credential-exposure.md"

SSH_CONNECT_RE = re.compile(
    r"client\.connect\([^\n)]*username\s*=\s*['\"]root['\"][^\n)]*"
    r"password\s*=\s*['\"][^'\"]+['\"][^\n)]*\)",
    re.IGNORECASE,
)
PASSWORD_CONNECT_RE = re.compile(
    r"client\.connect\([^\n)]*password\s*=\s*['\"][^'\"]+['\"][^\n)]*\)",
    re.IGNORECASE,
)
DIRECT_MAIN_PUSH_RE = re.compile(r"(?m)^\s*git push origin main\s*$")

SAFE_SSH_EXAMPLE = (
    "client.load_system_host_keys()\n"
    "client.set_missing_host_key_policy(paramiko.RejectPolicy())\n"
    "client.connect(\n"
    "    os.environ['VPS_HOST'],\n"
    "    username=os.environ['VPS_USER'],\n"
    "    key_filename=os.environ['VPS_SSH_KEY_FILE'],\n"
    "    timeout=30,\n"
    ")"
)

INCIDENT_TEXT = """# Credential exposure containment — 2026-07-11

A production debugging session introduced authentication material into generated
agent documentation and external work logs. The repository copy is sanitized by
this change without recording the exposed values again.

Required operational actions outside this repository:

1. Rotate the VPS administrator credential and prefer a non-root deploy account.
2. Rotate database, admin API, JWT/session, and LLM proxy credentials that appeared
   in the affected work log.
3. Invalidate sessions derived from the previous JWT secret.
4. Review SSH, API, database, and provider access logs for unexpected use.
5. Rewrite affected public Git history after rotations are complete. A normal
   follow-up commit does not remove values from earlier commits.
6. Do not paste replacement credentials into issues, pull requests, chat, logs, or
   repository documentation.

Runtime containment in this change:

- autonomous repository changes may only create Draft PRs;
- direct Dependabot auto-merge is removed;
- the unfinished local runner is disabled and its standalone entrypoint is
  quarantined;
- backend host publishing is limited to localhost;
- deploy images carry their source revision.
"""


def replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Expected text not found for {label}")
    return text.replace(old, new)


def sanitize_document(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = SSH_CONNECT_RE.sub(SAFE_SSH_EXAMPLE, text)
    text = PASSWORD_CONNECT_RE.sub(SAFE_SSH_EXAMPLE, text)
    text = DIRECT_MAIN_PUSH_RE.sub(
        'git push --set-upstream origin "$BRANCH"  # then open a Draft PR',
        text,
    )
    text = text.replace(
        "### ✅ DO: Copy Files Not Rebuild (Python-only fixes)",
        "### ❌ DON'T: Treat a patched live container as the release source",
    )
    text = text.replace(
        "# Fast hotfix: copy to running container",
        "# Build and deploy from a reviewed commit; do not make the container the source of truth",
    )
    text = text.replace(
        "### ✅ DO: Single Lock for Gunicorn Workers",
        "### ❌ DON'T: Use a thread lock as a cross-process worker singleton",
    )
    text = text.replace(
        "Thread-safe singleton: only one daemon runs even with multiple gunicorn workers.",
        "A thread lock is process-local and cannot coordinate multiple Gunicorn workers.",
    )
    path.write_text(text, encoding="utf-8")


def disable_embedded_runner() -> None:
    text = RUNNER_PATH.read_text(encoding="utf-8")
    text = replace_required(
        text,
        'ENABLED = os.getenv("SOVEREIGN_RUNNER_ENABLED", "true").lower() == "true"',
        'ENABLED = os.getenv("SOVEREIGN_RUNNER_ENABLED", "false").lower() == "true"',
        "runner default",
    )
    RUNNER_PATH.write_text(text, encoding="utf-8")


def repair_workspace_bootstrap(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = "        if any(repo_path.iterdir()):"
    new = "        repo_path.mkdir(parents=True, exist_ok=True)\n        if any(repo_path.iterdir()):"
    if new not in text:
        text = replace_required(text, old, new, f"workspace bootstrap in {path}")
    path.write_text(text, encoding="utf-8")


def validate() -> None:
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        if PASSWORD_CONNECT_RE.search(text):
            raise RuntimeError(f"Password-based SSH example remains in {path}")
        if DIRECT_MAIN_PUSH_RE.search(text):
            raise RuntimeError(f"Direct main push instruction remains in {path}")

    runner = RUNNER_PATH.read_text(encoding="utf-8")
    expected = 'ENABLED = os.getenv("SOVEREIGN_RUNNER_ENABLED", "false").lower() == "true"'
    if expected not in runner:
        raise RuntimeError("Runner is not fail-closed by default")

    for path in GIT_WORKSPACE_PATHS:
        text = path.read_text(encoding="utf-8")
        if "repo_path.mkdir(parents=True, exist_ok=True)" not in text:
            raise RuntimeError(f"Workspace bootstrap fix missing in {path}")

    if PAYLOAD_DIR.exists():
        raise RuntimeError("Temporary patch payload directory still exists")


for document in DOC_PATHS:
    sanitize_document(document)
disable_embedded_runner()
for workspace_path in GIT_WORKSPACE_PATHS:
    repair_workspace_bootstrap(workspace_path)
if PAYLOAD_DIR.exists():
    shutil.rmtree(PAYLOAD_DIR)
INCIDENT_PATH.parent.mkdir(parents=True, exist_ok=True)
INCIDENT_PATH.write_text(INCIDENT_TEXT, encoding="utf-8")
validate()
print("Urgent repository containment applied successfully.")
