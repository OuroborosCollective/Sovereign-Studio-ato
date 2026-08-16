"""Paid evidence verification for Sovereign A2A callers.

The public Evidence Observatory remains free. Sovereign provides the commercial
execution boundary: authenticated principals require a server-side entitlement;
non-privileged executions debit a small local credit cost exactly once per
request UUID; bounded verdicts are persisted as revision-bound receipts.
Model agreement is never a truth rule.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import os
import re
from typing import Any, Callable, Mapping
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from flask import jsonify, request

from paid_execution_entitlement import PaidExecutionEntitlement, resolve_paid_execution_entitlement
from .agent_run_receipts import ReceiptContractError, canonical_sha256


ConnectionFactory = Callable[[], Any]
SCHEMA_VERSION = "sovereign.verification-receipt.v1"
GATEWAY_VERSION = "1.0.0"
MAX_CLAIM_BYTES = 32_000
MAX_EVIDENCE_BYTES = 200_000
MAX_SOURCES = 200
MAX_JSON_DEPTH = 40
DEFAULT_CREDIT_COST = 1
A2A_PROTOCOL_VERSION = "1.0"

ROUTES = frozenset({
    "formal computation",
    "runtime readback",
    "source provenance",
    "federated receipt",
    "unknown",
})
VERDICTS = frozenset({
    "PROVEN",
    "CONTRADICTED",
    "UNPROVEN",
    "EVIDENCE_PRESENT_REVIEW_REQUIRED",
})

# Public Evidence Observatory anchor. Only public verification material is pinned.
HF_OBSERVATORY_SPACE_REVISION = "721dd06c4b5d3da923c4ecd88e4959ebc259df37"
HF_OBSERVATORY_KEY_ID = "7fc8cdc997b1fadc4c0b183789fd191e790fa12d8e470e9ba7a3d9de6c39b685"
HF_OBSERVATORY_PUBLIC_KEY_HEX = "51e79d3f21cf85812ad7f9068263478cbb128a7fba6a7a2926960bdc008fd7ae"

_FORMAL_CUE = re.compile(
    r"\bprime\b|\bprimzahl\b|\bdivisible\b|\bteilbar\b|"
    r"\d\s*(?:\+|-|\*|/|\^|==|=|<|>)\s*\d",
    re.IGNORECASE,
)
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_BIN = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow}
_ALLOWED_UNARY = {ast.UAdd, ast.USub}
_CREDENTIAL_MARKERS = (
    "sk" + "-",
    "gh" + "p_",
    "github" + "_pat_",
    "authorization" + ": bearer",
)


class VerificationGatewayError(RuntimeError):
    status_code = 400
    failure_family = "VERIFICATION_GATEWAY_ERROR"


class VerificationPaymentRequired(VerificationGatewayError):
    status_code = 402
    failure_family = "VERIFICATION_CREDITS_REQUIRED"


class VerificationEntitlementRequired(VerificationGatewayError):
    status_code = 403
    failure_family = "VERIFICATION_ENTITLEMENT_REQUIRED"


class VerificationConflict(VerificationGatewayError):
    status_code = 409
    failure_family = "VERIFICATION_IDEMPOTENCY_CONFLICT"


class VerificationCreditStateMismatch(VerificationGatewayError):
    status_code = 409
    failure_family = "CREDIT_STATE_VERIFICATION_FAILED"


class VerificationPersistenceUnavailable(VerificationGatewayError):
    status_code = 503
    failure_family = "VERIFICATION_PERSISTENCE_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    route: str
    verdict: str
    details: dict[str, Any]
    evidence_sha256: str


def _close_connection(connection: Any) -> None:
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def _normalize(value: object) -> str:
    return " ".join(str(value or "").split())


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _plain_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _contains_credential_text(value: str) -> bool:
    folded = str(value or "").casefold()
    return any(marker in folded for marker in _CREDENTIAL_MARKERS)


def _depth(value: Any, level: int = 0) -> int:
    if level > MAX_JSON_DEPTH:
        return level
    if isinstance(value, Mapping):
        return max([level] + [_depth(item, level + 1) for item in value.values()])
    if isinstance(value, list):
        return max([level] + [_depth(item, level + 1) for item in value])
    return level


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def _validate_input(claim: object, evidence: object) -> tuple[str, dict[str, Any]]:
    normalized_claim = _normalize(claim)
    if not normalized_claim:
        raise ValueError("claim is required")
    if len(normalized_claim.encode("utf-8")) > MAX_CLAIM_BYTES:
        raise ValueError("claim exceeds the bounded input limit")
    if _contains_credential_text(normalized_claim):
        raise ValueError("credential-shaped material is forbidden in verification claims")
    if evidence is None:
        normalized_evidence: dict[str, Any] = {}
    elif isinstance(evidence, Mapping):
        normalized_evidence = dict(evidence)
    else:
        raise ValueError("evidence must be a JSON object")
    if _depth(normalized_evidence) > MAX_JSON_DEPTH:
        raise ValueError("evidence nesting exceeds the bounded limit")
    if _contains_float(normalized_evidence):
        raise ValueError("floating-point evidence is forbidden")
    try:
        serialized = _canonical_json(normalized_evidence)
        if isinstance(normalized_evidence.get("federatedReceipt"), Mapping):
            _plain_sha256(normalized_evidence)
        else:
            canonical_sha256(normalized_evidence)
    except (TypeError, ValueError, ReceiptContractError) as exc:
        raise ValueError(f"evidence violates the canonical contract: {type(exc).__name__}") from exc
    if len(serialized.encode("utf-8")) > MAX_EVIDENCE_BYTES:
        raise ValueError("evidence exceeds the bounded input limit")
    if _contains_credential_text(serialized):
        raise ValueError("credential-shaped material is forbidden in verification evidence")
    return normalized_claim, normalized_evidence


def _source_revision() -> tuple[str, bool]:
    revision = str(os.getenv("SOVEREIGN_SOURCE_REVISION", "")).strip().lower()
    return revision, bool(_SHA40.fullmatch(revision))


def _credit_cost() -> int:
    raw = str(os.getenv("SOVEREIGN_VERIFICATION_CREDIT_COST", DEFAULT_CREDIT_COST)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_CREDIT_COST
    return max(1, min(value, 1000))


# ---------- deterministic formal lane ----------

def _is_prime_64(n: int) -> bool:
    if n < 2:
        return False
    if n >= 2**64:
        raise ValueError("integer outside deterministic <2^64 range")
    small = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    if n in small:
        return True
    if any(n % prime == 0 for prime in small):
        return False
    d, s = n - 1, 0
    while d % 2 == 0:
        s += 1
        d //= 2
    for base in (2, 325, 9375, 28178, 450775, 9780504, 1795265022):
        if base % n == 0:
            continue
        x = pow(base, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _safe_fraction_expr(expression: str) -> Fraction:
    if len(expression) > 180:
        raise ValueError("expression too long")
    tree = ast.parse(expression.replace("^", "**"), mode="eval")

    def evaluate(node: ast.AST) -> Fraction:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and type(node.value) is int:
            if abs(node.value) > 10**18:
                raise ValueError("integer too large")
            return Fraction(node.value, 1)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
            result = evaluate(node.operand)
            return result if isinstance(node.op, ast.UAdd) else -result
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BIN:
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ValueError("division by zero")
                return left / right
            if isinstance(node.op, ast.Pow):
                if right.denominator != 1 or abs(right.numerator) > 20:
                    raise ValueError("exponent must be an integer with |n| <= 20")
                if left == 0 and right.numerator < 0:
                    raise ValueError("division by zero")
                return left ** right.numerator
        raise ValueError("unsupported expression")

    return evaluate(tree)


def _fraction_payload(value: Fraction) -> dict[str, int | str]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "exact": str(value) if value.denominator != 1 else str(value.numerator),
    }


def formal_verify(claim: str) -> VerificationResult:
    normalized = _normalize(claim)
    lowered = normalized.lower().rstrip(".?! ")
    match = re.fullmatch(
        r"(-?\d+)\s+(?:is|ist)\s+(not\s+|nicht\s+)?(?:a\s+)?(?:prime(?:\s+number)?|primzahl)",
        lowered,
    )
    if match:
        number = int(match.group(1))
        asserted = not bool(match.group(2))
        if number >= 2**64:
            details = {
                "method": "deterministic-primality-64bit",
                "reason": "positive integer outside deterministic <2^64 range",
            }
            return VerificationResult("formal computation", "UNPROVEN", details, canonical_sha256(details))
        actual = _is_prime_64(number)
        verdict = "PROVEN" if actual == asserted else "CONTRADICTED"
        details = {
            "method": "deterministic-primality-64bit",
            "observed": actual,
            "asserted": asserted,
            "wolframVerificationExpression": (
                f"VerificationTest[PrimeQ[{number}], {'True' if asserted else 'False'}]"
            ),
        }
        return VerificationResult("formal computation", verdict, details, canonical_sha256(details))

    match = re.fullmatch(
        r"(-?\d+)\s+(?:is\s+)?(?:divisible\s+by|ist\s+durch)\s+(-?\d+)(?:\s+teilbar)?",
        lowered,
    )
    if match:
        number, divisor = map(int, match.groups())
        if divisor == 0 or abs(number) > 10**30 or abs(divisor) > 10**30:
            details = {"reason": "divisor zero or integer outside bounded divisibility range"}
            return VerificationResult("formal computation", "UNPROVEN", details, canonical_sha256(details))
        actual = number % divisor == 0
        details = {
            "method": "integer-divisibility",
            "observed": actual,
            "wolframVerificationExpression": f"VerificationTest[Mod[{number},{divisor}] == 0, True]",
        }
        return VerificationResult(
            "formal computation",
            "PROVEN" if actual else "CONTRADICTED",
            details,
            canonical_sha256(details),
        )

    comparison = re.fullmatch(r"(.+?)\s*(==|=|<=|>=|<|>)\s*(.+)", lowered)
    if comparison:
        left_text, operator, right_text = comparison.groups()
        try:
            left, right = _safe_fraction_expr(left_text), _safe_fraction_expr(right_text)
        except Exception as exc:
            details = {"reason": f"unsupported exact expression: {type(exc).__name__}"}
            return VerificationResult("formal computation", "UNPROVEN", details, canonical_sha256(details))
        observed = {
            "=": left == right,
            "==": left == right,
            "<": left < right,
            ">": left > right,
            "<=": left <= right,
            ">=": left >= right,
        }[operator]
        wolfram_operator = "==" if operator in {"=", "=="} else operator
        details = {
            "method": "exact-rational-comparison",
            "left": _fraction_payload(left),
            "right": _fraction_payload(right),
            "operator": operator,
            "observed": observed,
            "wolframVerificationExpression": (
                f"VerificationTest[({left_text}) {wolfram_operator} ({right_text}), True]"
            ),
        }
        return VerificationResult(
            "formal computation",
            "PROVEN" if observed else "CONTRADICTED",
            details,
            canonical_sha256(details),
        )

    details = {
        "reason": "claim outside bounded formal grammar",
        "supportedExamples": [
            "174 is prime",
            "173 is prime",
            "12 is divisible by 3",
            "1/3 + 1/6 = 1/2",
        ],
    }
    return VerificationResult("formal computation", "UNPROVEN", details, canonical_sha256(details))


# ---------- supplied runtime lane ----------

def _compare_expected(expected: Any, observed: Any, path: str = "$") -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    if isinstance(expected, Mapping):
        if not isinstance(observed, Mapping):
            return [{"path": path, "expected": expected, "observed": observed}]
        for key, value in expected.items():
            if key not in observed:
                mismatches.append({"path": f"{path}.{key}", "expected": value, "observed": "<missing>"})
            else:
                mismatches.extend(_compare_expected(value, observed[key], f"{path}.{key}"))
    elif expected != observed:
        mismatches.append({"path": path, "expected": expected, "observed": observed})
    return mismatches


def runtime_verify(evidence: Mapping[str, Any]) -> VerificationResult:
    expected = evidence.get("expected")
    observed = evidence.get("observed")
    if not isinstance(expected, Mapping) or not expected or not isinstance(observed, Mapping) or not observed:
        details = {"reason": "runtime evidence requires non-empty expected and observed objects"}
        return VerificationResult("runtime readback", "UNPROVEN", details, canonical_sha256(details))
    mismatches = _compare_expected(expected, observed)
    if mismatches:
        details = {
            "sourceAuthenticityVerified": False,
            "mismatches": mismatches[:100],
            "expectedSha256": canonical_sha256(expected),
            "observedSha256": canonical_sha256(observed),
        }
        return VerificationResult("runtime readback", "CONTRADICTED", details, canonical_sha256(details))
    details = {
        "sourceAuthenticityVerified": False,
        "mismatches": [],
        "expectedSha256": canonical_sha256(expected),
        "observedSha256": canonical_sha256(observed),
        "truthBoundary": (
            "Supplied observed JSON matches expected fields, but this lane does not authenticate "
            "that the observation came directly from the target runtime."
        ),
    }
    return VerificationResult(
        "runtime readback",
        "EVIDENCE_PRESENT_REVIEW_REQUIRED",
        details,
        canonical_sha256(details),
    )


# ---------- source provenance lane ----------

def provenance_verify(evidence: Mapping[str, Any]) -> VerificationResult:
    raw_sources = evidence.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources or len(raw_sources) > MAX_SOURCES:
        details = {"reason": f"sources must be a non-empty array of <= {MAX_SOURCES} objects"}
        return VerificationResult("source provenance", "UNPROVEN", details, canonical_sha256(details))
    if not all(isinstance(item, Mapping) for item in raw_sources):
        details = {"reason": "every source must be a JSON object"}
        return VerificationResult("source provenance", "UNPROVEN", details, canonical_sha256(details))
    by_id: dict[str, Mapping[str, Any]] = {}
    for index, source in enumerate(raw_sources):
        source_id = str(source.get("id") or f"source-{index + 1}").strip()
        if not source_id or source_id in by_id:
            details = {"reason": "source ids must be non-empty and unique"}
            return VerificationResult("source provenance", "UNPROVEN", details, canonical_sha256(details))
        by_id[source_id] = source

    def lineage_root(source_id: str) -> tuple[str | None, tuple[str, ...]]:
        path: list[str] = []
        positions: dict[str, int] = {}
        current = source_id
        while True:
            if current in positions:
                return None, tuple(sorted(path[positions[current] :]))
            positions[current] = len(path)
            path.append(current)
            parent = str(by_id.get(current, {}).get("derives_from") or "").strip()
            if not parent or parent not in by_id:
                return current, ()
            current = parent

    roots: dict[str, list[str]] = {}
    cycles: set[tuple[str, ...]] = set()
    for source_id in by_id:
        root, cycle = lineage_root(source_id)
        if cycle:
            cycles.add(cycle)
            continue
        assert root is not None
        root_source = by_id[root]
        origin = str(root_source.get("canonical_origin") or root_source.get("url") or root).strip().lower()
        content_sha = str(root_source.get("content_sha256") or "").strip().lower()
        identity = f"content:{content_sha}" if _SHA64.fullmatch(content_sha) else f"origin:{origin}"
        roots.setdefault(identity, []).append(source_id)
    independent = len(roots)
    duplicates = [sorted(items) for items in roots.values() if len(items) > 1]
    verdict = "EVIDENCE_PRESENT_REVIEW_REQUIRED" if independent else "UNPROVEN"
    details = {
        "sourceCount": len(raw_sources),
        "independentOriginCount": independent,
        "lineageIntegrityValid": not cycles,
        "duplicateOrDerivedClusters": sorted(duplicates),
        "lineageCycles": [list(item) for item in sorted(cycles)],
        "truthBoundary": "Independent origins increase diversity but do not by themselves prove the claim.",
    }
    return VerificationResult("source provenance", verdict, details, canonical_sha256(details))


# ---------- public Evidence Observatory federation lane ----------

def _verify_hf_receipt_integrity(receipt: Mapping[str, Any]) -> bool:
    digest = str(receipt.get("receiptSha256") or "").strip().lower()
    if not _SHA64.fullmatch(digest):
        return False
    unsigned = dict(receipt)
    unsigned.pop("receiptSha256", None)
    unsigned.pop("issuerSignatureBase64", None)
    try:
        return _plain_sha256(unsigned) == digest
    except (TypeError, ValueError):
        return False


def _verify_hf_receipt_signature(receipt: Mapping[str, Any]) -> bool:
    if not _verify_hf_receipt_integrity(receipt):
        return False
    issuer = receipt.get("issuer")
    signature_b64 = receipt.get("issuerSignatureBase64")
    if not isinstance(issuer, Mapping) or not isinstance(signature_b64, str):
        return False
    if issuer.get("status") != "SIGNED" or issuer.get("algorithm") != "Ed25519":
        return False
    if issuer.get("keyId") != HF_OBSERVATORY_KEY_ID:
        return False
    try:
        public_raw = bytes.fromhex(HF_OBSERVATORY_PUBLIC_KEY_HEX)
        signature = __import__("base64").b64decode(signature_b64, validate=True)
        Ed25519PublicKey.from_public_bytes(public_raw).verify(
            signature,
            bytes.fromhex(str(receipt["receiptSha256"])),
        )
        return hashlib.sha256(public_raw).hexdigest() == HF_OBSERVATORY_KEY_ID
    except (ValueError, InvalidSignature):
        return False


def federated_verify(claim: str, evidence: Mapping[str, Any]) -> VerificationResult:
    receipt = evidence.get("federatedReceipt")
    if not isinstance(receipt, Mapping):
        details = {"reason": "federatedReceipt must be a JSON object"}
        return VerificationResult("federated receipt", "UNPROVEN", details, canonical_sha256(details))
    integrity = _verify_hf_receipt_integrity(receipt)
    authenticated = integrity and _verify_hf_receipt_signature(receipt)
    claim_hash = _sha_text(_normalize(claim))
    claim_bound = authenticated and receipt.get("claimSha256") == claim_hash
    observed_verdict = str(receipt.get("verdict") or "UNPROVEN").upper()
    route = str(receipt.get("route") or "")
    replay_verified = False
    local_verdict = "UNPROVEN"
    if claim_bound and route == "formal computation":
        replay = formal_verify(claim)
        local_verdict = replay.verdict
        replay_verified = (
            replay.verdict == observed_verdict
            and replay.verdict in {"PROVEN", "CONTRADICTED", "UNPROVEN"}
        )
    verdict = (
        observed_verdict
        if replay_verified and observed_verdict in {"PROVEN", "CONTRADICTED"}
        else "EVIDENCE_PRESENT_REVIEW_REQUIRED"
        if authenticated and claim_bound
        else "UNPROVEN"
    )
    details = {
        "federatedProvider": "hugging-face-evidence-observatory",
        "pinnedTrustAnchorKeyId": HF_OBSERVATORY_KEY_ID,
        "pinnedObservatoryRevision": HF_OBSERVATORY_SPACE_REVISION,
        "receiptIntegrityValid": integrity,
        "issuerAuthenticated": authenticated,
        "claimBound": claim_bound,
        "formalReplayVerified": replay_verified,
        "observedVerdict": observed_verdict if integrity else "UNPROVEN",
        "localReplayVerdict": local_verdict,
        "truthBoundary": (
            "Federated authenticity proves issuer and bytes. A decisive formal verdict is promoted only "
            "after claim binding and independent local replay."
        ),
    }
    return VerificationResult("federated receipt", verdict, details, canonical_sha256(details))


def suggest_route(claim: str, evidence: Mapping[str, Any]) -> str:
    if isinstance(evidence.get("federatedReceipt"), Mapping):
        return "federated receipt"
    if _FORMAL_CUE.search(claim):
        return "formal computation"
    if isinstance(evidence.get("expected"), Mapping) or isinstance(evidence.get("observed"), Mapping):
        return "runtime readback"
    if isinstance(evidence.get("sources"), list):
        return "source provenance"
    return "unknown"


def verify_claim(*, claim: object, route: object = "auto", evidence: object = None) -> VerificationResult:
    normalized_claim, normalized_evidence = _validate_input(claim, evidence)
    selected = str(route or "auto").strip().lower().replace("_", " ")
    if selected == "auto":
        selected = suggest_route(normalized_claim, normalized_evidence)
    if selected not in ROUTES:
        raise ValueError("route must be auto, formal computation, runtime readback, source provenance, federated receipt or unknown")
    if selected == "formal computation":
        return formal_verify(normalized_claim)
    if selected == "runtime readback":
        return runtime_verify(normalized_evidence)
    if selected == "source provenance":
        return provenance_verify(normalized_evidence)
    if selected == "federated receipt":
        return federated_verify(normalized_claim, normalized_evidence)
    details = {"reason": "no deciding evidence class identified", "abstentionIsValid": True}
    return VerificationResult("unknown", "UNPROVEN", details, canonical_sha256(details))


# ---------- entitlement, exactly-once billing and persistence ----------

def _account_row(cursor: Any, user_id: str, *, for_update: bool) -> Mapping[str, Any] | None:
    lock = " FOR UPDATE" if for_update else ""
    cursor.execute(
        """SELECT account.id::text AS id, account.email, account.role,
                  account.credits::integer AS credits,
                  EXISTS(
                    SELECT 1
                    FROM transactions AS tx
                    JOIN credit_receipts AS credit_receipt
                      ON credit_receipt.user_id = tx.user_id
                     AND credit_receipt.provider = tx.provider
                     AND credit_receipt.provider_tx_id = tx.provider_tx_id
                    WHERE tx.user_id = account.id
                      AND tx.type = 'credit_purchase'
                      AND tx.status = 'completed'
                  ) AS paid_purchase_verified
           FROM admin_users AS account
           WHERE account.id = %s::uuid
           LIMIT 1""" + lock,
        (str(user_id),),
    )
    return cursor.fetchone()


def _entitlement_from_account(account: Mapping[str, Any]) -> PaidExecutionEntitlement:
    return resolve_paid_execution_entitlement(
        account_id=str(account["id"]),
        email=str(account.get("email") or ""),
        role=str(account.get("role") or ""),
        purchase_verified=bool(account.get("paid_purchase_verified")),
        credit_balance=int(account.get("credits") or 0),
        configured_owner_id=os.getenv("SOVEREIGN_OWNER_ADMIN_ID", ""),
        configured_owner_email=os.getenv("SOVEREIGN_OWNER_ADMIN_EMAIL", ""),
    )


def read_verification_entitlement(get_connection: ConnectionFactory, *, user_id: str) -> dict[str, Any]:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            account = _account_row(cursor, user_id, for_update=False)
            if not account:
                raise LookupError("authenticated user account was not found")
            entitlement = _entitlement_from_account(account)
            return {
                "verified": entitlement.verified,
                "source": entitlement.source,
                "purchaseVerified": entitlement.purchase_verified,
                "privileged": entitlement.privileged,
                "creditBalance": max(0, int(account.get("credits") or 0)),
                "verificationCreditCost": 0 if entitlement.privileged else _credit_cost(),
                "serverSide": True,
            }
    finally:
        _close_connection(connection)


def _existing_receipt(cursor: Any, request_id: str) -> Mapping[str, Any] | None:
    cursor.execute(
        """SELECT request_id::text, user_id::text, request_fingerprint,
                  receipt, charged_credits, created_at
           FROM verification_receipts
           WHERE request_id=%s::uuid
           LIMIT 1""",
        (request_id,),
    )
    return cursor.fetchone()


def _receipt_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    stored = row.get("receipt")
    if isinstance(stored, str):
        stored = json.loads(stored)
    if not isinstance(stored, Mapping):
        raise VerificationPersistenceUnavailable("stored verification receipt is malformed")
    return dict(stored)


def _seal_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out["issuer"] = {
        "status": "REVISION_BOUND_DB_PERSISTED",
        "algorithm": "sha256",
        "ed25519Configured": False,
    }
    out["receiptSha256"] = canonical_sha256(out)
    return out


def execute_paid_verification(
    get_connection: ConnectionFactory,
    *,
    user_id: str,
    request_id: object,
    claim: object,
    route: object = "auto",
    evidence: object = None,
) -> tuple[dict[str, Any], bool]:
    try:
        normalized_request_id = str(uuid.UUID(str(request_id or "")))
    except (ValueError, AttributeError) as exc:
        raise ValueError("requestId must be a UUID") from exc
    normalized_claim, normalized_evidence = _validate_input(claim, evidence)
    selected_route = str(route or "auto").strip().lower().replace("_", " ")
    request_fingerprint = _plain_sha256({
        "claim": normalized_claim,
        "evidence": normalized_evidence,
        "route": selected_route,
    })
    result = verify_claim(claim=normalized_claim, route=selected_route, evidence=normalized_evidence)
    source_revision, revision_verified = _source_revision()
    if result.verdict in {"PROVEN", "CONTRADICTED"} and not revision_verified:
        result = VerificationResult(
            result.route,
            "EVIDENCE_PRESENT_REVIEW_REQUIRED",
            {
                **result.details,
                "decisiveVerifierResult": result.verdict,
                "reason": "SOVEREIGN_SOURCE_REVISION is not an exact Git SHA",
            },
            result.evidence_sha256,
        )

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            account = _account_row(cursor, user_id, for_update=True)
            if not account:
                raise LookupError("authenticated user account was not found")
            existing = _existing_receipt(cursor, normalized_request_id)
            if existing:
                if str(existing.get("user_id") or "") != str(user_id):
                    raise VerificationConflict("requestId belongs to another principal")
                if str(existing.get("request_fingerprint") or "") != request_fingerprint:
                    raise VerificationConflict("requestId was already used with different verification input")
                return _receipt_from_row(existing), True

            entitlement = _entitlement_from_account(account)
            if not entitlement.verified:
                raise VerificationEntitlementRequired("paid verification entitlement is required")

            cached_balance = int(account.get("credits") or 0)
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0)::integer AS ledger_balance FROM credit_ledger WHERE user_id=%s::uuid",
                (str(user_id),),
            )
            ledger_row = cursor.fetchone() or {"ledger_balance": 0}
            ledger_balance = int(ledger_row.get("ledger_balance") or 0)
            if ledger_balance != cached_balance:
                raise VerificationCreditStateMismatch("cached credits do not match the append-only credit ledger")

            charged = 0 if entitlement.privileged else _credit_cost()
            if charged > ledger_balance:
                raise VerificationPaymentRequired("insufficient credits for paid verification")

            receipt_payload = {
                "schemaVersion": SCHEMA_VERSION,
                "gatewayVersion": GATEWAY_VERSION,
                "requestId": normalized_request_id,
                "requestFingerprint": request_fingerprint,
                "claimSha256": _sha_text(normalized_claim),
                "route": result.route,
                "verdict": result.verdict,
                "evidenceSha256": result.evidence_sha256,
                "details": result.details,
                "sourceRevision": source_revision,
                "sourceRevisionVerified": revision_verified,
                "billing": {
                    "chargedCredits": charged,
                    "entitlementSource": entitlement.source,
                    "privileged": entitlement.privileged,
                    "idempotencyKey": normalized_request_id,
                },
                "truthNotInferredFromAgreement": True,
                "automaticModelFallback": False,
                "rawModelOutputUsed": False,
            }
            sealed = _seal_receipt(receipt_payload)

            if charged:
                cursor.execute(
                    """INSERT INTO credit_ledger
                           (user_id, type, amount, reason, provider, provider_tx_id, created_by)
                       VALUES (%s::uuid, 'verification_usage', %s,
                               'Sovereign Verification Gateway',
                               'verification-gateway', %s, %s::uuid)""",
                    (str(user_id), -charged, normalized_request_id, str(user_id)),
                )
                cursor.execute(
                    "UPDATE admin_users SET credits = credits - %s WHERE id=%s::uuid",
                    (charged, str(user_id)),
                )

            cursor.execute(
                """INSERT INTO verification_receipts
                       (request_id, user_id, request_fingerprint, claim_sha256,
                        route, verdict, receipt_sha256, receipt, charged_credits)
                   VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb, %s)""",
                (
                    normalized_request_id,
                    str(user_id),
                    request_fingerprint,
                    sealed["claimSha256"],
                    sealed["route"],
                    sealed["verdict"],
                    sealed["receiptSha256"],
                    _canonical_json(sealed),
                    charged,
                ),
            )
        connection.commit()
        return sealed, False
    except (VerificationGatewayError, LookupError, ValueError):
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback()
        raise
    except Exception as exc:
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback()
        raise VerificationPersistenceUnavailable(
            f"verification persistence failed: {type(exc).__name__}"
        ) from exc
    finally:
        _close_connection(connection)


def read_verification_receipt(
    get_connection: ConnectionFactory,
    *,
    user_id: str,
    request_id: str,
) -> dict[str, Any] | None:
    try:
        normalized_request_id = str(uuid.UUID(str(request_id or "")))
    except (ValueError, AttributeError) as exc:
        raise ValueError("requestId must be a UUID") from exc
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT receipt FROM verification_receipts
                   WHERE request_id=%s::uuid AND user_id=%s::uuid LIMIT 1""",
                (normalized_request_id, str(user_id)),
            )
            row = cursor.fetchone()
            return _receipt_from_row(row) if row else None
    finally:
        _close_connection(connection)


