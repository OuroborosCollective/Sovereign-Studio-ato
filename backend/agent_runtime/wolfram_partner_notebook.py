"""Private Wolfram Cloud projection for the CAG partner analysis ledger.

This module deliberately keeps three identities separate:

* the Wolfram CAG API credential used only by the CAG HTTP transport;
* the Wolfram Cloud secured-authentication consumer key/secret used only to
  open an authenticated WolframCloudSession;
* the secret-free partner handoff pack that is rendered into a private cloud
  notebook and hash-read back after deployment.

A successful render is not evidence. A cloud notebook sync is reported as
verified only when the canonical projection cell is fetched from the fixed
private CloudObject, its SHA-256 matches, and the target permissions read back
as private.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from typing import Any, Mapping

from agent_runtime.wolfram_cag_partner_ledger import (
    PACK_SCHEMA_VERSION,
    assert_partner_safe,
)

NOTEBOOK_PROJECTION_SCHEMA_VERSION = "sovereign.wolfram-partner-notebook-projection.v1"
DEFAULT_WOLFRAM_PARTNER_NOTEBOOK_PATH = "Sovereign/Wolfram-CAG/Partner-Analysis.nb"
DEFAULT_WOLFRAM_CLOUD_CONSUMER_KEY_FILE = "/opt/sovereign-owner-managed/wolfram_cloud_consumer_key.txt"
DEFAULT_WOLFRAM_CLOUD_CONSUMER_SECRET_FILE = "/opt/sovereign-owner-managed/wolfram_cloud_consumer_secret.txt"
MAX_WOLFRAM_CLOUD_CREDENTIAL_BYTES = 8192

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_NOTEBOOK_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,238}\.nb$")


class WolframCloudNotebookError(ValueError):
    def __init__(self, message: str, *, family: str) -> None:
        super().__init__(message)
        self.family = family


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _selected_notebook_path() -> str:
    value = os.getenv("WOLFRAM_PARTNER_NOTEBOOK_PATH", "").strip() or DEFAULT_WOLFRAM_PARTNER_NOTEBOOK_PATH
    if (
        not _NOTEBOOK_PATH.fullmatch(value)
        or value.startswith(("/", "\\"))
        or ".." in value.split("/")
        or "\\" in value
    ):
        raise WolframCloudNotebookError("Wolfram partner notebook path is not allowlisted", family="NOTEBOOK_PATH")
    return value


def _read_fixed_secret_file(*, configured: str, expected: str, label: str) -> str:
    if not configured or configured != expected:
        raise WolframCloudNotebookError(f"{label} file pointer is not configured", family="CLOUD_AUTH")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(expected, flags)
    except OSError as exc:
        raise WolframCloudNotebookError(f"{label} file is unavailable", family="CLOUD_AUTH") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise WolframCloudNotebookError(f"{label} source is not a regular file", family="CLOUD_AUTH")
        if metadata.st_size <= 0 or metadata.st_size > MAX_WOLFRAM_CLOUD_CREDENTIAL_BYTES:
            raise WolframCloudNotebookError(f"{label} file size is invalid", family="CLOUD_AUTH")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise WolframCloudNotebookError(f"{label} file permissions are too broad", family="CLOUD_AUTH")
        raw = os.read(descriptor, MAX_WOLFRAM_CLOUD_CREDENTIAL_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > MAX_WOLFRAM_CLOUD_CREDENTIAL_BYTES:
        raise WolframCloudNotebookError(f"{label} file exceeds the byte limit", family="CLOUD_AUTH")
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise WolframCloudNotebookError(f"{label} file is not UTF-8", family="CLOUD_AUTH") from exc
    if not value or "\x00" in value:
        raise WolframCloudNotebookError(f"{label} value is empty or invalid", family="CLOUD_AUTH")
    return value


def _cloud_credentials() -> tuple[str, str]:
    key = _read_fixed_secret_file(
        configured=os.getenv("WOLFRAM_CLOUD_CONSUMER_KEY_FILE", "").strip(),
        expected=DEFAULT_WOLFRAM_CLOUD_CONSUMER_KEY_FILE,
        label="Wolfram Cloud consumer key",
    )
    secret = _read_fixed_secret_file(
        configured=os.getenv("WOLFRAM_CLOUD_CONSUMER_SECRET_FILE", "").strip(),
        expected=DEFAULT_WOLFRAM_CLOUD_CONSUMER_SECRET_FILE,
        label="Wolfram Cloud consumer secret",
    )
    return key, secret


def _safe_secret_file_metadata(configured: str, expected: str) -> dict[str, Any]:
    if configured != expected:
        return {"configured": False, "validFile": False}
    try:
        metadata = os.stat(expected, follow_symlinks=False)
    except OSError:
        return {"configured": True, "validFile": False}
    valid = (
        stat.S_ISREG(metadata.st_mode)
        and 0 < metadata.st_size <= MAX_WOLFRAM_CLOUD_CREDENTIAL_BYTES
        and not (stat.S_IMODE(metadata.st_mode) & 0o077)
    )
    return {"configured": True, "validFile": bool(valid)}


def wolfram_cloud_notebook_status() -> dict[str, Any]:
    """Return only secret-free configuration metadata; never authenticate here."""
    key_meta = _safe_secret_file_metadata(
        os.getenv("WOLFRAM_CLOUD_CONSUMER_KEY_FILE", "").strip(),
        DEFAULT_WOLFRAM_CLOUD_CONSUMER_KEY_FILE,
    )
    secret_meta = _safe_secret_file_metadata(
        os.getenv("WOLFRAM_CLOUD_CONSUMER_SECRET_FILE", "").strip(),
        DEFAULT_WOLFRAM_CLOUD_CONSUMER_SECRET_FILE,
    )
    try:
        path = _selected_notebook_path()
        path_valid = True
    except WolframCloudNotebookError:
        path = None
        path_valid = False
    return {
        "configured": bool(key_meta["configured"] and secret_meta["configured"]),
        "credentialFilesValid": bool(key_meta["validFile"] and secret_meta["validFile"]),
        "targetPath": path,
        "targetPathValid": path_valid,
        "authenticated": False,
        "syncExecuted": False,
        "secretValuesReturned": False,
        "truthNotice": "Configuration metadata is not Wolfram Cloud authentication or notebook readback evidence.",
    }


def build_partner_notebook_projection(pack: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(pack, Mapping) or pack.get("schemaVersion") != PACK_SCHEMA_VERSION:
        raise WolframCloudNotebookError("canonical Wolfram partner handoff pack is required", family="NOTEBOOK_PROJECTION")
    pack_sha = str(pack.get("packSha256") or "").casefold()
    if not _HEX64.fullmatch(pack_sha):
        raise WolframCloudNotebookError("partner pack SHA-256 is invalid", family="NOTEBOOK_PROJECTION")
    assert_partner_safe(pack)
    body: dict[str, Any] = {
        "schemaVersion": NOTEBOOK_PROJECTION_SCHEMA_VERSION,
        "title": "Sovereign — Wolfram CAG Partner Analysis",
        "sourcePackSha256": pack_sha,
        "cagContractVersion": pack.get("cagContractVersion"),
        "recordCount": int(pack.get("recordCount") or 0),
        "summary": dict(pack.get("summary") or {}),
        "analyses": list(pack.get("analyses") or []),
        "quotaObservations": list(pack.get("quotaObservations") or []),
        "limits": list(pack.get("limits") or []),
        "unresolvedQuestions": list(pack.get("unresolvedQuestions") or []),
        "evidencePassportRefs": list(pack.get("evidencePassportRefs") or []),
        "hfPublications": list(pack.get("hfPublications") or []),
        "researchBoundary": {
            "onlineResearch": "Use primary-source/search evidence for historical and attribution claims; Wolfram is supplemental computational evidence.",
            "bitcoinReadback": "Read-only Wolfram BlockchainData/BlockchainBlockData/BlockchainTransactionData evidence may support transaction and chain-state claims.",
            "identityNotice": "Blockchain transaction history alone cannot identify Satoshi Nakamoto; identity attribution remains a separate evidence class.",
        },
        "truthNotice": (
            "This private notebook is a deterministic review projection. It does not become a truth store, "
            "does not expose raw provider payloads, and does not make publication rights claims."
        ),
    }
    projection_sha = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    projection = {**body, "notebookProjectionSha256": projection_sha}
    assert_partner_safe(projection)
    return projection


def build_wolfram_notebook_expression(projection: Mapping[str, Any], *, wl_factory: Any | None = None) -> Any:
    """Create a data-only Notebook expression without evaluating user-controlled Wolfram code."""
    assert_partner_safe(projection)
    if projection.get("schemaVersion") != NOTEBOOK_PROJECTION_SCHEMA_VERSION:
        raise WolframCloudNotebookError("notebook projection schema mismatch", family="NOTEBOOK_PROJECTION")
    if wl_factory is None:
        from wolframclient.language import wl as wl_factory  # type: ignore

    cells: list[Any] = [
        wl_factory.Cell(str(projection["title"]), "Title"),
        wl_factory.Cell(f"Source pack SHA-256: {projection['sourcePackSha256']}", "Text"),
        wl_factory.Cell(f"Notebook projection SHA-256: {projection['notebookProjectionSha256']}", "Text"),
        wl_factory.Cell("Truth boundary", "Section"),
        wl_factory.Cell(json.dumps(projection["researchBoundary"], sort_keys=True, ensure_ascii=False, indent=2), "Text"),
        wl_factory.Cell("Summary", "Section"),
        wl_factory.Cell(json.dumps(projection["summary"], sort_keys=True, ensure_ascii=False, indent=2), "Text"),
    ]
    for analysis in projection.get("analyses") or []:
        analysis_id = str(analysis.get("analysisId") or analysis.get("analysisRecordSha256") or "analysis")
        cells.append(wl_factory.Cell(analysis_id, "Subsection"))
        cells.append(wl_factory.Cell(json.dumps(analysis, sort_keys=True, ensure_ascii=False, indent=2), "Text"))
    cells.extend([
        wl_factory.Cell("Canonical projection", "Section"),
        wl_factory.Cell(_canonical_json(dict(projection)), "Program"),
        wl_factory.Cell(str(projection["truthNotice"]), "Text"),
    ])
    return wl_factory.Notebook(cells)


def _hash_string(value: Any, *, label: str) -> str:
    if isinstance(value, bytes):
        value = value.decode("ascii", errors="strict")
    text = str(value or "").strip().strip('"').casefold()
    if not _HEX64.fullmatch(text):
        raise WolframCloudNotebookError(f"{label} did not return a SHA-256 hex string", family="CLOUD_READBACK")
    return text


def _program_cell_readback_hash_expression(target: Any, *, wl_factory: Any) -> Any:
    text_symbol = wl_factory.sovereignProjectionText
    program_pattern = wl_factory.Cell(
        wl_factory.Pattern(text_symbol, wl_factory.Blank(wl_factory.String)),
        "Program",
        wl_factory.BlankNullSequence(),
    )
    extracted = wl_factory.First(
        wl_factory.Cases(
            wl_factory.CloudGet(target),
            wl_factory.RuleDelayed(program_pattern, text_symbol),
            wl_factory.Infinity,
        )
    )
    return wl_factory.Hash(extracted, "SHA256", "HexString")


def sync_partner_notebook(
    pack: Mapping[str, Any],
    *,
    session_factory: Any | None = None,
    credentials_factory: Any | None = None,
    wl_factory: Any | None = None,
) -> dict[str, Any]:
    """Deploy one fixed private notebook and verify canonical-cell + permission readback."""
    projection = build_partner_notebook_projection(pack)
    notebook_path = _selected_notebook_path()
    consumer_key, consumer_secret = _cloud_credentials()

    if wl_factory is None:
        from wolframclient.language import wl as wl_factory  # type: ignore
    if credentials_factory is None or session_factory is None:
        from wolframclient.evaluation import SecuredAuthenticationKey, WolframCloudSession  # type: ignore
        credentials_factory = credentials_factory or SecuredAuthenticationKey
        session_factory = session_factory or (lambda credentials: WolframCloudSession(credentials=credentials))

    credentials = credentials_factory(consumer_key, consumer_secret)
    session = session_factory(credentials)
    started = False
    try:
        session.start()
        started = True
        authorized = session.authorized() if callable(getattr(session, "authorized", None)) else bool(getattr(session, "authorized", False))
        if not authorized:
            raise WolframCloudNotebookError("Wolfram Cloud session is not authorized", family="CLOUD_AUTH")

        notebook = build_wolfram_notebook_expression(projection, wl_factory=wl_factory)
        canonical_projection = _canonical_json(dict(projection))
        expected_hash = hashlib.sha256(canonical_projection.encode("utf-8")).hexdigest()
        target = wl_factory.CloudObject(notebook_path)
        session.evaluate(
            wl_factory.CloudDeploy(
                notebook,
                target,
                wl_factory.Rule(wl_factory.Permissions, "Private"),
            )
        )
        observed_hash = _hash_string(
            session.evaluate(_program_cell_readback_hash_expression(target, wl_factory=wl_factory)),
            label="cloud canonical projection readback hash",
        )
        permissions_private = session.evaluate(
            wl_factory.MemberQ(
                wl_factory.Options(target, wl_factory.Permissions),
                wl_factory.Rule(wl_factory.Permissions, "Private"),
            )
        )
        if observed_hash != expected_hash:
            raise WolframCloudNotebookError("Wolfram Cloud canonical projection hash mismatch", family="CLOUD_READBACK")
        if permissions_private is not True:
            raise WolframCloudNotebookError("Wolfram Cloud notebook is not private on readback", family="CLOUD_PERMISSIONS")
        return {
            "ok": True,
            "status": "WOLFRAM_CLOUD_NOTEBOOK_SYNC_VERIFIED",
            "targetPath": notebook_path,
            "sourcePackSha256": projection["sourcePackSha256"],
            "notebookProjectionSha256": projection["notebookProjectionSha256"],
            "canonicalProjectionCellSha256": expected_hash,
            "cloudReadbackSha256": observed_hash,
            "permissions": "Private",
            "permissionsReadbackVerified": True,
            "authenticated": True,
            "syncExecuted": True,
            "secretValuesReturned": False,
            "truthNotice": "Notebook sync is verified only for the canonical projection cell and private permission readback; it does not verify the claims contained in the notebook.",
        }
    finally:
        if started:
            terminator = getattr(session, "terminate", None) or getattr(session, "stop", None)
            if callable(terminator):
                terminator()


__all__ = [
    "DEFAULT_WOLFRAM_PARTNER_NOTEBOOK_PATH",
    "NOTEBOOK_PROJECTION_SCHEMA_VERSION",
    "WolframCloudNotebookError",
    "build_partner_notebook_projection",
    "build_wolfram_notebook_expression",
    "sync_partner_notebook",
    "wolfram_cloud_notebook_status",
]
