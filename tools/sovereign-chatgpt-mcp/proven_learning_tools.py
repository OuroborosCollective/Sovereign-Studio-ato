"""Tool-only MCP contracts for evidence-proven learning and repository logbooks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from mcp.types import ToolAnnotations

from policy import safe_repo_path

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
NON_IDEMPOTENT_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
IDEMPOTENT_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

_RUNTIME: Any = None
_OWNER_INPUT: Any = None
_REGISTERED = False
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_MARKER = re.compile(r"<!-- proven-learning:([0-9a-f]{64}) -->")
_LOGBOOK_PATH = "docs/SOVEREIGN_LEARNING_LOGBOOK.md"
_MANIFEST_PATH = ".sovereign/proven-learning-manifest.json"
_IMPORTANT_EXACT = frozenset({
    "AGENTS.md",
    "AGENTS_KNOWLEDGE.md",
    "AGENTS_SKILLS.md",
    "AGENTS_BEST_PRACTICES.md",
    "package.json",
    "pnpm-lock.yaml",
    "tsconfig.json",
    "vite.config.ts",
    ".env.example",
    "scripts/sovereign-backend/Dockerfile",
    "tools/sovereign-chatgpt-mcp/Dockerfile",
})
_IMPORTANT_PREFIXES = (
    ".github/workflows/",
    "scripts/sovereign-backend/migrations/",
    "deploy/",
)
_IMPORTANT_NAMES = frozenset({
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "pyproject.toml",
    "requirements.txt",
})


def _repo(workspace_id: str) -> Path:
    if _RUNTIME is None:
        raise RuntimeError("Proven learning tools are not registered")
    return _RUNTIME._repo(workspace_id)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.proven-learning.tmp")
    temporary.write_text(content, "utf-8")
    temporary.replace(path)


def _clean_line(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _validated_plan(plan: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(plan, dict) or plan.get("status") != "PROVEN_LEARNING_PLAN_READY":
        raise ValueError("plan must be a backend-confirmed proven-learning plan")
    digest = _clean_line(plan.get("confirmationSha256"), 80).casefold()
    record = plan.get("record")
    if not _HEX_64.fullmatch(digest) or not isinstance(record, dict):
        raise ValueError("plan is missing its exact confirmation hash or record")
    if record.get("content_hash") != f"sha256:{digest}":
        raise ValueError("plan record and confirmation hash do not match")
    return digest, record


def proven_learning_pattern_plan(record: dict[str, Any]) -> dict[str, Any]:
    """Use this when a verified outcome should be normalized and hashed without writing any database row."""
    if _OWNER_INPUT is None:
        raise RuntimeError("Owner-input backend client is unavailable")
    return _OWNER_INPUT.plan_proven_learning(record)


def proven_learning_owner_approval_request(
    confirmation_sha256: str,
    title: str,
    reason: str,
    expires_in_seconds: int = 900,
) -> dict[str, Any]:
    """Use this when an exact proven-learning plan needs fresh authenticated Owner consent before persistence."""
    if _OWNER_INPUT is None:
        raise RuntimeError("Owner-input backend client is unavailable")
    digest = _clean_line(confirmation_sha256, 80).casefold()
    if not _HEX_64.fullmatch(digest):
        raise ValueError("confirmation_sha256 must be an exact SHA-256")
    bounded_reason = _clean_line(reason, 700)
    return _OWNER_INPUT.create_request(
        target_id="proven_learning_confirmation",
        title=_clean_line(title, 140) or "Learning Pattern freigeben",
        reason=f"{bounded_reason} Exakter Plan-Hash: {digest}"[:1000],
        field_label="Exakten 64-stelligen Plan-Hash eingeben",
        expires_in_seconds=expires_in_seconds,
    )


def proven_learning_pattern_apply(
    request_id: str = "",
    confirmation_sha256: str = "",
    record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Use this after Owner approval to idempotently persist one exact pattern and verify pgvector readback."""
    if _OWNER_INPUT is None:
        raise RuntimeError("Owner-input backend client is unavailable")
    return _OWNER_INPUT.apply_proven_learning(
        request_id=request_id,
        confirmation_sha256=confirmation_sha256,
        record=record,
    )


def _important_manifests(repo: Path) -> list[dict[str, Any]]:
    tracked = set(_git(repo, "ls-files").splitlines())
    candidates = set(_IMPORTANT_EXACT)
    candidates.update(
        path for path in tracked
        if path.startswith(_IMPORTANT_PREFIXES)
        or Path(path).name in _IMPORTANT_NAMES
    )
    if (repo / _LOGBOOK_PATH).is_file():
        candidates.add(_LOGBOOK_PATH)
    output: list[dict[str, Any]] = []
    for relative in sorted(candidates):
        if relative == _MANIFEST_PATH:
            continue
        try:
            path = safe_repo_path(repo, relative, must_exist=True)
        except (ValueError, FileNotFoundError):
            continue
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        output.append({
            "path": relative,
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        })
    return output


