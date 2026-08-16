from __future__ import annotations

from functools import wraps
import json
import os
from pathlib import Path
import sys
import uuid

import pytest
from flask import Flask, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.verification_gateway import (  # noqa: E402
    VerificationConflict,
    VerificationCreditStateMismatch,
    VerificationEntitlementRequired,
    VerificationPaymentRequired,
    federated_verify,
    formal_verify,
    gateway_status,
    provenance_verify,
    register_verification_gateway_routes,
    runtime_verify,
    verify_claim,
    execute_paid_verification,
)


HF_173_RECEIPT = {
    "asserted": True,
    "authority": {
        "externalWrite": False,
        "networkAccess": "NONE",
        "paidCompute": False,
        "scope": "CURRENT_PUBLIC_SPACE_LOCAL_LANE",
        "secretInputAccepted": False,
        "userDataExport": False,
    },
    "claim": "173 is prime",
    "claimSha256": "da912adfc07787eedce197c5f6c77ca55c1f37dc2d003a1c3b0739673d533af0",
    "implementationVersion": "2.1.3",
    "issuer": {
        "algorithm": "Ed25519",
        "keyId": "7fc8cdc997b1fadc4c0b183789fd191e790fa12d8e470e9ba7a3d9de6c39b685",
        "publicKeyBase64": "UeedPyHPhYEq1/kGgmNHjLsSin+6anopJpYL3ACP164=",
        "status": "SIGNED",
    },
    "issuerSignatureBase64": "tdJeObTOUSBQjtBRhdMJRC+DW/74pfwnEkV9ajwu5vhzPxvLvKDl/u8LppMT5wBexH3cQB+jAwd0x0oCVeiSDA==",
    "method": "deterministic-primality-64bit",
    "observed": True,
    "receiptSha256": "ca0df7e9005d2c06c6800590884a1a9a0e2f8de5e5fc90b1124db6145aa420a8",
    "route": "formal computation",
    "schemaVersion": "sovereign.proof-router-receipt.v2",
    "truthNotInferredFromAgreement": True,
    "verdict": "PROVEN",
    "verifierAuthority": "bounded-local-deterministic",
    "wolframVerificationExpression": "VerificationTest[PrimeQ[173], True]",
}


