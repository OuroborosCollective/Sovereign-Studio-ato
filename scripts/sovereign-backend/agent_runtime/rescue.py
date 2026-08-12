"""Sovereign Rescue product contracts and persisted repair-pack boundary.

Free diagnosis is deterministic, revision-bound and repository read-only.
Paid repair is authorized and reserved server-side before the existing
free-single-agent workspace executor is allowed to mutate an isolated clone.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import time
from typing import Any, Mapping
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import uuid

from paid_execution_entitlement import (
    PaidExecutionEntitlement,
    resolve_paid_execution_entitlement,
)

from .mutation_evidence_layer import (
    build_mutation_proof_envelope,
    evaluate_mutation_evidence,
)
from .proof_verdict import ProofObservation, ProofVerdict


RESCUE_SCHEMA_VERSION = "sovereign.rescue.v1"
REPAIR_PACK_ID = "rescue-repair-pack-v1"
REPAIR_PACK_CREDITS = 10
MAX_EVIDENCE_CHARS = 120_000
MAX_AFFECTED_FILES = 20
MAX_REPAIR_CHANGED_FILES = 12
RESCUE_CSRF_TTL_SECONDS = 600

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")
_FILE_PATH = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:\.github/workflows/|docker/|migrations?/|src/|backend/|scripts/)"
    r"[A-Za-z0-9_./@+-]{1,220}\.(?:ya?ml|json|toml|py|ts|tsx|js|sql|sh|env))"
)
_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{8,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{8,}", re.IGNORECASE),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.IGNORECASE),
    re.compile(
        r"(?i)\b((?:[a-z][a-z0-9]*_)+(?:token|password|passwd|secret|api[_-]?key))"
        r"(\s*[=:]\s*)([^\s,;]+)"
    ),
    re.compile(
        r"(?i)\b(token|password|passwd|secret|api[_-]?key)\b"
        r"(\s*[=:]\s*)([^\s,;]+)"
    ),
)


@dataclass(frozen=True, slots=True)
class RescueFailureFamily:
    code: str
    title: str
    patterns: tuple[str, ...]
    suggested_paths: tuple[str, ...]
    repair_proposal: str
    verification: tuple[str, ...]


FAILURE_FAMILIES: tuple[RescueFailureFamily, ...] = (
    RescueFailureFamily(
        code="github_actions_ci",
        title="GitHub Actions oder CI",
        patterns=(
            "github actions",
            "workflow",
            "job failed",
            "process completed with exit code",
            "actions/checkout",
            "runner",
            "ci failed",
        ),
        suggested_paths=(".github/workflows/",),
        repair_proposal=(
            "Den kleinsten revisionsgebundenen Workflow- oder Code-Fix anwenden, "
            "die fehlgeschlagene Prüfung erneut ausführen und den Draft-PR-Head "
            "gegen genau dieselbe CI-Auswertung binden."
        ),
        verification=(
            "targeted failed check passes",
            "required checks pass on the exact Draft PR head SHA",
        ),
    ),
    RescueFailureFamily(
        code="docker_compose_container",
        title="Docker Compose oder Container",
        patterns=(
            "docker compose",
            "docker-compose",
            "container exited",
            "unhealthy",
            "healthcheck",
            "manifest unknown",
            "no such image",
            "connection refused",
        ),
        suggested_paths=("compose.yml", "compose.yaml", "docker-compose.yml", "Dockerfile"),
        repair_proposal=(
            "Compose-, Image- oder Healthcheck-Vertrag minimal korrigieren, "
            "Konfiguration validieren und einen revisionsgebundenen Container-Canary "
            "ohne produktive Umschaltung ausführen."
        ),
        verification=(
            "docker compose config passes",
            "bounded container canary reaches its declared health state",
        ),
    ),
    RescueFailureFamily(
        code="postgresql_migration_schema",
        title="PostgreSQL Migration oder Schema",
        patterns=(
            "postgres",
            "sqlstate",
            "migration",
            "relation does not exist",
            "column does not exist",
            "violates check constraint",
            "duplicate column",
            "schema",
        ),
        suggested_paths=("migrations/", "backend/migrations/", "scripts/sovereign-backend/migrations/"),
        repair_proposal=(
            "Eine additive oder kompatible Migration mit Transaktions-Preview "
            "erstellen, historischen Schema-Drift berücksichtigen und den "
            "Rollback vor jeder produktiven Anwendung belegen."
        ),
        verification=(
            "migration preview completes inside a rollback transaction",
            "schema canary passes without a production write",
        ),
    ),
)

_FAMILY_BY_CODE = {family.code: family for family in FAILURE_FAMILIES}


def redact_secret_text(value: Any, limit: int = MAX_EVIDENCE_CHARS) -> str:
    """Bound text and remove common credentials without returning their values."""

    text = str(value or "")[: max(0, limit)]
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(r"\1\2[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def normalize_rescue_origin(value: Any) -> str:
    """Return one path-free browser origin suitable for CSRF binding."""

    parsed = urlparse(str(value or "").strip())
    if (
        parsed.scheme.lower() not in {"http", "https", "capacitor"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("A canonical Rescue request origin is required.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Rescue request origin port is invalid.") from exc
    host = parsed.hostname.lower()
    authority = f"[{host}]" if ":" in host else host
    if port is not None:
        authority = f"{authority}:{port}"
    return f"{parsed.scheme.lower()}://{authority}"


def issue_rescue_csrf_token(
    *,
    user_id: str,
    origin: Any,
    secret: Any,
    now: int | None = None,
) -> str:
    """Issue a bounded HMAC token without persisting session or secret material."""

    normalized_user = str(user_id or "").strip()
    normalized_origin = normalize_rescue_origin(origin)
    secret_bytes = str(secret or "").encode("utf-8")
    if not normalized_user:
        raise ValueError("Authenticated user id is required for Rescue CSRF.")
    if len(secret_bytes) < 32:
        raise RuntimeError("rescue_csrf_secret_unavailable")
    issued_at = int(time.time() if now is None else now)
    message = f"{normalized_user}\n{normalized_origin}\n{issued_at}".encode("utf-8")
    signature = hmac.new(secret_bytes, message, hashlib.sha256).hexdigest()
    return f"v1.{issued_at}.{signature}"


def verify_rescue_csrf_token(
    token: Any,
    *,
    user_id: str,
    origin: Any,
    secret: Any,
    now: int | None = None,
    ttl_seconds: int = RESCUE_CSRF_TTL_SECONDS,
) -> bool:
    """Verify token version, age, user and request-origin binding."""

    try:
        version, issued_text, supplied_signature = str(token or "").split(".", 2)
        if version != "v1" or not issued_text.isdigit():
            return False
        issued_at = int(issued_text)
        current = int(time.time() if now is None else now)
        if issued_at > current + 30 or current - issued_at > max(1, int(ttl_seconds)):
            return False
        normalized_user = str(user_id or "").strip()
        normalized_origin = normalize_rescue_origin(origin)
        secret_bytes = str(secret or "").encode("utf-8")
        if not normalized_user or len(secret_bytes) < 32:
            return False
        message = f"{normalized_user}\n{normalized_origin}\n{issued_at}".encode("utf-8")
        expected = hmac.new(secret_bytes, message, hashlib.sha256).hexdigest()
        return bool(
            re.fullmatch(r"[0-9a-f]{64}", supplied_signature)
            and hmac.compare_digest(supplied_signature, expected)
        )
    except (TypeError, ValueError):
        return False


def normalize_repair_changed_files(value: Any) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or value is None:
        return ()
    return tuple(dict.fromkeys(
        str(item)
        for item in value
        if isinstance(item, str) and str(item).strip()
    ))


def repair_changed_file_limit_blocker(value: Any) -> str | None:
    count = len(normalize_repair_changed_files(value))
    if count <= MAX_REPAIR_CHANGED_FILES:
        return None
    return f"changed_file_limit_exceeded:{count}>{MAX_REPAIR_CHANGED_FILES}"


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_head_sha(value: Any) -> str:
    sha = str(value or "").strip().lower()
    if not _SHA40.fullmatch(sha):
        raise ValueError("A verified 40-character Git commit SHA is required.")
    return sha


def normalize_branch(value: Any) -> str:
    branch = str(value or "main").strip()
    if (
        not _SAFE_BRANCH.fullmatch(branch)
        or ".." in branch
        or "//" in branch
        or branch.endswith("/")
    ):
        raise ValueError("Branch is invalid.")
    return branch


def github_owner_repo(repository: Any) -> tuple[str, str]:
    parsed = urlparse(str(repository or "").strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("Repository must be a canonical GitHub HTTPS URL.")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise ValueError("Repository must identify exactly one GitHub owner/repository.")
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", owner) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,100}",
        repo,
    ):
        raise ValueError("Repository owner or name is invalid.")
    return owner, repo


def _github_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "sovereign-rescue-runtime",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def resolve_github_head(
    repository: Any,
    branch: Any,
    *,
    token: str | None = None,
    opener=urlopen,
) -> dict[str, Any]:
    """Resolve one branch to an exact GitHub revision without mutating the repo."""

    owner, repo = github_owner_repo(repository)
    safe_branch = normalize_branch(branch)
    request = Request(
        "https://api.github.com/repos/"
        f"{quote(owner, safe='')}/{quote(repo, safe='')}/commits/"
        f"{quote(safe_branch, safe='')}",
        method="GET",
        headers=_github_headers(token),
    )
    with opener(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    sha = normalize_head_sha(body.get("sha") if isinstance(body, dict) else "")
    return {
        "repository": f"https://github.com/{owner}/{repo}",
        "baseBranch": safe_branch,
        "baseSha": sha,
        "resolvedBy": "github-rest-commit",
        "mutationPerformed": False,
    }


def read_github_pr_evidence(
    pr_url: Any,
    *,
    token: str | None = None,
    opener=urlopen,
) -> dict[str, Any]:
    """Read PR head and check-runs; absent or pending checks remain non-green."""

    parsed = urlparse(str(pr_url or "").strip())
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or len(parts) != 4
        or parts[2] != "pull"
        or not parts[3].isdigit()
    ):
        raise ValueError("A canonical GitHub pull request URL is required.")
    owner, repo, _, number = parts
    pr_request = Request(
        f"https://api.github.com/repos/{quote(owner, safe='')}/"
        f"{quote(repo, safe='')}/pulls/{number}",
        method="GET",
        headers=_github_headers(token),
    )
    with opener(pr_request, timeout=30) as response:
        pr_body = json.loads(response.read().decode("utf-8"))
    head = pr_body.get("head") if isinstance(pr_body, dict) else {}
    head_sha = normalize_head_sha(head.get("sha") if isinstance(head, dict) else "")
    check_request = Request(
        f"https://api.github.com/repos/{quote(owner, safe='')}/"
        f"{quote(repo, safe='')}/commits/{head_sha}/check-runs?per_page=100",
        method="GET",
        headers=_github_headers(token),
    )
    with opener(check_request, timeout=30) as response:
        check_body = json.loads(response.read().decode("utf-8"))
    raw_runs = check_body.get("check_runs") if isinstance(check_body, dict) else []
    checks = [
        {
            "name": redact_secret_text(item.get("name"), 160),
            "status": str(item.get("status") or ""),
            "conclusion": str(item.get("conclusion") or ""),
            "headSha": str(item.get("head_sha") or "").lower(),
        }
        for item in raw_runs
        if isinstance(item, dict)
    ][:100]
    complete = bool(checks) and all(item["status"] == "completed" for item in checks)
    green = complete and all(
        item["conclusion"] in {"success", "neutral", "skipped"}
        for item in checks
    )
    head_match = bool(checks) and all(item["headSha"] == head_sha for item in checks)
    return {
        "url": f"https://github.com/{owner}/{repo}/pull/{number}",
        "headSha": head_sha,
        "draft": pr_body.get("draft") is True if isinstance(pr_body, dict) else False,
        "ciHeadShaMatch": head_match,
        "ciGreen": green and head_match,
        "checks": checks,
        "mutationPerformed": False,
    }


def _family_score(text: str, family: RescueFailureFamily) -> int:
    lowered = text.lower()
    return sum(3 if len(pattern) >= 12 else 1 for pattern in family.patterns if pattern in lowered)


def classify_failure_family(
    evidence_text: Any,
    *,
    requested_family: str = "",
) -> tuple[RescueFailureFamily | None, tuple[dict[str, Any], ...]]:
    evidence = redact_secret_text(evidence_text)
    requested = str(requested_family or "").strip().lower()
    scores = tuple(
        {
            "code": family.code,
            "score": _family_score(evidence, family),
        }
        for family in FAILURE_FAMILIES
    )
    if requested:
        return _FAMILY_BY_CODE.get(requested), scores
    ranked = sorted(scores, key=lambda item: (-int(item["score"]), str(item["code"])))
    if not ranked or int(ranked[0]["score"]) <= 0:
        return None, scores
    return _FAMILY_BY_CODE[str(ranked[0]["code"])], scores


def affected_files(evidence_text: Any, family: RescueFailureFamily) -> tuple[str, ...]:
    evidence = redact_secret_text(evidence_text)
    found = list(dict.fromkeys(match.group(1) for match in _FILE_PATH.finditer(evidence)))
    if not found:
        found.extend(family.suggested_paths)
    return tuple(found[:MAX_AFFECTED_FILES])


def build_outcome_contract(diagnosis: Mapping[str, Any]) -> dict[str, Any]:
    family_code = str(diagnosis.get("failureFamily") or "")
    family = _FAMILY_BY_CODE.get(family_code)
    if not family:
        raise ValueError("A supported Rescue failure family is required.")
    base_sha = normalize_head_sha(diagnosis.get("baseSha"))
    contract = {
        "schemaVersion": "sovereign.outcome-contract.v1",
        "product": "sovereign-rescue",
        "repository": str(diagnosis.get("repository") or ""),
        "baseBranch": normalize_branch(diagnosis.get("baseBranch")),
        "baseSha": base_sha,
        "failureFamily": family.code,
        "repairPack": {
            "id": REPAIR_PACK_ID,
            "credits": REPAIR_PACK_CREDITS,
            "maxChangedFiles": MAX_REPAIR_CHANGED_FILES,
            "maxRepairAttempts": 3,
            "draftPrOnly": True,
            "autoMerge": False,
        },
        "successConditions": [
            "changed-file and diff evidence are present",
            "targeted tests pass",
            *family.verification,
            "Draft PR head SHA and CI evidence refer to the same revision",
            "ProofPack verifies without secret material",
        ],
        "stopConditions": [
            "repository head changed after diagnosis",
            "failure family leaves the supported v1 boundary",
            "a production migration, deployment, OAuth switch, or secret is required",
            "three repair attempts fail without a reclassified failure family",
        ],
        "rollback": {
            "strategy": "close the Draft PR or revert its isolated commit",
            "productionMutationIncluded": False,
        },
    }
    return {**contract, "contractSha256": canonical_sha256(contract)}


def build_free_diagnosis(
    *,
    repository: str,
    base_branch: str,
    base_sha: str,
    evidence_text: Any,
    requested_family: str = "",
) -> dict[str, Any]:
    """Build a deterministic free report without a repository mutation."""

    verified_sha = normalize_head_sha(base_sha)
    branch = normalize_branch(base_branch)
    evidence = redact_secret_text(evidence_text)
    family, scores = classify_failure_family(
        evidence,
        requested_family=requested_family,
    )
    if not family:
        return {
            "schemaVersion": RESCUE_SCHEMA_VERSION,
            "ok": False,
            "supported": False,
            "mutationPerformed": False,
            "repository": repository,
            "baseBranch": branch,
            "baseSha": verified_sha,
            "evidenceSha256": hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
            "familyScores": list(scores),
            "blocker": "unsupported_failure_family",
            "message": (
                "Rescue v1 supports only GitHub Actions/CI, Docker Compose/container, "
                "and PostgreSQL migration/schema failures."
            ),
        }
    risk = "high" if family.code == "postgresql_migration_schema" else "medium"
    report = {
        "schemaVersion": RESCUE_SCHEMA_VERSION,
        "ok": True,
        "supported": True,
        "mutationPerformed": False,
        "repository": repository,
        "baseBranch": branch,
        "baseSha": verified_sha,
        "failureFamily": family.code,
        "failureFamilyTitle": family.title,
        "riskClass": risk,
        "affectedFiles": list(affected_files(evidence, family)),
        "repairProposal": family.repair_proposal,
        "verificationPlan": list(family.verification),
        "evidenceSha256": hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
        "familyScores": list(scores),
        "secretValuesReturned": False,
    }
    return {**report, "outcomeContract": build_outcome_contract(report)}


def resolve_account_entitlement(row: Mapping[str, Any]) -> PaidExecutionEntitlement:
    return resolve_paid_execution_entitlement(
        account_id=str(row.get("id") or ""),
        email=str(row.get("email") or ""),
        role=str(row.get("role") or ""),
        purchase_verified=bool(row.get("paid_purchase_verified")),
        credit_balance=int(row.get("credits") or 0),
        configured_owner_id=str(row.get("configured_owner_id") or ""),
        configured_owner_email=str(row.get("configured_owner_email") or ""),
    )


def entitlement_payload(
    row: Mapping[str, Any],
    entitlement: PaidExecutionEntitlement,
) -> dict[str, Any]:
    credits = int(row.get("credits") or 0)
    funded = entitlement.verified and (entitlement.privileged or credits >= REPAIR_PACK_CREDITS)
    return {
        "schemaVersion": "sovereign.rescue-entitlement.v1",
        "entitled": bool(funded),
        "source": entitlement.source,
        "purchaseVerified": entitlement.purchase_verified,
        "privileged": entitlement.privileged,
        "availableCredits": credits,
        "requiredCredits": 0 if entitlement.privileged else REPAIR_PACK_CREDITS,
        "repairPackId": REPAIR_PACK_ID,
        "serverSideVerified": True,
        "checkout": {
            "required": not entitlement.verified,
            "surface": "existing-paywall-modal",
            "external": True,
        },
    }


def reserve_repair_pack(
    conn: Any,
    *,
    user_id: str,
    repair_id: str,
    job_id: str,
    idempotency_key: str,
    repository: str,
    base_branch: str,
    base_sha: str,
    failure_family: str,
    outcome_contract_sha256: str,
    configured_owner_id: str = "",
    configured_owner_email: str = "",
) -> dict[str, Any]:
    """Atomically reserve one bounded pack; duplicates never charge twice."""

    normalized_repair_id = str(uuid.UUID(str(repair_id)))
    normalized_idempotency = str(uuid.UUID(str(idempotency_key)))
    verified_sha = normalize_head_sha(base_sha)
    branch = normalize_branch(base_branch)
    if failure_family not in _FAMILY_BY_CODE:
        raise ValueError("Unsupported Rescue failure family.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(outcome_contract_sha256 or "")):
        raise ValueError("Outcome contract SHA-256 is required.")

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"sovereign-rescue:{user_id}",),
            )
            cur.execute(
                """SELECT repair_id::text, job_id, repository, base_sha,
                          failure_family, state, charged_credits, run_id
                   FROM sovereign_rescue_repairs
                   WHERE user_id = %s::uuid AND idempotency_key = %s::uuid
                   LIMIT 1""",
                (user_id, normalized_idempotency),
            )
            existing = cur.fetchone()
            if existing:
                if (
                    str(existing.get("repository") or "") != repository
                    or str(existing.get("base_sha") or "") != verified_sha
                    or str(existing.get("failure_family") or "") != failure_family
                ):
                    raise RuntimeError("rescue_idempotency_conflict")
                conn.rollback()
                return {
                    "ok": True,
                    "duplicate": True,
                    "repairId": str(existing["repair_id"]),
                    "jobId": str(existing["job_id"]),
                    "runId": existing.get("run_id"),
                    "state": str(existing["state"]),
                    "chargedCredits": 0,
                }

            cur.execute(
                """SELECT account.id::text AS id, account.email, account.role,
                          account.credits::integer AS credits,
                          EXISTS(
                            SELECT 1
                            FROM transactions AS tx
                            JOIN credit_receipts AS receipt
                              ON receipt.user_id = tx.user_id
                             AND receipt.provider = tx.provider
                             AND receipt.provider_tx_id = tx.provider_tx_id
                            WHERE tx.user_id = account.id
                              AND tx.type = 'credit_purchase'
                              AND tx.status = 'completed'
                          ) AS paid_purchase_verified
                   FROM admin_users AS account
                   WHERE account.id = %s::uuid
                   FOR UPDATE""",
                (user_id,),
            )
            account = cur.fetchone()
            if not account:
                raise LookupError("Authenticated account not found.")
            account = dict(account)
            account["configured_owner_id"] = configured_owner_id
            account["configured_owner_email"] = configured_owner_email
            entitlement = resolve_account_entitlement(account)
            if not entitlement.verified:
                raise PermissionError("verified_purchase_required")
            charged = 0 if entitlement.privileged else REPAIR_PACK_CREDITS
            available = int(account.get("credits") or 0)
            if charged and available < charged:
                raise PermissionError("insufficient_rescue_credits")
            if charged:
                cur.execute(
                    """UPDATE admin_users
                       SET credits = credits - %s
                       WHERE id = %s::uuid AND credits >= %s
                       RETURNING credits""",
                    (charged, user_id, charged),
                )
                if not cur.fetchone():
                    raise RuntimeError("rescue_credit_settlement_race")
                cur.execute(
                    """INSERT INTO credit_ledger
                           (user_id, type, amount, reason, provider, provider_tx_id)
                       VALUES (%s::uuid, 'usage', %s, %s, 'sovereign-rescue', %s)""",
                    (
                        user_id,
                        -charged,
                        f"Sovereign Rescue Repair Pack: {normalized_repair_id}",
                        f"rescue-pack:{normalized_repair_id}",
                    ),
                )
            cur.execute(
                """INSERT INTO sovereign_rescue_repairs
                       (repair_id, user_id, job_id, idempotency_key, repository,
                        base_branch, base_sha, failure_family, repair_pack_id,
                        outcome_contract_sha256, entitlement_source,
                        charged_credits, state)
                   VALUES (%s::uuid, %s::uuid, %s, %s::uuid, %s, %s, %s, %s,
                           %s, %s, %s, %s, 'reserved')""",
                (
                    normalized_repair_id,
                    user_id,
                    job_id,
                    normalized_idempotency,
                    repository,
                    branch,
                    verified_sha,
                    failure_family,
                    REPAIR_PACK_ID,
                    outcome_contract_sha256,
                    entitlement.source,
                    charged,
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "ok": True,
        "duplicate": False,
        "repairId": normalized_repair_id,
        "jobId": job_id,
        "state": "reserved",
        "chargedCredits": charged,
        "entitlementSource": entitlement.source,
    }


def update_repair_execution(
    conn: Any,
    *,
    user_id: str,
    repair_id: str,
    run_id: str | None,
    job_id: str | None,
    state: str,
    blocker: str = "",
) -> None:
    allowed = {"reserved", "running", "blocked", "draft_pr_ready", "completed", "cancelled"}
    if state not in allowed:
        raise ValueError("Invalid Rescue repair state.")
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE sovereign_rescue_repairs
               SET run_id = COALESCE(%s, run_id),
                   job_id = COALESCE(%s, job_id),
                   state = %s,
                   blocker = NULLIF(%s, ''),
                   updated_at = NOW()
               WHERE repair_id = %s::uuid AND user_id = %s::uuid""",
            (run_id, job_id, state, redact_secret_text(blocker, 1200), repair_id, user_id),
        )
    conn.commit()


