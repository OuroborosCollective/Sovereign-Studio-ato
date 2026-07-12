"""Embedded, policy-guarded Sovereign Universal Toolchain runtime.

This module integrates the safe core of the supplied universal toolchain into the
existing Flask/PostgreSQL Sovereign runtime. It is intentionally read-only until
an existing Sovereign Agent job takes over. It never executes arbitrary shell,
never talks to GitHub directly, never deploys and never writes to main.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

TOOLCHAIN_VERSION = "2.0.0-embedded"
MAX_EVIDENCE_CHARS = 120_000
MAX_FAMILIES = 6
FOLLOWUP_LIMIT = 4
MAX_AUTO_REPAIR_ATTEMPTS = 2


@dataclass(frozen=True)
class FailureFamily:
    code: str
    title: str
    severity: str
    patterns: tuple[str, ...]
    followups: tuple[str, ...]
    checks: tuple[str, ...]


FAILURE_FAMILIES: tuple[FailureFamily, ...] = (
    FailureFamily(
        "dependency_runtime_missing",
        "Dependency or runtime installation is incomplete",
        "high",
        ("no module named", "module_not_found", "node_modules missing", "cannot find module", "flask", "corepack", "pnpm install"),
        (
            "The next test shard can fail on a different missing dependency even after the first import is repaired.",
            "CI and local runners can drift when they do not share one lockfile-backed setup path.",
            "A build can appear healthy while browser or Python integration tests still use another runtime.",
            "Cached dependencies can hide an undeclared package until a clean runner executes.",
        ),
        ("verify the shared setup action", "run the clean dependency canary", "run frozen-lockfile install", "run the exact failed test"),
    ),
    FailureFamily(
        "typescript_contract_mismatch",
        "TypeScript or frontend contract mismatch",
        "high",
        ("typecheck", "typescript", "ts2322", "ts2339", "cannot find name", "is not assignable", "property does not exist"),
        (
            "A corrected API type can still disagree with the runtime JSON shape.",
            "A component test can pass while the production Vite build imports a different code path.",
            "A newly optional field can still be dereferenced without a runtime fallback.",
            "Generated Android/WebView assets can remain stale after a successful web-only check.",
        ),
        ("run targeted typecheck", "run targeted Vitest", "run full Vite build", "verify copied Android assets"),
    ),
    FailureFamily(
        "playwright_runtime_missing",
        "Playwright browser or system runtime is missing",
        "medium",
        ("playwright", "browser executable", "chromium", "install --with-deps", "browser_type.launch"),
        (
            "UI regressions can remain invisible when unit tests pass without a real browser.",
            "The browser cache can belong to another Playwright version than the lockfile.",
            "Screenshots and traces can be absent, leaving a false green release signal.",
            "A WebView-specific failure can survive a desktop-only browser run.",
        ),
        ("verify Playwright version", "install matching browser", "run trace-enabled smoke", "run Android/WebView release audit"),
    ),
    FailureFamily(
        "github_access_or_scope",
        "GitHub access, repository scope or callback state is invalid",
        "high",
        ("github", "403", "401", "forbidden", "unauthorized", "oauth", "repo scope", "callback", "draft pr"),
        (
            "Login can succeed while repository read or pull-request permission remains missing.",
            "A callback can close successfully without updating the opener surface.",
            "The repository can change after validation, invalidating stored access evidence.",
            "Draft-PR creation can fail after code generation if head/base revisions are stale.",
        ),
        ("verify active repository identity", "verify callback state/origin", "verify repository permission", "re-read head SHA before Draft PR"),
    ),
    FailureFamily(
        "strict_patch_drift",
        "Strict SEARCH/REPLACE patch no longer matches",
        "medium",
        ("search must occur exactly once", "expected exactly 1 match", "search/replace", "stale sha", "match count"),
        (
            "The target file may have changed after preview and before write.",
            "A broad search anchor can match another nearby implementation after refactoring.",
            "A valid patch can target the wrong branch when repository scope changes.",
            "The final Draft PR can omit a related mirror file and create runtime drift.",
        ),
        ("re-read current SHA", "scope the exact anchor", "verify active branch", "compare runtime mirrors"),
    ),
    FailureFamily(
        "database_schema_contract",
        "Database migration or persisted schema contract is incompatible",
        "high",
        ("check constraint", "violates check constraint", "relation does not exist", "column does not exist", "migration", "postgres", "pgvector", "sqlstate"),
        (
            "Application code can accept a value that the live database constraint still rejects.",
            "A migration can pass on a fresh schema but fail against a historical constraint name.",
            "The backend can deploy before the additive migration is present in the image.",
            "A rollback can restore code that no longer understands rows written by the new schema.",
        ),
        ("preview migration transactionally", "inspect historical constraints", "verify image contains migration", "verify backward-compatible rollback"),
    ),
    FailureFamily(
        "embedding_or_worker_route",
        "Embedding or Worker route is absent, stale or incompatible",
        "high",
        ("embedding", "vector", "worker", "http 404", "route configured", "768", "proxy returned"),
        (
            "The repository route can exist while the published Worker still runs an older revision.",
            "Existing knowledge blocks can remain partial after the provider route is repaired.",
            "A provider can return vectors with the wrong dimensions and poison inserts.",
            "A health endpoint can pass without exercising the real embedding route.",
        ),
        ("run live embedding canary", "verify 768 dimensions", "repair missing vectors", "verify Worker revision contract"),
    ),
    FailureFamily(
        "agent_evidence_or_state",
        "Agent job state and runtime evidence disagree",
        "high",
        ("fake success", "runtime evidence", "job state", "tool event", "changedfiles", "diffsummary", "testsummary", "blocker"),
        (
            "The UI can show completion before changed-file and test evidence are persisted.",
            "A tool result from another repository can be attached to the active job.",
            "Draft-PR preparation can run before the evidence gate is satisfied.",
            "A terminal job can still expose a stale next action from an earlier state.",
        ),
        ("verify job ownership", "verify repository identity", "run evidence gate", "derive next action from persisted state"),
    ),
    FailureFamily(
        "backend_revision_stale",
        "Backend container or image revision is stale",
        "high",
        ("stale container", "old runtime", "revision mismatch", "image not found", "manifest unknown", "no such image"),
        (
            "Merged fixes remain absent while health checks still hit the previous process.",
            "A new migration can be skipped because the old image does not contain it.",
            "Logs can mix failed deployment output with the still-running old container.",
            "Rollback can reintroduce the same contract failure unless the digest is pinned.",
        ),
        ("resolve immutable image digest", "verify revision label", "inspect container logs", "retain pinned rollback digest"),
    ),
)

_GENERIC_FOLLOWUPS = (
    "The next state transition can still use stale input evidence.",
    "A parallel runtime surface can keep the old contract after the first fix.",
    "The persisted state can disagree with the response shown to the user.",
    "The final Draft-PR handoff can fail if repository or revision identity changes.",
)

_DOLLAR_QUOTE_RE = re.compile(r"(?P<tag>\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$).*?(?P=tag)", re.DOTALL)
_TOP_LEVEL_TX_RE = re.compile(r"(?im)^\s*(BEGIN(?:\s+(?:WORK|TRANSACTION))?|START\s+TRANSACTION|COMMIT|ROLLBACK)\s*;?")


def _bounded_text(value: Any, limit: int = MAX_EVIDENCE_CHARS) -> str:
    return str(value or "")[: max(0, limit)]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def evidence_hash(value: str) -> str:
    return sha256_text(_bounded_text(value))


def _family_score(text: str, family: FailureFamily) -> int:
    lowered = text.lower()
    score = 0
    for pattern in family.patterns:
        normalized = pattern.lower()
        if normalized and normalized in lowered:
            score += 3 if len(normalized) >= 12 else 1
    return score


def detect_failure_families(evidence_text: str, limit: int = MAX_FAMILIES) -> list[dict[str, Any]]:
    text = _bounded_text(evidence_text)
    matches: list[dict[str, Any]] = []
    for family in FAILURE_FAMILIES:
        score = _family_score(text, family)
        if score:
            matches.append({
                "code": family.code,
                "title": family.title,
                "severity": family.severity,
                "score": score,
                "checks": list(family.checks),
            })
    severity_rank = {"high": 3, "medium": 2, "low": 1}
    matches.sort(key=lambda item: (item["score"], severity_rank.get(item["severity"], 0)), reverse=True)
    return matches[: max(1, min(int(limit or MAX_FAMILIES), MAX_FAMILIES))]


def predict_followups(family_codes: Iterable[str], limit: int = FOLLOWUP_LIMIT) -> list[dict[str, Any]]:
    requested = max(1, min(int(limit or FOLLOWUP_LIMIT), FOLLOWUP_LIMIT))
    catalog = {family.code: family for family in FAILURE_FAMILIES}
    predictions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for code in family_codes:
        family = catalog.get(str(code))
        if not family:
            continue
        for index, prediction in enumerate(family.followups):
            if prediction in seen:
                continue
            seen.add(prediction)
            predictions.append({
                "fromFamily": family.code,
                "prediction": prediction,
                "checkNext": family.checks[index % len(family.checks)],
            })
            if len(predictions) == requested:
                return predictions
    for index, prediction in enumerate(_GENERIC_FOLLOWUPS):
        if prediction not in seen:
            predictions.append({
                "fromFamily": "runtime_state_neighbour",
                "prediction": prediction,
                "checkNext": ("verify input", "verify route", "verify stored state", "verify Draft PR evidence")[index],
            })
        if len(predictions) == requested:
            break
    return predictions


def runtime_failure_diagnose(
    evidence_text: str = "",
    *,
    mission: str = "",
    max_families: int = MAX_FAMILIES,
    followup_limit: int = FOLLOWUP_LIMIT,
) -> dict[str, Any]:
    bounded_evidence = _bounded_text(evidence_text)
    bounded_mission = _bounded_text(mission, 20_000)
    families = detect_failure_families("\n".join((bounded_mission, bounded_evidence)), max_families)
    followups = predict_followups((item["code"] for item in families), followup_limit)
    return {
        "ok": True,
        "runtime": "sovereign-universal-toolchain",
        "version": TOOLCHAIN_VERSION,
        "writeAction": False,
        "evidenceHash": evidence_hash(bounded_evidence),
        "missionHash": evidence_hash(bounded_mission),
        "logsReflected": False,
        "failureFamilies": families,
        "nextLogicalFailures": followups,
        "policy": {
            "pushToMain": False,
            "draftPrOnly": True,
            "arbitraryShell": False,
            "directGithubWrite": False,
            "productionWrite": False,
            "rawSecretsReflected": False,
            "followupLimit": FOLLOWUP_LIMIT,
        },
    }


def _mask_dollar_quoted_bodies(sql: str) -> tuple[str, list[dict[str, Any]]]:
    blocks: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        body = match.group(0)
        blocks.append({
            "index": len(blocks),
            "tag": match.group("tag"),
            "sha256": sha256_text(body),
            "bytes": len(body.encode("utf-8")),
        })
        return f"__PG_DOLLAR_QUOTED_BLOCK_{len(blocks) - 1}__"

    return _DOLLAR_QUOTE_RE.sub(replace, sql or ""), blocks


def validate_migration_for_rollback_preview(
    migration_sql: str,
    *,
    expected_sha256: str | None = None,
    repair_attempt: int = 0,
) -> dict[str, Any]:
    original = str(migration_sql or "")
    original_sha = sha256_text(original)
    masked, blocks = _mask_dollar_quoted_bodies(original)
    top_level_transactions = [
        {"keyword": re.sub(r"\s+", " ", match.group(1).upper()), "offset": match.start(1)}
        for match in _TOP_LEVEL_TX_RE.finditer(masked)
    ]
    expected_match = None if not expected_sha256 else original_sha == expected_sha256
    attempt_allowed = 0 <= int(repair_attempt or 0) <= MAX_AUTO_REPAIR_ATTEMPTS
    transaction_allowed = len(top_level_transactions) <= 2
    ok = attempt_allowed and transaction_allowed and expected_match is not False
    return {
        "ok": ok,
        "runtime": "sovereign-universal-toolchain",
        "version": TOOLCHAIN_VERSION,
        "writeAction": False,
        "policy": "rollback_preview_only",
        "originalMigrationUnchanged": True,
        "originalSha256": original_sha,
        "expectedSha256": expected_sha256,
        "expectedSha256Match": expected_match,
        "maskedPlpgsqlBlocks": blocks,
        "topLevelTransactions": top_level_transactions,
        "repairAttempt": int(repair_attempt or 0),
        "maxAutoRepairAttempts": MAX_AUTO_REPAIR_ATTEMPTS,
        "repairAttemptAllowed": attempt_allowed,
        "productionWrite": False,
        "blockedActions": [
            "Do not rewrite the original migration during diagnosis.",
            "Do not apply database writes from rollback preview.",
            "Do not exceed the bounded automatic repair limit.",
        ],
    }


def toolchain_manifest() -> dict[str, Any]:
    return {
        "name": "Sovereign Universal Toolchain",
        "version": TOOLCHAIN_VERSION,
        "runtime": "embedded",
        "tools": [
            {
                "name": "runtime_failure_diagnose",
                "description": "Classify evidence and return exactly four logical neighbouring runtime failures without reflecting raw logs.",
                "write_action": False,
                "input_schema": {"type": "object", "properties": {"evidence_text": {"type": "string"}, "mission": {"type": "string"}}},
            },
            {
                "name": "policy_guarded_rollback_preview",
                "description": "Validate migration transaction structure without changing or applying SQL.",
                "write_action": False,
                "input_schema": {"type": "object", "required": ["migration_sql"], "properties": {"migration_sql": {"type": "string"}, "expected_sha256": {"type": "string"}, "repair_attempt": {"type": "integer"}}},
            },
            {
                "name": "agent_toolchain_handoff",
                "description": "Create a predictive context and hand execution to the existing Sovereign Agent workspace. Draft PR remains a separate evidence-gated action.",
                "write_action": True,
                "requires_confirm": True,
                "execution_runtime": "sovereign-agent",
                "direct_github_write": False,
            },
        ],
        "policy": {
            "autoLoad": True,
            "pushToMain": False,
            "draftPrOnly": True,
            "confirmRequired": True,
            "arbitraryShell": False,
            "directProductionRunner": False,
            "directGithubToken": False,
            "auditEvidence": True,
        },
    }


def toolchain_briefing() -> dict[str, Any]:
    manifest = toolchain_manifest()
    return {
        "ok": True,
        "runtime": manifest["runtime"],
        "version": manifest["version"],
        "briefing": (
            "Use runtime_failure_diagnose before an execution handoff when logs or a failing state are present. "
            "Treat input, intent, route, result, stored state and next action as separate evidence boundaries. "
            "Execution stays in the existing Sovereign Agent workspace. Never push to main; create at most a Draft PR after changed-file, diff and test evidence pass."
        ),
        "policy": manifest["policy"],
    }


def build_agent_handoff_context(mission: str, evidence_text: str = "") -> dict[str, Any]:
    normalized_mission = _bounded_text(mission, 20_000).strip()
    if not normalized_mission:
        raise ValueError("mission is required")
    diagnosis = runtime_failure_diagnose(evidence_text, mission=normalized_mission)
    family_lines = [
        f"- {item['code']}: {item['title']} (severity={item['severity']})"
        for item in diagnosis["failureFamilies"]
    ] or ["- no known family matched; preserve runtime evidence and verify each state transition"]
    followup_lines = [
        f"{index}. {item['prediction']} Check next: {item['checkNext']}"
        for index, item in enumerate(diagnosis["nextLogicalFailures"], start=1)
    ]
    augmented_mission = "\n".join((
        normalized_mission,
        "",
        "[Sovereign Universal Toolchain predictive handoff]",
        f"Evidence SHA-256: {diagnosis['evidenceHash']}",
        "Detected failure families:",
        *family_lines,
        "Four logical neighbouring failures to verify:",
        *followup_lines,
        "Hard policy: no direct main write, no fake success, no arbitrary shell from chat, and Draft PR only after persisted runtime evidence.",
    ))
    return {"mission": augmented_mission, "diagnosis": diagnosis}


def dispatch_embedded_tool(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(args or {})
    if name == "runtime_failure_diagnose":
        return runtime_failure_diagnose(
            payload.get("evidence_text") or payload.get("log_text") or "",
            mission=payload.get("mission") or "",
        )
    if name == "policy_guarded_rollback_preview":
        return validate_migration_for_rollback_preview(
            str(payload.get("migration_sql") or ""),
            expected_sha256=payload.get("expected_sha256"),
            repair_attempt=int(payload.get("repair_attempt") or 0),
        )
    if name == "toolchain_briefing":
        return toolchain_briefing()
    raise KeyError(f"Unknown or blocked embedded tool: {name}")


def persist_toolchain_incident(
    conn: Any,
    *,
    user_id: str,
    mission: str,
    diagnosis: dict[str, Any],
) -> str:
    families = diagnosis.get("failureFamilies") or []
    followups = diagnosis.get("nextLogicalFailures") or []
    primary_family = families[0].get("code") if families else None
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO sovereign_toolchain_incidents
                   (user_id, mission_hash, evidence_hash, primary_family,
                    failure_families, followup_predictions, policy_snapshot)
               VALUES (%s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
               RETURNING id::text""",
            (
                user_id,
                evidence_hash(_bounded_text(mission, 20_000)),
                str(diagnosis.get("evidenceHash") or evidence_hash("")),
                primary_family,
                json.dumps(families, ensure_ascii=False),
                json.dumps(followups, ensure_ascii=False),
                json.dumps(diagnosis.get("policy") or {}, ensure_ascii=False),
            ),
        )
        row = cur.fetchone()
    conn.commit()
    if not row:
        raise RuntimeError("toolchain incident persistence returned no id")
    return str(row["id"] if isinstance(row, dict) else row[0])


def persist_toolchain_handoff(
    conn: Any,
    *,
    incident_id: str,
    user_id: str,
    job_id: str,
    repo_url: str,
    branch: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO sovereign_toolchain_handoffs
                   (incident_id, user_id, job_id, repo_url, branch)
               VALUES (%s::uuid, %s::uuid, %s, %s, %s)
               ON CONFLICT (job_id) DO UPDATE SET
                   incident_id = EXCLUDED.incident_id,
                   repo_url = EXCLUDED.repo_url,
                   branch = EXCLUDED.branch""",
            (incident_id, user_id, job_id, repo_url, branch),
        )
    conn.commit()
