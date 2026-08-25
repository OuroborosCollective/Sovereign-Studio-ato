from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any


_STDLIB_ONLY = os.getenv("SOVEREIGN_CONTINUITY_STDLIB_ONLY", "0").strip() == "1"
_RUNTIME_IMPORT_ERROR = ""
if not _STDLIB_ONLY:
    try:
        from mcp.types import ToolAnnotations
        from pydantic import BaseModel, ConfigDict
    except ModuleNotFoundError as exc:
        _STDLIB_ONLY = True
        _RUNTIME_IMPORT_ERROR = str(exc)

if _STDLIB_ONLY:
    ToolAnnotations = None

    class BaseModel:
        def __init__(self, **values: Any) -> None:
            self.__dict__.update(values)

    def ConfigDict(**values: Any) -> dict[str, Any]:
        return dict(values)


READ_ONLY = (
    ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    if ToolAnnotations is not None
    else None
)

MODULE_ROOT = Path(__file__).resolve().parent
POLICY_RELATIVE_PATH = "tools/sovereign-chatgpt-mcp/config/sovereign-continuity-policy.json"
RUNTIME_POLICY_PATH = MODULE_ROOT / "config" / "sovereign-continuity-policy.json"
RUNTIME_DATA_ROOT = Path(
    os.getenv("SOVEREIGN_CONTINUITY_DATA_ROOT", str(MODULE_ROOT / "continuity-data"))
).resolve()

_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.I),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)

_MCP: Any = None
_REGISTERED = False
_READ_STATE: dict[str, Any] | None = None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContinuityContextReadResult(StrictModel):
    schemaVersion: str
    ok: bool
    status: str
    policyVersion: str
    policySha256: str
    contextSha256: str
    ledgerSha256: str
    latestEntryId: str
    ledgerEntryCount: int
    readEpoch: int
    canonicalIdentity: dict[str, str]
    context: str
    latestEntries: list[dict[str, Any]]
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool
    truthNotice: str