def build_proof_pack(
    *,
    repair: Mapping[str, Any],
    job: Mapping[str, Any],
    pr_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a verifiable pack; missing evidence stays explicit and blocks ready."""

    pr = dict(pr_evidence or {})
    repository = str(repair.get("repository") or "")
    base_sha = normalize_head_sha(repair.get("base_sha") or repair.get("baseSha"))
    head_sha = str(pr.get("headSha") or "").lower()
    changed_files = list(normalize_repair_changed_files(
        job.get("changed_files") or job.get("changedFiles") or []
    ))
    test_summary = redact_secret_text(
        job.get("test_summary") or job.get("testSummary") or "",
        4000,
    )
    pr_url = str(job.get("draft_pr_url") or job.get("draftPrUrl") or pr.get("url") or "")
    published_head_sha = str(
        repair.get("published_head_sha") or repair.get("publishedHeadSha") or ""
    ).strip().lower()
    outcome_contract_sha256 = str(repair.get("outcome_contract_sha256") or "")
    repair_id = str(repair.get("repair_id") or repair.get("repairId") or "")

    blockers: list[str] = []
    changed_file_blocker = repair_changed_file_limit_blocker(changed_files)
    if not changed_files:
        blockers.append("changed_file_evidence_missing")
    if changed_file_blocker:
        blockers.append(changed_file_blocker)
    if not test_summary:
        blockers.append("test_evidence_missing")
    if "[REDACTED]" in test_summary:
        blockers.append("secret_material_redacted")
    if not pr_url.startswith("https://github.com/") or "/pull/" not in pr_url:
        blockers.append("draft_pr_evidence_missing")
    if not _SHA40.fullmatch(head_sha):
        blockers.append("draft_pr_head_sha_missing")
    if not _SHA40.fullmatch(published_head_sha):
        blockers.append("published_head_sha_missing")
    elif head_sha and head_sha != published_head_sha:
        blockers.append("draft_pr_head_changed_after_publication")
    if pr.get("ciHeadShaMatch") is not True:
        blockers.append("ci_head_sha_not_bound")
    if pr.get("ciGreen") is not True:
        blockers.append("ci_not_green")

    # Issue #1100: callers must supply independent receipts. This function never
    # manufactures receipt hashes from descriptive inputs, test summaries, or IDs.
    diff_sha256 = hashlib.sha256(json.dumps(changed_files, sort_keys=True).encode("utf-8")).hexdigest()
    envelope = build_mutation_proof_envelope(
        operation_family="sovereign_rescue_repair",
        operation_identity=repair_id,
        repository=repository,
        revision=base_sha,
        input_sha256=outcome_contract_sha256,
        diff_sha256=diff_sha256,
    )

    def receipt_sha256(value: Any) -> str:
        candidate = str(value or "").strip().lower()
        return candidate if _SHA256.fullmatch(candidate) else ""

    def observation(
        requirement_id: str,
        evidence_kind: str,
        source_kind: str,
        assertion: str,
        evidence_sha256: str,
    ) -> ProofObservation:
        return ProofObservation(
            observation_id=f"{requirement_id}-{repair_id}",
            requirement_id=requirement_id,
            evidence_kind=evidence_kind,
            source_kind=source_kind,
            assertion=assertion,
            operation_family="sovereign_rescue_repair",
            operation_identity=repair_id,
            revision=base_sha,
            input_sha256=outcome_contract_sha256,
            diff_sha256=diff_sha256,
            evidence_sha256=evidence_sha256 or "0" * 64,
        )

    authorization_sha = receipt_sha256(repair.get("authorization_receipt_sha256"))
    diagnostic_sha = receipt_sha256(repair.get("diagnostic_evidence_sha256"))
    agent_run_sha = receipt_sha256(job.get("agent_run_receipt_sha256"))
    changed_path_sha = receipt_sha256(pr.get("changedPathSha256") or pr.get("changed_path_sha256"))
    ci_sha = receipt_sha256(pr.get("ciReadbackSha256") or pr.get("ci_readback_sha256"))
    github_readback_sha = receipt_sha256(pr.get("githubReadbackSha256") or pr.get("github_readback_sha256"))
    capability_delta_sha = receipt_sha256(pr.get("capabilityDeltaSha256") or pr.get("capability_delta_sha256"))

    if not authorization_sha:
        blockers.append("owner_authorization_receipt_missing")
    if not diagnostic_sha:
        blockers.append("diagnostic_baseline_receipt_missing")
    if not agent_run_sha:
        blockers.append("agent_run_receipt_missing")
    if changed_path_sha != diff_sha256:
        blockers.append("changed_path_readback_missing_or_mismatched")
    if not ci_sha:
        blockers.append("ci_readback_receipt_missing")
    if not github_readback_sha:
        blockers.append("github_readback_receipt_missing")
    if not capability_delta_sha or pr.get("capabilityDeltaVerified") is not True:
        blockers.append("capability_delta_receipt_missing_or_unverified")

    ci_assertion = (
        "OBSERVED" if ci_sha and pr.get("ciGreen") is True and pr.get("ciHeadShaMatch") is True
        else "CONTRADICTED" if pr.get("ciGreen") is False or pr.get("ciHeadShaMatch") is False
        else "UNAVAILABLE"
    )
    readback_assertion = (
        "OBSERVED" if github_readback_sha and head_sha and head_sha == published_head_sha
        else "CONTRADICTED" if head_sha and published_head_sha and head_sha != published_head_sha
        else "UNAVAILABLE"
    )
    observations = [
        observation(
            "owner_authorization", "owner_authorization", "AGENT_RUN_RECEIPT",
            "OBSERVED" if authorization_sha else "UNAVAILABLE", authorization_sha,
        ),
        observation(
            "diagnostic_baseline", "diagnostic_baseline", "AGENT_RUN_RECEIPT",
            "OBSERVED" if diagnostic_sha else "UNAVAILABLE", diagnostic_sha,
        ),
        observation(
            "agent_run_receipt", "agent_run_receipt", "AGENT_RUN_RECEIPT",
            "OBSERVED" if agent_run_sha else "UNAVAILABLE", agent_run_sha,
        ),
        observation(
            "input_diff_identity", "input_diff_identity", "REPOSITORY_READBACK",
            "OBSERVED" if changed_path_sha == diff_sha256 else "UNAVAILABLE", changed_path_sha,
        ),
        observation("exact_head_ci", "exact_head_ci", "CI_READBACK", ci_assertion, ci_sha),
        observation("repair_readback", "repair_readback", "REPOSITORY_READBACK", readback_assertion, github_readback_sha),
        observation(
            "capability_delta", "capability_delta", "REPOSITORY_READBACK",
            "OBSERVED" if capability_delta_sha and pr.get("capabilityDeltaVerified") is True else "UNAVAILABLE",
            capability_delta_sha,
        ),
    ]

    verdict = evaluate_mutation_evidence(envelope, observations)
    if verdict.status != "VERIFIED":
        blockers.append(f"mutation_evidence_unverified: {verdict.status}")
        for req in verdict.missing_requirements:
            blockers.append(f"missing_evidence: {req}")
        for req in verdict.contradictory_requirements:
            blockers.append(f"contradictory_evidence: {req}")

    payload = {
        "schemaVersion": "sovereign.proof-pack.v1",
        "product": "sovereign-rescue",
        "repairId": repair_id,
        "repository": repository,
        "failureFamily": str(repair.get("failure_family") or repair.get("failureFamily") or ""),
        "baseSha": base_sha,
        "headSha": head_sha or None,
        "publishedHeadSha": published_head_sha or None,
        "draftPrUrl": pr_url or None,
        "changedFiles": changed_files,
        "changedFileCount": len(changed_files),
        "maxChangedFiles": MAX_REPAIR_CHANGED_FILES,
        "testSummary": test_summary or None,
        "ci": {
            "headShaMatch": pr.get("ciHeadShaMatch") is True,
            "green": pr.get("ciGreen") is True,
            "checks": pr.get("checks") if isinstance(pr.get("checks"), list) else [],
        },
        "mutationEvidence": {
            "envelope": envelope.canonical_body(),
            "verdict": {
                "status": verdict.status,
                "satisfied": list(verdict.satisfied_requirements),
                "missing": list(verdict.missing_requirements),
                "contradictory": list(verdict.contradictory_requirements),
                "findings": list(verdict.finding_codes),
            },
        },
        "rollback": {
            "strategy": "close the Draft PR or revert its isolated commit",
            "productionMutationIncluded": False,
        },
        "blockers": blockers,
        "ready": not blockers,
        "secretValuesReturned": False,
    }
    return {**payload, "proofSha256": canonical_sha256(payload)}


def verify_proof_pack(pack: Mapping[str, Any]) -> bool:
    proof_sha = str(pack.get("proofSha256") or "")
    payload = {key: value for key, value in pack.items() if key != "proofSha256"}

    mutation_evidence = pack.get("mutationEvidence") or {}
    verdict = mutation_evidence.get("verdict") or {}

    return bool(
        pack.get("ready") is True
        and not pack.get("blockers")
        and verdict.get("status") == "VERIFIED"
        and _SHA40.fullmatch(str(pack.get("baseSha") or ""))
        and _SHA40.fullmatch(str(pack.get("headSha") or ""))
        and _SHA40.fullmatch(str(pack.get("publishedHeadSha") or ""))
        and str(pack.get("headSha") or "") == str(pack.get("publishedHeadSha") or "")
        and len(normalize_repair_changed_files(pack.get("changedFiles"))) <= MAX_REPAIR_CHANGED_FILES
        and proof_sha == canonical_sha256(payload)
        and "[REDACTED]" not in json.dumps(pack)
    )


def public_repair_row(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "repair_id",
        "job_id",
        "run_id",
        "repository",
        "base_branch",
        "base_sha",
        "failure_family",
        "repair_pack_id",
        "outcome_contract_sha256",
        "entitlement_source",
        "charged_credits",
        "published_head_sha",
        "state",
        "blocker",
        "created_at",
        "updated_at",
    )
    payload = {key: row.get(key) for key in keys}
    return {
        "repairId": str(payload["repair_id"] or ""),
        "jobId": str(payload["job_id"] or ""),
        "runId": str(payload["run_id"] or "") or None,
        "repository": str(payload["repository"] or ""),
        "baseBranch": str(payload["base_branch"] or ""),
        "baseSha": str(payload["base_sha"] or ""),
        "failureFamily": str(payload["failure_family"] or ""),
        "repairPackId": str(payload["repair_pack_id"] or ""),
        "outcomeContractSha256": str(payload["outcome_contract_sha256"] or ""),
        "entitlementSource": str(payload["entitlement_source"] or ""),
        "chargedCredits": int(payload["charged_credits"] or 0),
        "publishedHeadSha": str(payload["published_head_sha"] or "") or None,
        "state": str(payload["state"] or ""),
        "blocker": redact_secret_text(payload["blocker"], 1200) or None,
        "createdAt": str(payload["created_at"] or ""),
        "updatedAt": str(payload["updated_at"] or ""),
    }
