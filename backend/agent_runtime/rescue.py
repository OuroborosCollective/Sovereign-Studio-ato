"""Sovereign Rescue product contracts and persisted repair-pack boundary.

Free diagnosis is deterministic, revision-bound and repository read-only.
Paid repair is authorized and reserved server-side before the existing
free-single-agent workspace executor is allowed to mutate an isolated clone.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import uuid

from paid_execution_entitlement import (
    PaidExecutionEntitlement,
    resolve_paid_execution_entitlement,
)


RESCUE_SCHEMA_VERSION = "sovereign.rescue.v1"
REPAIR_PACK_ID = "rescue-repair-pack-v1"
REPAIR_PACK_CREDITS = 10
MAX_EVIDENCE_CHARS = 120_000
MAX_AFFECTED_FILES = 20

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")
_FILE_PATH = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:(?:\.github/workflows/|docker/|migrations?/|src/|backend/|scripts/)"
    r"[A-Za-z0-9_./@+-]{1,220}\.(?:ya?ml|json|toml|py|ts|tsx|js|sql|sh|env))"
    r"|(?:docker-compose|compose)\.ya?ml|Dockerfile)"
)
_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{8,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{8,}", re.IGNORECASE),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.IGNORECASE),
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


def _github_json(url: str, *, token: str | None, opener: Any) -> Any:
    request = Request(url, method="GET", headers=_github_headers(token))
    with opener(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_github_affected_files(
    repository: Any,
    head_sha: Any,
    candidates: Any,
    *,
    token: str | None = None,
    opener=urlopen,
) -> tuple[str, ...]:
    """Return only candidate paths that exist at the exact diagnosed revision."""

    owner, repo = github_owner_repo(repository)
    verified_sha = normalize_head_sha(head_sha)
    verified: list[str] = []
    for item in list(candidates or [])[:MAX_AFFECTED_FILES]:
        path = str(item or "").strip()
        if (
            not path
            or path.startswith("/")
            or ".." in path.split("/")
            or not re.fullmatch(r"[A-Za-z0-9_./@+-]{1,240}", path)
        ):
            continue
        url = (
            f"https://api.github.com/repos/{quote(owner, safe='')}/"
            f"{quote(repo, safe='')}/contents/{quote(path, safe='/')}"
            f"?ref={verified_sha}"
        )
        try:
            body = _github_json(url, token=token, opener=opener)
        except HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        if (
            isinstance(body, dict)
            and body.get("type") in {"file", "symlink", "submodule"}
            and str(body.get("path") or "") == path
            and body.get("sha")
        ):
            verified.append(path)
    return tuple(dict.fromkeys(verified))


def _required_contexts(branch_body: Any, rules_body: Any) -> tuple[str, ...]:
    required: list[str] = []
    protection = branch_body.get("protection") if isinstance(branch_body, dict) else {}
    status_checks = (
        protection.get("required_status_checks")
        if isinstance(protection, dict)
        else {}
    )
    if isinstance(status_checks, dict):
        required.extend(str(item) for item in status_checks.get("contexts") or [] if item)
        required.extend(
            str(item.get("context") or "")
            for item in status_checks.get("checks") or []
            if isinstance(item, dict) and item.get("context")
        )
    for rule in rules_body if isinstance(rules_body, list) else []:
        if not isinstance(rule, dict) or rule.get("type") != "required_status_checks":
            continue
        parameters = rule.get("parameters") if isinstance(rule.get("parameters"), dict) else {}
        required.extend(
            str(item.get("context") or "")
            for item in parameters.get("required_status_checks") or []
            if isinstance(item, dict) and item.get("context")
        )
    return tuple(dict.fromkeys(item for item in required if item))


def read_github_pr_evidence(
    pr_url: Any,
    *,
    token: str | None = None,
    opener=urlopen,
) -> dict[str, Any]:
    """Read exact-head PR, required-check, CheckRun and legacy status evidence."""

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
    api_root = (
        f"https://api.github.com/repos/{quote(owner, safe='')}/"
        f"{quote(repo, safe='')}"
    )
    pr_body = _github_json(
        f"{api_root}/pulls/{number}",
        token=token,
        opener=opener,
    )
    head = pr_body.get("head") if isinstance(pr_body, dict) else {}
    base = pr_body.get("base") if isinstance(pr_body, dict) else {}
    head_sha = normalize_head_sha(head.get("sha") if isinstance(head, dict) else "")
    base_branch = normalize_branch(base.get("ref") if isinstance(base, dict) else "")
    check_body = _github_json(
        f"{api_root}/commits/{head_sha}/check-runs?per_page=100",
        token=token,
        opener=opener,
    )
    status_body = _github_json(
        f"{api_root}/commits/{head_sha}/status?per_page=100",
        token=token,
        opener=opener,
    )
    branch_body = _github_json(
        f"{api_root}/branches/{quote(base_branch, safe='')}",
        token=token,
        opener=opener,
    )
    rules_body = _github_json(
        f"{api_root}/rules/branches/{quote(base_branch, safe='')}",
        token=token,
        opener=opener,
    )

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
    raw_statuses = status_body.get("statuses") if isinstance(status_body, dict) else []
    statuses: list[dict[str, str]] = []
    seen_status_contexts: set[str] = set()
    for item in raw_statuses if isinstance(raw_statuses, list) else []:
        if not isinstance(item, dict):
            continue
        context = redact_secret_text(item.get("context"), 160)
        if not context or context in seen_status_contexts:
            continue
        seen_status_contexts.add(context)
        statuses.append({
            "context": context,
            "state": str(item.get("state") or ""),
        })
        if len(statuses) >= 100:
            break

    required = _required_contexts(branch_body, rules_body)
    check_by_name = {
        name: [item for item in checks if item["name"] == name]
        for name in required
    }
    status_by_context = {item["context"]: item for item in statuses}
    required_present = all(
        bool(check_by_name.get(name)) or name in status_by_context
        for name in required
    )
    required_green = required_present and all(
        (
            not check_by_name.get(name)
            or all(
                item["status"] == "completed"
                and item["conclusion"] in {"success", "neutral", "skipped"}
                for item in check_by_name[name]
            )
        )
        and (
            name not in status_by_context
            or status_by_context[name]["state"] == "success"
        )
        for name in required
    )
    observed = bool(checks or statuses)
    all_observed_green = observed and all(
        item["status"] == "completed"
        and item["conclusion"] in {"success", "neutral", "skipped"}
        for item in checks
    ) and all(item["state"] == "success" for item in statuses)
    head_match = observed and all(item["headSha"] == head_sha for item in checks)
    ci_green = head_match and (
        required_green if required else all_observed_green
    )
    return {
        "url": f"https://github.com/{owner}/{repo}/pull/{number}",
        "headSha": head_sha,
        "baseBranch": base_branch,
        "draft": pr_body.get("draft") is True if isinstance(pr_body, dict) else False,
        "ciHeadShaMatch": head_match,
        "ciGreen": ci_green,
        "requiredChecksKnown": True,
        "requiredChecksPresent": required_present,
        "requiredChecks": list(required),
        "checks": checks,
        "statuses": statuses,
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
    del family
    evidence = redact_secret_text(evidence_text)
    found = list(dict.fromkeys(match.group(1) for match in _FILE_PATH.finditer(evidence)))
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
            "maxChangedFiles": 12,
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
    verified_affected_files: Any = None,
) -> dict[str, Any]:
    """Build a deterministic free report without a repository mutation."""

    verified_sha = normalize_head_sha(base_sha)
    branch = normalize_branch(base_branch)
    evidence = redact_secret_text(evidence_text)
    family, scores = classify_failure_family(
        evidence,
        requested_family=requested_family,
    )
    common = {
        "schemaVersion": RESCUE_SCHEMA_VERSION,
        "mutationPerformed": False,
        "repository": repository,
        "baseBranch": branch,
        "baseSha": verified_sha,
        "evidenceSha256": hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
        "familyScores": list(scores),
        "secretValuesReturned": False,
    }
    if not family:
        return {
            **common,
            "ok": False,
            "supported": False,
            "blocker": "unsupported_failure_family",
            "message": (
                "Rescue v1 supports only GitHub Actions/CI, Docker Compose/container, "
                "and PostgreSQL migration/schema failures."
            ),
        }

    candidates = affected_files(evidence, family)
    selected_files = (
        candidates
        if verified_affected_files is None
        else tuple(
            item
            for item in dict.fromkeys(str(value) for value in verified_affected_files or [])
            if item in candidates
        )
    )
    if not selected_files:
        return {
            **common,
            "ok": False,
            "supported": True,
            "failureFamily": family.code,
            "failureFamilyTitle": family.title,
            "affectedFiles": [],
            "blocker": "repository_evidence_missing",
            "message": (
                "No affected file from the supplied failure evidence could be "
                "verified at the exact repository revision."
            ),
        }

    risk = "high" if family.code == "postgresql_migration_schema" else "medium"
    report = {
        **common,
        "ok": True,
        "supported": True,
        "failureFamily": family.code,
        "failureFamilyTitle": family.title,
        "riskClass": risk,
        "affectedFiles": list(selected_files),
        "repairProposal": family.repair_proposal,
        "verificationPlan": list(family.verification),
    }
    return {**report, "outcomeContract": build_outcome_contract(report)}


def resolve_account_entitlement(row: Mapping[str, Any]) -> PaidExecutionEntitlement:
    return resolve_paid_execution_entitlement(
        account_id=str(row.get("id") or ""),
        email=str(row.get("email") or ""),
        role=str(row.get("role") or ""),
        purchase_verified=bool(row.get("paid_purchase_verified")),
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
            "required": not funded,
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


def claim_repair_execution(
    conn: Any,
    *,
    user_id: str,
    repair_id: str,
) -> dict[str, Any]:
    """Atomically claim one reserved repair so retries cannot execute it twice."""

    with conn.cursor() as cur:
        cur.execute(
            """UPDATE sovereign_rescue_repairs AS repair
               SET state = 'running', blocker = NULL, updated_at = NOW()
               WHERE repair.repair_id = %s::uuid
                 AND repair.user_id = %s::uuid
                 AND (
                   repair.state = 'reserved'
                   OR (
                     repair.state = 'running'
                     AND repair.run_id IS NULL
                     AND repair.updated_at < NOW() - INTERVAL '2 minutes'
                     AND NOT EXISTS (
                       SELECT 1
                       FROM sovereign_agent_jobs AS job
                       WHERE job.job_id = repair.job_id
                         AND job.user_id = repair.user_id
                     )
                   )
                 )
               RETURNING repair_id::text, job_id, run_id, state, charged_credits""",
            (repair_id, user_id),
        )
        claimed = cur.fetchone()
        if claimed:
            conn.commit()
            return {"claimed": True, **dict(claimed)}
        cur.execute(
            """SELECT repair_id::text, job_id, run_id, state, charged_credits, blocker
               FROM sovereign_rescue_repairs
               WHERE repair_id = %s::uuid AND user_id = %s::uuid
               LIMIT 1""",
            (repair_id, user_id),
        )
        current = cur.fetchone()
    conn.rollback()
    return {"claimed": False, **(dict(current) if current else {"state": "missing"})}


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
    base_sha = normalize_head_sha(repair.get("base_sha") or repair.get("baseSha"))
    head_sha = str(pr.get("headSha") or "").lower()
    published_head_sha = str(
        repair.get("published_head_sha") or repair.get("publishedHeadSha") or ""
    ).lower()
    raw_changed_files = [
        str(item)
        for item in (job.get("changed_files") or job.get("changedFiles") or [])
        if isinstance(item, str)
    ]
    changed_files = raw_changed_files[:12]
    test_summary = redact_secret_text(
        job.get("test_summary") or job.get("testSummary") or "",
        4000,
    )
    pr_url = str(job.get("draft_pr_url") or job.get("draftPrUrl") or pr.get("url") or "")
    blockers: list[str] = []
    if not changed_files:
        blockers.append("changed_file_evidence_missing")
    if len(raw_changed_files) > 12:
        blockers.append("changed_file_limit_exceeded")
    if not test_summary:
        blockers.append("test_evidence_missing")
    if "[REDACTED]" in test_summary:
        blockers.append("secret_material_redacted")
    if not pr_url.startswith("https://github.com/") or "/pull/" not in pr_url:
        blockers.append("draft_pr_evidence_missing")
    if pr.get("draft") is not True:
        blockers.append("draft_pr_not_draft")
    if not _SHA40.fullmatch(head_sha):
        blockers.append("draft_pr_head_sha_missing")
    if not _SHA40.fullmatch(published_head_sha):
        blockers.append("published_head_sha_missing")
    elif head_sha != published_head_sha:
        blockers.append("published_head_sha_mismatch")
    if pr.get("ciHeadShaMatch") is not True:
        blockers.append("ci_head_sha_not_bound")
    if pr.get("requiredChecksKnown") is not True:
        blockers.append("required_checks_unverified")
    if pr.get("requiredChecksPresent") is not True:
        blockers.append("required_checks_missing")
    if pr.get("ciGreen") is not True:
        blockers.append("ci_not_green")

    payload = {
        "schemaVersion": "sovereign.proof-pack.v1",
        "product": "sovereign-rescue",
        "repairId": str(repair.get("repair_id") or repair.get("repairId") or ""),
        "repository": str(repair.get("repository") or ""),
        "failureFamily": str(repair.get("failure_family") or repair.get("failureFamily") or ""),
        "baseSha": base_sha,
        "headSha": head_sha or None,
        "publishedHeadSha": published_head_sha or None,
        "draftPr": pr.get("draft") is True,
        "draftPrUrl": pr_url or None,
        "changedFiles": changed_files,
        "testSummary": test_summary or None,
        "ci": {
            "headShaMatch": pr.get("ciHeadShaMatch") is True,
            "green": pr.get("ciGreen") is True,
            "requiredChecksKnown": pr.get("requiredChecksKnown") is True,
            "requiredChecksPresent": pr.get("requiredChecksPresent") is True,
            "requiredChecks": (
                pr.get("requiredChecks")
                if isinstance(pr.get("requiredChecks"), list)
                else []
            ),
            "checks": pr.get("checks") if isinstance(pr.get("checks"), list) else [],
            "statuses": pr.get("statuses") if isinstance(pr.get("statuses"), list) else [],
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
    return bool(
        pack.get("ready") is True
        and not pack.get("blockers")
        and _SHA40.fullmatch(str(pack.get("baseSha") or ""))
        and _SHA40.fullmatch(str(pack.get("headSha") or ""))
        and _SHA40.fullmatch(str(pack.get("publishedHeadSha") or ""))
        and pack.get("headSha") == pack.get("publishedHeadSha")
        and pack.get("draftPr") is True
        and isinstance(pack.get("ci"), Mapping)
        and pack["ci"].get("requiredChecksKnown") is True
        and pack["ci"].get("requiredChecksPresent") is True
        and pack["ci"].get("green") is True
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
        "published_head_sha",
        "failure_family",
        "repair_pack_id",
        "outcome_contract_sha256",
        "entitlement_source",
        "charged_credits",
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
        "publishedHeadSha": str(payload["published_head_sha"] or "") or None,
        "failureFamily": str(payload["failure_family"] or ""),
        "repairPackId": str(payload["repair_pack_id"] or ""),
        "outcomeContractSha256": str(payload["outcome_contract_sha256"] or ""),
        "entitlementSource": str(payload["entitlement_source"] or ""),
        "chargedCredits": int(payload["charged_credits"] or 0),
        "state": str(payload["state"] or ""),
        "blocker": redact_secret_text(payload["blocker"], 1200) or None,
        "createdAt": str(payload["created_at"] or ""),
        "updatedAt": str(payload["updated_at"] or ""),
    }