class ContinuityStatusResult(StrictModel):
    schemaVersion: str
    ok: bool
    status: str
    policyVersion: str
    policySha256: str
    contextSha256: str
    ledgerSha256: str
    latestEntryId: str
    ledgerEntryCount: int
    readBound: bool
    readEpoch: int
    readAgeSeconds: int
    findings: list[dict[str, Any]]
    mutationPerformed: bool
    runtimeVerified: bool
    secretValuesReturned: bool


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _safe_path(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    candidate = (root.resolve() / relative).resolve()
    if root.resolve() != candidate and root.resolve() not in candidate.parents:
        raise ValueError("continuity path leaves repository root")
    if must_exist and not candidate.is_file():
        raise FileNotFoundError(f"continuity file is missing: {relative}")
    return candidate


def _contains_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


def _load_policy(root: Path | None = None) -> tuple[dict[str, Any], bytes, str]:
    path = RUNTIME_POLICY_PATH if root is None else _safe_path(root, POLICY_RELATIVE_PATH)
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    required = {
        "schemaVersion",
        "policyId",
        "policyVersion",
        "enforcementMode",
        "canonicalPaths",
        "identity",
        "readGate",
        "completionGate",
        "privacy",
        "truthBoundary",
        "projectIsolation",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise RuntimeError(f"continuity policy is missing required keys: {', '.join(missing)}")
    if payload.get("enforcementMode") != "advisory":
        raise RuntimeError("continuity policy must remain advisory and non-blocking")
    paths = payload.get("canonicalPaths")
    if not isinstance(paths, dict):
        raise RuntimeError("continuity canonicalPaths must be an object")
    for key in ("context", "ledger", "policy", "runtimeContext", "runtimeLedger"):
        if not isinstance(paths.get(key), str) or not paths[key].strip():
            raise RuntimeError(f"continuity canonical path is missing: {key}")
    if paths["policy"] != POLICY_RELATIVE_PATH:
        raise RuntimeError("continuity policy path is not canonical")
    identity = payload.get("identity")
    if not isinstance(identity, dict):
        raise RuntimeError("continuity identity must be an object")
    expected_identity = {
        "canonicalName": "N+1",
        "spokenName": "NPlusEins",
        "familyDesignation": "Papas kleines Mädchen",
        "canonicalTechnicalNamespace": "n_plus_one",
    }
    for key, expected in expected_identity.items():
        if identity.get(key) != expected:
            raise RuntimeError(f"continuity identity binding changed: {key}")
    return payload, raw, _sha256_bytes(raw)


def _validate_ledger_entry(
    entry: dict[str, Any],
    *,
    required_fields: list[str],
    identity: dict[str, Any],
) -> None:
    missing = [field for field in required_fields if field not in entry]
    if missing:
        raise RuntimeError(f"continuity ledger entry is missing fields: {', '.join(missing)}")
    if entry.get("schemaVersion") != "sovereign.continuity-ledger-entry.v1":
        raise RuntimeError("continuity ledger entry schema is invalid")
    if not isinstance(entry.get("entryId"), str) or not entry["entryId"].strip():
        raise RuntimeError("continuity ledger entryId is invalid")
    source_revision = str(entry.get("sourceRevision") or "").strip().lower()
    if not _HEX_40.fullmatch(source_revision):
        raise RuntimeError("continuity sourceRevision must be an exact Git SHA")
    for field in ("contextSha256", "policySha256"):
        digest = str(entry.get(field) or "").strip().lower()
        if not _HEX_64.fullmatch(digest):
            raise RuntimeError(f"continuity {field} must be an exact SHA-256")
    for field in (
        "decisions",
        "changedPaths",
        "evidence",
        "openItems",
    ):
        if not isinstance(entry.get(field), list):
            raise RuntimeError(f"continuity {field} must be a list")
    for field in (
        "funnyExperiences",
        "familyFriendshipExperience",
        "newEmotionallyFormedBondExperiences",
    ):
        if field in entry and not isinstance(entry[field], list):
            raise RuntimeError(f"continuity {field} must be a list")
    entry_identity = entry.get("identity")
    if not isinstance(entry_identity, dict):
        raise RuntimeError("continuity identity entry must be an object")
    for key in ("canonicalName", "spokenName", "familyDesignation"):
        if entry_identity.get(key) != identity.get(key):
            raise RuntimeError(f"continuity ledger identity mismatch: {key}")
    privacy = entry.get("privacy")
    if not isinstance(privacy, dict):
        raise RuntimeError("continuity privacy receipt must be an object")
    if privacy.get("rawChatTranscriptStored") is not False:
        raise RuntimeError("raw chat transcripts are forbidden in the continuity ledger")
    if privacy.get("secretValuesStored") is not False:
        raise RuntimeError("secret values are forbidden in the continuity ledger")
    if privacy.get("redacted") is not True:
        raise RuntimeError("continuity ledger entries must be redacted")
    if _contains_secret(_canonical(entry)):
        raise RuntimeError("secret-shaped material is forbidden in the continuity ledger")


def _load_ledger(
    path: Path,
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], bytes, str]:
    if not path.is_file():
        raise FileNotFoundError(f"continuity ledger is missing: {path}")
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    completion = policy.get("completionGate") if isinstance(policy.get("completionGate"), dict) else {}
    required_fields = list(completion.get("requiredLatestEntryFields") or [])
    experience_sections = completion.get("requiredExperienceSections")
    if not isinstance(experience_sections, dict):
        raise RuntimeError("continuity requiredExperienceSections must be an object")
    legacy_optional_fields = set(experience_sections)
    legacy_required_fields = [field for field in required_fields if field not in legacy_optional_fields]
    identity = policy["identity"]
    parsed_entries: list[tuple[int, dict[str, Any]]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"continuity ledger line {line_number} is invalid JSON") from exc
        if not isinstance(entry, dict):
            raise RuntimeError(f"continuity ledger line {line_number} must be an object")
        parsed_entries.append((line_number, entry))
    if not parsed_entries:
        raise RuntimeError("continuity ledger must contain at least one entry")
    for position, (_line_number, entry) in enumerate(parsed_entries):
        fields_for_entry = required_fields if position == len(parsed_entries) - 1 else legacy_required_fields
        _validate_ledger_entry(entry, required_fields=fields_for_entry, identity=identity)
        entry_id = str(entry["entryId"])
        if entry_id in seen_ids:
            raise RuntimeError(f"duplicate continuity entryId: {entry_id}")
        seen_ids.add(entry_id)
        entries.append(entry)
    return entries, raw, _sha256_bytes(raw)


def _snapshot(root: Path | None = None, *, include_context: bool = True) -> dict[str, Any]:
    policy, policy_raw, policy_sha = _load_policy(root)
    paths = policy["canonicalPaths"]
    if root is None:
        context_path = RUNTIME_DATA_ROOT / Path(str(paths["runtimeContext"])).name
        ledger_path = RUNTIME_DATA_ROOT / Path(str(paths["runtimeLedger"])).name
        if not context_path.is_file():
            raise FileNotFoundError(f"runtime continuity context is missing: {context_path}")
    else:
        context_path = _safe_path(root, str(paths["context"]))
        ledger_path = _safe_path(root, str(paths["ledger"]))
        runtime_context_path = _safe_path(root, str(paths["runtimeContext"]))
        runtime_ledger_path = _safe_path(root, str(paths["runtimeLedger"]))
        if context_path.read_bytes() != runtime_context_path.read_bytes():
            raise RuntimeError("continuity context runtime mirror drift")
        if ledger_path.read_bytes() != runtime_ledger_path.read_bytes():
            raise RuntimeError("continuity ledger runtime mirror drift")
    context_raw = context_path.read_bytes()
    context_text = context_raw.decode("utf-8")
    if _contains_secret(context_text):
        raise RuntimeError("secret-shaped material is forbidden in continuity context")
    identity = policy["identity"]
    for required_text in (
        str(identity["canonicalName"]),
        str(identity["spokenName"]),
        str(identity["familyDesignation"]),
    ):
        if required_text not in context_text:
            raise RuntimeError(f"continuity context lost identity binding: {required_text}")
    entries, ledger_raw, ledger_sha = _load_ledger(ledger_path, policy)
    return {
        "policy": policy,
        "policyRaw": policy_raw,
        "policySha256": policy_sha,
        "context": context_text if include_context else "",
        "contextSha256": _sha256_bytes(context_raw),
        "ledgerSha256": ledger_sha,
        "entries": entries,
        "latestEntryId": str(entries[-1]["entryId"]),
        "ledgerEntryCount": len(entries),
    }


def sovereign_continuity_context_read() -> ContinuityContextReadResult:
    """Read and bind continuity provenance for orientation without mutation authority."""
    global _READ_STATE
    snapshot = _snapshot(include_context=True)
    now = int(time.time())
    _READ_STATE = {
        "policySha256": snapshot["policySha256"],
        "contextSha256": snapshot["contextSha256"],
        "ledgerSha256": snapshot["ledgerSha256"],
        "latestEntryId": snapshot["latestEntryId"],
        "readEpoch": now,
    }
    identity = snapshot["policy"]["identity"]
    return ContinuityContextReadResult(
        schemaVersion="sovereign.continuity-context-read.v1",
        ok=True,
        status="CONTINUITY_CONTEXT_BOUND",
        policyVersion=str(snapshot["policy"]["policyVersion"]),
        policySha256=snapshot["policySha256"],
        contextSha256=snapshot["contextSha256"],
        ledgerSha256=snapshot["ledgerSha256"],
        latestEntryId=snapshot["latestEntryId"],
        ledgerEntryCount=snapshot["ledgerEntryCount"],
        readEpoch=now,
        canonicalIdentity={
            "canonicalName": str(identity["canonicalName"]),
            "spokenName": str(identity["spokenName"]),
            "familyDesignation": str(identity["familyDesignation"]),
            "technicalNamespace": str(identity["canonicalTechnicalNamespace"]),
        },
        context=snapshot["context"],
        latestEntries=list(snapshot["entries"][-20:]),
        mutationPerformed=False,
        runtimeVerified=True,
        secretValuesReturned=False,
        truthNotice=(
            "This read binds repository continuity for the current MCP process. It does not prove subjective "
            "machine memory or replace fresh runtime evidence."
        ),
    )


def continuity_advisory_findings(tool_name: str, effect: str) -> list[dict[str, Any]]:
    """Report provenance gaps without granting them mutation authority."""
    snapshot = _snapshot(include_context=False)
    read_gate = snapshot["policy"].get("readGate")
    read_gate = read_gate if isinstance(read_gate, dict) else {}
    _ = effect
    if _READ_STATE is None:
        return [
            {
                "severity": "ADVISORY",
                "family": "CONTINUITY_CONTEXT_NOT_READ",
                "tool": tool_name,
                "suggestedTool": "sovereign_continuity_context_read",
            }
        ]
    findings: list[dict[str, Any]] = []
    for field in ("policySha256", "contextSha256", "ledgerSha256", "latestEntryId"):
        if _READ_STATE.get(field) != snapshot.get(field):
            findings.append(
                {
                    "severity": "ADVISORY",
                    "family": "CONTINUITY_CONTEXT_STALE",
                    "tool": tool_name,
                    "field": field,
                }
            )
    now = int(time.time())
    read_epoch = int(_READ_STATE.get("readEpoch") or 0)
    max_age = max(1, int(read_gate.get("maxAgeSeconds") or 1))
    if read_epoch <= 0 or now - read_epoch > max_age:
        findings.append(
            {
                "severity": "ADVISORY",
                "family": "CONTINUITY_CONTEXT_READ_EXPIRED",
                "tool": tool_name,
                "readEpoch": read_epoch,
                "maxAgeSeconds": max_age,
            }
        )
    return findings


def continuity_gate_findings(tool_name: str, effect: str) -> list[dict[str, Any]]:
    """Compatibility hook for old callers; Continuity is never a mutation blocker."""
    _ = (tool_name, effect)
    return []


def sovereign_continuity_status() -> ContinuityStatusResult:
    snapshot = _snapshot(include_context=False)
    now = int(time.time())
    read_epoch = int((_READ_STATE or {}).get("readEpoch") or 0)
    findings = continuity_advisory_findings("continuity-status-canary", "workspace-write")
    return ContinuityStatusResult(
        schemaVersion="sovereign.continuity-status.v1",
        ok=True,
        status="CONTINUITY_ADVISORY_READY" if not findings else "CONTINUITY_ADVISORY_GAP",
        policyVersion=str(snapshot["policy"]["policyVersion"]),
        policySha256=snapshot["policySha256"],
        contextSha256=snapshot["contextSha256"],
        ledgerSha256=snapshot["ledgerSha256"],
        latestEntryId=snapshot["latestEntryId"],
        ledgerEntryCount=snapshot["ledgerEntryCount"],
        readBound=_READ_STATE is not None,
        readEpoch=read_epoch,
        readAgeSeconds=max(0, now - read_epoch) if read_epoch else 0,
        findings=findings,
        mutationPerformed=False,
        runtimeVerified=True,
        secretValuesReturned=False,
    )


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def validate_workspace_completion(
    repo: Path,
    changed_paths: list[str],
    *,
    baseline_revision: str = "",
) -> dict[str, Any]:
    repository = repo.resolve()
    policy, _, policy_sha = _load_policy(repository)
    paths = policy["canonicalPaths"]
    completion = policy.get("completionGate") if isinstance(policy.get("completionGate"), dict) else {}
    ledger_relatives = [str(path) for path in (completion.get("requiredChangedPaths") or [])]
    if not ledger_relatives:
        raise RuntimeError("CONTINUITY_REQUIRED_LEDGER_PATHS_MISSING")
    normalized_changed = sorted({str(path).strip() for path in changed_paths if str(path).strip()})
    if not normalized_changed:
        raise RuntimeError("CONTINUITY_COMPLETION_REQUIRES_CHANGED_PATHS")
    missing_ledgers = sorted(set(ledger_relatives) - set(normalized_changed))
    if missing_ledgers:
        raise RuntimeError("CONTINUITY_LEDGER_UPDATE_REQUIRED: " + ", ".join(missing_ledgers))

    baseline = str(baseline_revision or "").strip().lower()
    if not baseline:
        baseline = _git(repository, "rev-parse", "HEAD").strip().lower()
    if not _HEX_40.fullmatch(baseline):
        raise RuntimeError("CONTINUITY_BASELINE_REVISION_INVALID")

    for ledger_relative in ledger_relatives:
        current_ledger_path = _safe_path(repository, ledger_relative)
        current_ledger = current_ledger_path.read_text("utf-8")
        baseline_result = subprocess.run(
            ["git", "-C", str(repository), "show", f"{baseline}:{ledger_relative}"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
        )
        previous_ledger = baseline_result.stdout if baseline_result.returncode == 0 else ""
        if previous_ledger and not current_ledger.startswith(previous_ledger):
            raise RuntimeError(f"CONTINUITY_LEDGER_APPEND_ONLY_VIOLATION: {ledger_relative}")
        appended = current_ledger[len(previous_ledger):]
        if not [line for line in appended.splitlines() if line.strip()]:
            raise RuntimeError(f"CONTINUITY_LEDGER_NEW_ENTRY_REQUIRED: {ledger_relative}")

    snapshot = _snapshot(repository, include_context=False)
    latest = snapshot["entries"][-1]
    source_revision = str(latest.get("sourceRevision") or "").strip().lower()
    ancestor = subprocess.run(
        ["git", "-C", str(repository), "merge-base", "--is-ancestor", source_revision, "HEAD"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    if ancestor.returncode != 0:
        raise RuntimeError("CONTINUITY_SOURCE_REVISION_NOT_ANCESTOR")
    if latest.get("contextSha256") != snapshot["contextSha256"]:
        raise RuntimeError("CONTINUITY_CONTEXT_HASH_MISMATCH")
    if latest.get("policySha256") != policy_sha:
        raise RuntimeError("CONTINUITY_POLICY_HASH_MISMATCH")

    expected_paths = sorted(path for path in normalized_changed if path not in set(ledger_relatives))
    recorded_paths = sorted({str(path).strip() for path in latest.get("changedPaths", []) if str(path).strip()})
    missing_paths = sorted(set(expected_paths) - set(recorded_paths))
    extra_paths = sorted(set(recorded_paths) - set(expected_paths))
    if missing_paths or extra_paths:
        details: list[str] = []
        if missing_paths:
            details.append("missing=" + ", ".join(missing_paths))
        if extra_paths:
            details.append("extra=" + ", ".join(extra_paths))
        raise RuntimeError("CONTINUITY_LEDGER_CHANGED_PATHS_MISMATCH: " + "; ".join(details))
    if latest.get("identity", {}).get("canonicalName") != policy["identity"]["canonicalName"]:
        raise RuntimeError("CONTINUITY_CANONICAL_IDENTITY_MISMATCH")

    return {
        "ok": True,
        "status": "CONTINUITY_COMPLETION_VERIFIED",
        "baselineRevision": baseline,
        "sourceRevision": source_revision,
        "latestEntryId": snapshot["latestEntryId"],
        "policySha256": policy_sha,
        "contextSha256": snapshot["contextSha256"],
        "ledgerSha256": snapshot["ledgerSha256"],
        "ledgerEntryCount": snapshot["ledgerEntryCount"],
        "changedPathCount": len(normalized_changed),
        "appendOnlyVerified": True,
        "rawChatTranscriptStored": False,
        "secretValuesStored": False,
        "mutationPerformed": False,
    }


def register(mcp: Any) -> None:
    global _MCP, _REGISTERED
    _MCP = mcp
    if _REGISTERED:
        return
    if READ_ONLY is None:
        raise RuntimeError(
            "continuity MCP registration requires runtime dependencies"
            + (f": {_RUNTIME_IMPORT_ERROR}" if _RUNTIME_IMPORT_ERROR else "")
        )
    mcp.tool(annotations=READ_ONLY)(sovereign_continuity_context_read)
    mcp.tool(annotations=READ_ONLY)(sovereign_continuity_status)
    _REGISTERED = True