class FakeCursor:
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn
        self.last_result = None

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.conn.executed.append((sql, params))
        self.last_result = None
        normalized = " ".join(sql.upper().split())
        if "FROM ADMIN_USERS AS ACCOUNT" in normalized:
            user_id = str(params[0])
            account = self.conn.users.get(user_id)
            self.last_result = dict(account) if account else None
        elif "FROM VERIFICATION_RECEIPTS" in normalized and "REQUEST_FINGERPRINT" in normalized:
            request_id = str(params[0])
            row = self.conn.receipts.get(request_id)
            self.last_result = dict(row) if row else None
        elif normalized.startswith("SELECT COALESCE(SUM(AMOUNT)") and "FROM CREDIT_LEDGER" in normalized:
            user_id = str(params[0])
            balance = sum(entry["amount"] for entry in self.conn.ledger if entry["user_id"] == user_id)
            self.last_result = {"ledger_balance": balance}
        elif normalized.startswith("INSERT INTO CREDIT_LEDGER"):
            user_id, amount, provider_tx_id, created_by = params
            self.conn.ledger.append({
                "user_id": str(user_id),
                "amount": int(amount),
                "provider_tx_id": str(provider_tx_id),
                "created_by": str(created_by),
            })
        elif normalized.startswith("UPDATE ADMIN_USERS SET CREDITS = CREDITS -"):
            amount, user_id = params
            self.conn.users[str(user_id)]["credits"] -= int(amount)
        elif normalized.startswith("INSERT INTO VERIFICATION_RECEIPTS"):
            (
                request_id,
                user_id,
                request_fingerprint,
                claim_sha256,
                route,
                verdict,
                receipt_sha256,
                receipt_json,
                charged_credits,
            ) = params
            self.conn.receipts[str(request_id)] = {
                "request_id": str(request_id),
                "user_id": str(user_id),
                "request_fingerprint": str(request_fingerprint),
                "claim_sha256": str(claim_sha256),
                "route": str(route),
                "verdict": str(verdict),
                "receipt_sha256": str(receipt_sha256),
                "receipt": json.loads(str(receipt_json)),
                "charged_credits": int(charged_credits),
                "created_at": "test",
            }
        elif "SELECT RECEIPT FROM VERIFICATION_RECEIPTS" in normalized:
            request_id, user_id = map(str, params)
            row = self.conn.receipts.get(request_id)
            self.last_result = {"receipt": row["receipt"]} if row and row["user_id"] == user_id else None

    def fetchone(self):
        return self.last_result

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.ledger: list[dict] = []
        self.receipts: dict[str, dict] = {}
        self.executed: list[tuple[str, tuple]] = []
        self.commits = 0
        self.rollbacks = 0

    def add_user(
        self,
        user_id: str,
        *,
        credits: int,
        role: str = "user",
        purchased: bool = False,
    ) -> None:
        self.users[user_id] = {
            "id": user_id,
            "email": f"{user_id}@example.invalid",
            "role": role,
            "credits": credits,
            "paid_purchase_verified": purchased,
        }
        if credits:
            self.ledger.append({
                "user_id": user_id,
                "amount": credits,
                "provider_tx_id": "seed",
                "created_by": user_id,
            })

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def create_app(conn: FakeConnection) -> Flask:
    app = Flask(__name__)

    def require_session(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user_id = request.headers.get("X-Test-User")
            if not user_id:
                return jsonify({"error": "not authenticated"}), 401
            request.session_user_id = user_id
            return fn(*args, **kwargs)
        return wrapped

    register_verification_gateway_routes(
        app,
        require_session=require_session,
        get_connection=lambda: conn,
    )
    return app


def test_formal_prime_and_composite_are_decisive():
    assert formal_verify("173 is prime").verdict == "PROVEN"
    assert formal_verify("174 is prime").verdict == "CONTRADICTED"
    assert formal_verify("-173 is prime").verdict == "CONTRADICTED"


def test_formal_outside_64_bit_abstains():
    assert formal_verify("18446744073709551629 is prime").verdict == "UNPROVEN"


def test_formal_exact_rational_comparison():
    result = formal_verify("1/3 + 1/6 = 1/2")
    assert result.verdict == "PROVEN"
    assert result.details["left"]["exact"] == "1/2"
    assert result.details["wolframVerificationExpression"].startswith("VerificationTest[")


def test_auto_route_abstains_for_unknown_claim():
    result = verify_claim(claim="This design is beautiful", evidence={})
    assert result.route == "unknown"
    assert result.verdict == "UNPROVEN"


def test_runtime_match_is_not_promoted_without_source_authentication():
    result = runtime_verify({"expected": {"healthy": True}, "observed": {"healthy": True, "pid": 7}})
    assert result.verdict == "EVIDENCE_PRESENT_REVIEW_REQUIRED"
    assert result.details["sourceAuthenticityVerified"] is False


def test_runtime_mismatch_is_contradicted():
    result = runtime_verify({"expected": {"revision": "a"}, "observed": {"revision": "b"}})
    assert result.verdict == "CONTRADICTED"


def test_provenance_collapses_derivation_and_rejects_all_cycle():
    result = provenance_verify({
        "sources": [
            {"id": "a", "url": "https://a.example/original"},
            {"id": "b", "url": "https://b.example/copy", "derives_from": "a"},
            {"id": "c", "url": "https://c.example/independent"},
        ]
    })
    assert result.details["independentOriginCount"] == 2
    cycle = provenance_verify({
        "sources": [
            {"id": "a", "url": "https://a.example", "derives_from": "b"},
            {"id": "b", "url": "https://b.example", "derives_from": "a"},
        ]
    })
    assert cycle.verdict == "UNPROVEN"
    assert cycle.details["lineageIntegrityValid"] is False


def test_federated_real_hf_receipt_authenticates_and_replays():
    result = federated_verify("173 is prime", {"federatedReceipt": HF_173_RECEIPT})
    assert result.verdict == "PROVEN"
    assert result.details["receiptIntegrityValid"] is True
    assert result.details["issuerAuthenticated"] is True
    assert result.details["claimBound"] is True
    assert result.details["formalReplayVerified"] is True


def test_federated_tamper_and_wrong_claim_fail_closed():
    tampered = json.loads(json.dumps(HF_173_RECEIPT))
    tampered["verdict"] = "CONTRADICTED"
    assert federated_verify("173 is prime", {"federatedReceipt": tampered}).verdict == "UNPROVEN"
    wrong_claim = federated_verify("179 is prime", {"federatedReceipt": HF_173_RECEIPT})
    assert wrong_claim.verdict == "UNPROVEN"
    assert wrong_claim.details["issuerAuthenticated"] is True
    assert wrong_claim.details["claimBound"] is False


def test_federated_envelope_allows_public_hf_authority_metadata():
    result = verify_claim(
        claim="173 is prime",
        route="federated receipt",
        evidence={"federatedReceipt": HF_173_RECEIPT},
    )
    assert result.verdict == "PROVEN"


def test_float_and_credential_shaped_input_are_rejected():
    with pytest.raises(ValueError, match="floating-point"):
        verify_claim(claim="173 is prime", evidence={"value": 1.5})
    with pytest.raises(ValueError, match="credential-shaped"):
        verify_claim(claim="verify sk-abc123", evidence={})


def test_decisive_paid_receipt_requires_exact_source_revision(monkeypatch):
    user_id = str(uuid.uuid4())
    conn = FakeConnection()
    conn.add_user(user_id, credits=2)
    monkeypatch.delenv("SOVEREIGN_SOURCE_REVISION", raising=False)
    receipt, replayed = execute_paid_verification(
        lambda: conn,
        user_id=user_id,
        request_id=str(uuid.uuid4()),
        claim="173 is prime",
    )
    assert replayed is False
    assert receipt["verdict"] == "EVIDENCE_PRESENT_REVIEW_REQUIRED"
    assert receipt["details"]["decisiveVerifierResult"] == "PROVEN"
    assert receipt["sourceRevisionVerified"] is False


def test_paid_execution_charges_once_and_replays_same_request(monkeypatch):
    user_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    conn = FakeConnection()
    conn.add_user(user_id, credits=3)
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "a" * 40)
    first, replayed = execute_paid_verification(
        lambda: conn,
        user_id=user_id,
        request_id=request_id,
        claim="173 is prime",
    )
    assert replayed is False
    assert first["verdict"] == "PROVEN"
    assert first["billing"]["chargedCredits"] == 1
    assert conn.users[user_id]["credits"] == 2
    usage_entries = [row for row in conn.ledger if row["provider_tx_id"] == request_id]
    assert len(usage_entries) == 1
    second, replayed = execute_paid_verification(
        lambda: conn,
        user_id=user_id,
        request_id=request_id,
        claim="173 is prime",
    )
    assert replayed is True
    assert second["receiptSha256"] == first["receiptSha256"]
    assert conn.users[user_id]["credits"] == 2
    assert len([row for row in conn.ledger if row["provider_tx_id"] == request_id]) == 1