def repository_learning_logbook_update(
    workspace_id: str,
    plan: dict[str, Any],
    merge_target: str = "main",
    expected_pr_head_sha: str = "",
) -> dict[str, Any]:
    """Use this before a merge to idempotently update the human logbook and manifest snapshot in the reviewed branch."""
    repo = _repo(workspace_id)
    digest, record = _validated_plan(plan)
    target = _clean_line(merge_target, 120)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,119}", target):
        raise ValueError("merge_target is invalid")
    expected_head = _clean_line(expected_pr_head_sha, 80).casefold()
    if expected_head and not _HEX_40.fullmatch(expected_head):
        raise ValueError("expected_pr_head_sha must be an exact Git SHA")

    evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    source_revision = _clean_line(evidence.get("revision"), 80).casefold()
    if not _HEX_40.fullmatch(source_revision):
        raise ValueError("plan evidence lacks an exact source revision")
    checks = evidence.get("checks") if isinstance(evidence.get("checks"), list) else []
    marker = f"<!-- proven-learning:{digest} -->"
    logbook_path = safe_repo_path(repo, _LOGBOOK_PATH)
    if logbook_path.exists():
        logbook = logbook_path.read_text("utf-8")
    else:
        logbook = (
            "# Sovereign Learning Logbook\n\n"
            "Dieses Logbuch enthält ausschließlich evidence-geprüfte, deduplizierte Lernmuster. "
            "Ein Eintrag ist keine Laufzeitwahrheit für spätere Revisionen und muss vor Wiederverwendung erneut geprüft werden.\n"
        )
    created = marker not in logbook
    if created:
        check_lines = "\n".join(
            f"- {_clean_line(item.get('name'), 160)} "
            f"({_clean_line(item.get('source'), 80)}, SHA-256 {_clean_line(item.get('evidence_sha256'), 80)}): "
            f"{_clean_line(item.get('summary'), 500)}"
            for item in checks
            if isinstance(item, dict)
        )
        changed = ", ".join(_clean_line(item, 240) for item in (evidence.get("changed_paths") or [])) or "keine Repository-Datei"
        refs = "; ".join(
            f"{_clean_line(item.get('repository'), 240)}@{_clean_line(item.get('revision'), 80)}:"
            f"{_clean_line(item.get('path'), 300)}"
            for item in (record.get("source_refs") or [])
            if isinstance(item, dict)
        )
        entry = (
            f"\n\n{marker}\n"
            f"## {_clean_line(record.get('title'), 240)}\n\n"
            f"- Zeitpunkt: {_clean_line(evidence.get('completed_at'), 80)}\n"
            f"- Vorgang: {_clean_line(evidence.get('operation_type'), 40)}\n"
            f"- Inhalts-Hash: sha256:{digest}\n"
            f"- Quellrevision: {source_revision}\n"
            f"- Merge-Ziel: {target}\n"
            f"- Erwarteter PR-Head: {expected_head or 'wird beim PR-Gate gebunden'}\n"
            f"- Geänderte Pfade: {changed}\n"
            f"- Problem: {_clean_line(record.get('problem'), 1000)}\n"
            f"- Lösung: {_clean_line(record.get('solution'), 1500)}\n"
            f"- Gültigkeit: {_clean_line(record.get('applicability'), 1000)}\n"
            f"- Quellen: {refs}\n\n"
            f"### Nachweise\n\n{check_lines or '- keine gültigen Nachweise'}\n"
        )
        _atomic_text(logbook_path, logbook.rstrip() + entry + "\n")

    manifests = _important_manifests(repo)
    current_logbook = logbook_path.read_text("utf-8")
    learning_hashes = sorted(set(_MARKER.findall(current_logbook)))
    manifest_payload = {
        "schemaVersion": "sovereign.proven-learning-manifest.v1",
        "generatedFromRepositoryRevision": _git(repo, "rev-parse", "HEAD"),
        "generatedAt": _clean_line(evidence.get("completed_at"), 80),
        "mergeTarget": target,
        "expectedPrHeadSha": expected_head or None,
        "latestPatternSha256": digest,
        "learningPatternSha256": learning_hashes,
        "importantManifestFiles": manifests,
        "logbookPath": _LOGBOOK_PATH,
        "logbookSha256": _sha256(logbook_path),
        "selfHashExcluded": True,
    }
    manifest_path = safe_repo_path(repo, _MANIFEST_PATH)
    _atomic_text(manifest_path, json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return {
        "ok": True,
        "status": "REPOSITORY_LEARNING_LOGBOOK_UPDATED" if created else "REPOSITORY_LEARNING_LOGBOOK_ALREADY_CURRENT",
        "contentSha256": digest,
        "entryCreated": created,
        "logbookPath": _LOGBOOK_PATH,
        "manifestPath": _MANIFEST_PATH,
        "manifestFileCount": len(manifests),
        "repositoryWritten": True,
        "databaseAccessed": False,
        "mergePerformed": False,
        "postMergeRule": "Verify this exact entry and manifest at the merged revision; never bypass the reviewed merge.",
    }


def register(mcp: Any, runtime: Any, owner_input: Any) -> None:
    global _RUNTIME, _OWNER_INPUT, _REGISTERED
    _RUNTIME = runtime
    _OWNER_INPUT = owner_input
    if _REGISTERED:
        return
    mcp.tool(annotations=READ_ONLY)(proven_learning_pattern_plan)
    mcp.tool(annotations=NON_IDEMPOTENT_WRITE)(proven_learning_owner_approval_request)
    for tool in (
        proven_learning_pattern_apply,
        repository_learning_logbook_update,
    ):
        mcp.tool(annotations=IDEMPOTENT_WRITE)(tool)
    _REGISTERED = True