def gateway_status() -> dict[str, Any]:
    source_revision, revision_verified = _source_revision()
    return {
        "schemaVersion": "sovereign.verification-gateway-status.v1",
        "gatewayVersion": GATEWAY_VERSION,
        "status": "READY" if revision_verified else "REVISION_UNVERIFIED",
        "sourceRevision": source_revision or None,
        "sourceRevisionVerified": revision_verified,
        "routes": sorted(ROUTES),
        "defaultCreditCost": _credit_cost(),
        "entitlement": "server-side-required",
        "idempotency": "requestId-uuid-exactly-once",
        "receiptAuthority": "revision-bound-database-persistence",
        "federation": {
            "huggingFaceObservatoryRevision": HF_OBSERVATORY_SPACE_REVISION,
            "huggingFaceTrustAnchorKeyId": HF_OBSERVATORY_KEY_ID,
            "crossSystemKeyReuse": False,
        },
        "truthNotInferredFromAgreement": True,
        "credentialValuesReturned": False,
    }


def _current_user_id() -> str:
    return str(getattr(request, "session_user_id", None) or "")


def _error_payload(exc: Exception) -> tuple[dict[str, Any], int]:
    if isinstance(exc, VerificationGatewayError):
        return {
            "ok": False,
            "error": exc.failure_family,
            "message": str(exc),
            "credentialValuesReturned": False,
        }, exc.status_code
    if isinstance(exc, LookupError):
        return {"ok": False, "error": "ACCOUNT_NOT_FOUND", "message": str(exc)}, 404
    if isinstance(exc, ValueError):
        return {"ok": False, "error": "INVALID_VERIFICATION_REQUEST", "message": str(exc)}, 400
    return {
        "ok": False,
        "error": "VERIFICATION_GATEWAY_UNAVAILABLE",
        "message": type(exc).__name__,
        "credentialValuesReturned": False,
    }, 503