def test_same_request_id_with_different_input_conflicts(monkeypatch):
    user_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    conn = FakeConnection()
    conn.add_user(user_id, credits=3)
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "b" * 40)
    execute_paid_verification(lambda: conn, user_id=user_id, request_id=request_id, claim="173 is prime")
    with pytest.raises(VerificationConflict):
        execute_paid_verification(lambda: conn, user_id=user_id, request_id=request_id, claim="174 is prime")


def test_missing_entitlement_and_insufficient_credits_are_separate(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "c" * 40)
    user_id = str(uuid.uuid4())
    conn = FakeConnection()
    conn.add_user(user_id, credits=0, purchased=False)
    with pytest.raises(VerificationEntitlementRequired):
        execute_paid_verification(
            lambda: conn,
            user_id=user_id,
            request_id=str(uuid.uuid4()),
            claim="173 is prime",
        )
    purchased_id = str(uuid.uuid4())
    purchased = FakeConnection()
    purchased.add_user(purchased_id, credits=0, purchased=True)
    with pytest.raises(VerificationPaymentRequired):
        execute_paid_verification(
            lambda: purchased,
            user_id=purchased_id,
            request_id=str(uuid.uuid4()),
            claim="173 is prime",
        )


def test_credit_cache_mismatch_fails_closed(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "d" * 40)
    user_id = str(uuid.uuid4())
    conn = FakeConnection()
    conn.add_user(user_id, credits=3)
    conn.ledger[0]["amount"] = 4
    with pytest.raises(VerificationCreditStateMismatch):
        execute_paid_verification(
            lambda: conn,
            user_id=user_id,
            request_id=str(uuid.uuid4()),
            claim="173 is prime",
        )
    assert conn.users[user_id]["credits"] == 3