def register_verification_gateway_routes(
    app,
    *,
    require_session,
    get_connection: ConnectionFactory,
) -> None:
    """Register public status plus authenticated REST and A2A verification routes."""

    @app.route("/api/verification/status", methods=["GET"])
    def public_verification_gateway_status():
        return jsonify(gateway_status())

    @app.route("/api/user/agent/verification/entitlement", methods=["GET"])
    @require_session
    def user_verification_entitlement():
        try:
            return jsonify({
                "ok": True,
                "entitlement": read_verification_entitlement(
                    get_connection,
                    user_id=_current_user_id(),
                ),
            })
        except Exception as exc:
            payload, status = _error_payload(exc)
            return jsonify(payload), status

    def execute_request(body: Mapping[str, Any]):
        try:
            receipt, replayed = execute_paid_verification(
                get_connection,
                user_id=_current_user_id(),
                request_id=body.get("requestId"),
                claim=body.get("claim"),
                route=body.get("route") or "auto",
                evidence=body.get("evidence") or {},
            )
            return jsonify({
                "ok": True,
                "replayed": replayed,
                "receipt": receipt,
                "credentialValuesReturned": False,
            }), 200
        except Exception as exc:
            payload, status = _error_payload(exc)
            return jsonify(payload), status

    @app.route("/api/user/agent/verification/verify", methods=["POST"])
    @require_session
    def user_execute_verification():
        return execute_request(request.get_json(force=True) or {})

    @app.route("/api/user/agent/verification/receipts/<request_id>", methods=["GET"])
    @require_session
    def user_read_verification_receipt(request_id: str):
        try:
            receipt = read_verification_receipt(
                get_connection,
                user_id=_current_user_id(),
                request_id=request_id,
            )
            if receipt is None:
                return jsonify({"error": "verification receipt not found"}), 404
            return jsonify({"ok": True, "receipt": receipt, "credentialValuesReturned": False})
        except Exception as exc:
            payload, status = _error_payload(exc)
            return jsonify(payload), status

    @app.route("/a2a/v1/verification:verify", methods=["POST"])
    @require_session
    def a2a_execute_verification():
        if str(request.headers.get("A2A-Version") or "").strip() != A2A_PROTOCOL_VERSION:
            response = jsonify({
                "error": {
                    "code": 400,
                    "status": "FAILED_PRECONDITION",
                    "message": "A2A-Version 1.0 is required",
                    "details": [{"reason": "VERSION_NOT_SUPPORTED", "domain": "a2a-protocol.org"}],
                }
            })
            response.status_code = 400
            response.headers["A2A-Version"] = A2A_PROTOCOL_VERSION
            return response
        response, status = execute_request(request.get_json(force=True) or {})
        response.status_code = status
        response.headers["A2A-Version"] = A2A_PROTOCOL_VERSION
        response.headers["X-Sovereign-A2A-Extension"] = "verification-v1"
        return response