def test_admin_entitlement_is_credit_exempt(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "e" * 40)
    user_id = str(uuid.uuid4())
    conn = FakeConnection()
    conn.add_user(user_id, credits=0, role="admin")
    receipt, replayed = execute_paid_verification(
        lambda: conn,
        user_id=user_id,
        request_id=str(uuid.uuid4()),
        claim="174 is prime",
    )
    assert replayed is False
    assert receipt["verdict"] == "CONTRADICTED"
    assert receipt["billing"]["chargedCredits"] == 0
    assert conn.ledger == []


def test_public_status_is_free_but_execution_requires_session(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "f" * 40)
    conn = FakeConnection()
    app = create_app(conn)
    client = app.test_client()
    status = client.get("/api/verification/status")
    assert status.status_code == 200
    assert status.get_json()["status"] == "READY"
    assert status.get_json()["federation"]["crossSystemKeyReuse"] is False
    paid = client.post(
        "/api/user/agent/verification/verify",
        json={"requestId": str(uuid.uuid4()), "claim": "173 is prime"},
    )
    assert paid.status_code == 401


def test_a2a_requires_version_and_can_execute_paid_verification(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "1" * 40)
    user_id = str(uuid.uuid4())
    conn = FakeConnection()
    conn.add_user(user_id, credits=2)
    app = create_app(conn)
    client = app.test_client()
    wrong = client.post(
        "/a2a/v1/verification:verify",
        headers={"X-Test-User": user_id},
        json={"requestId": str(uuid.uuid4()), "claim": "173 is prime"},
    )
    assert wrong.status_code == 400
    assert wrong.headers["A2A-Version"] == "1.0"
    good = client.post(
        "/a2a/v1/verification:verify",
        headers={"X-Test-User": user_id, "A2A-Version": "1.0"},
        json={"requestId": str(uuid.uuid4()), "claim": "173 is prime"},
    )
    assert good.status_code == 200
    assert good.headers["A2A-Version"] == "1.0"
    assert good.headers["X-Sovereign-A2A-Extension"] == "verification-v1"
    assert good.get_json()["receipt"]["verdict"] == "PROVEN"


def test_gateway_status_is_explicit_about_receipt_authority(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "2" * 40)
    status = gateway_status()
    assert status["receiptAuthority"] == "revision-bound-database-persistence"
    assert status["truthNotInferredFromAgreement"] is True
    assert status["federation"]["huggingFaceTrustAnchorKeyId"] == HF_173_RECEIPT["issuer"]["keyId"]


def test_mirrors_and_migration_contract_are_exact():
    root = Path(__file__).resolve().parents[2]
    canonical = root / "backend/agent_runtime/verification_gateway.py"
    mirror = root / "scripts/sovereign-backend/agent_runtime/verification_gateway.py"
    migration = root / "backend/migrations/052_verification_gateway.sql"
    migration_mirror = root / "scripts/sovereign-backend/migrations/052_verification_gateway.sql"
    assert canonical.read_bytes() == mirror.read_bytes()
    assert migration.read_bytes() == migration_mirror.read_bytes()
    sql = migration.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS verification_receipts" in sql
    assert "verification_usage" in sql
    assert "agent_usage_reservation" in sql
    assert "agent_usage_adjustment" in sql
    assert "agent_usage_refund" in sql


def test_a2a_agent_card_advertises_verification_skill():
    root = Path(__file__).resolve().parents[2]
    for relative in (
        "backend/agent_runtime/a2a_adapter.py",
        "scripts/sovereign-backend/agent_runtime/a2a_adapter.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert 'id="sovereign-verification"' in source
        assert "model agreement is never a truth rule" in source
