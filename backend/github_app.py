"""GitHub App integration for Sovereign Studio Marketplace.

This module handles GitHub App webhooks, installation events,
and credit management for the Sovereign Studio service.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable
import os
import requests
import jwt

from flask import jsonify, request, Response


# ── Configuration ──────────────────────────────────────────────────────────────

GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_APP_CLIENT_ID = os.getenv("GITHUB_APP_CLIENT_ID", "")
GITHUB_APP_CLIENT_SECRET = os.getenv("GITHUB_APP_CLIENT_SECRET", "")
GITHUB_APP_WEBHOOK_SECRET = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "")
GITHUB_APP_PRIVATE_KEY_B64 = os.getenv("GITHUB_APP_PRIVATE_KEY", "")


# ── Private Key Management ────────────────────────────────────────────────────

def _get_private_key() -> bytes | None:
    """Decode the base64-encoded private key."""
    if not GITHUB_APP_PRIVATE_KEY_B64:
        return None
    try:
        # Handle escaped newlines in environment variable
        key = GITHUB_APP_PRIVATE_KEY_B64.replace("\\n", "\n")
        return base64.b64decode(key)
    except Exception:
        return None


def _create_jwt() -> str | None:
    """Create a JWT for GitHub API authentication."""
    private_key = _get_private_key()
    if not private_key:
        return None
    
    if not GITHUB_APP_ID:
        return None
    
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,  # 10 minutes
        "iss": GITHUB_APP_ID,
    }
    
    try:
        return jwt.encode(payload, private_key, algorithm="RS256")
    except Exception:
        return None


# ── Webhook Verification ──────────────────────────────────────────────────────

def verify_github_app_webhook(payload_bytes: bytes, signature: str) -> bool:
    """Verify the webhook signature using HMAC-SHA256."""
    if not GITHUB_APP_WEBHOOK_SECRET:
        return False
    
    expected_signature = "sha256=" + hmac.new(
        GITHUB_APP_WEBHOOK_SECRET.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


def require_github_app_webhook(f: Callable) -> Callable:
    """Decorator to require valid GitHub App webhook signature."""
    def wrapper(*args, **kwargs) -> Response | Any:
        payload = request.get_data()
        signature = request.headers.get("X-Hub-Signature-256", "")
        
        if not verify_github_app_webhook(payload, signature):
            return jsonify({"error": "Invalid webhook signature"}), 401
        
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


# ── Installation Management ───────────────────────────────────────────────────

@dataclass(frozen=True)
class Installation:
    id: int
    account_login: str
    account_type: str
    account_id: int
    created_at: datetime
    permissions: dict[str, str]
    events: list[str]


def get_installation(installation_id: int) -> Installation | None:
    """Get installation details from GitHub API."""
    jwt_token = _create_jwt()
    if not jwt_token:
        return None
    
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    try:
        response = requests.get(
            f"https://api.github.com/app/installations/{installation_id}",
            headers=headers,
            timeout=15,
        )
        if not response.ok:
            return None
        
        data = response.json()
        return Installation(
            id=data["id"],
            account_login=data["account"]["login"],
            account_type=data["account"]["type"],
            account_id=data["account"]["id"],
            created_at=datetime.fromisoformat(
                data["created_at"].replace("Z", "+00:00")
            ),
            permissions=data.get("permissions", {}),
            events=data.get("events", []),
        )
    except Exception:
        return None


def get_installation_token(installation_id: int) -> str | None:
    """Get access token for an installation."""
    jwt_token = _create_jwt()
    if not jwt_token:
        return None
    
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    try:
        response = requests.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers=headers,
            timeout=15,
        )
        if not response.ok:
            return None
        
        return response.json().get("token")
    except Exception:
        return None


def list_installations() -> list[Installation]:
    """List all installations for the app."""
    jwt_token = _create_jwt()
    if not jwt_token:
        return []
    
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    installations = []
    
    try:
        response = requests.get(
            "https://api.github.com/app/installations",
            headers=headers,
            timeout=15,
        )
        if not response.ok:
            return []
        
        for data in response.json():
            installations.append(Installation(
                id=data["id"],
                account_login=data["account"]["login"],
                account_type=data["account"]["type"],
                account_id=data["account"]["id"],
                created_at=datetime.fromisoformat(
                    data["created_at"].replace("Z", "+00:00")
                ),
                permissions=data.get("permissions", {}),
                events=data.get("events", []),
            ))
    except Exception:
        pass
    
    return installations


# ── Credit Management ────────────────────────────────────────────────────────


def _row_value(row: Any, key: str, index: int) -> Any:
    """Read both RealDictCursor rows and sequence rows without path-dependent behavior."""
    if isinstance(row, Mapping):
        return row.get(key)
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
        return row[index]
    raise TypeError("database row is neither a mapping nor a sequence")


@dataclass(frozen=True)
class CreditBalance:
    installation_id: int
    account_login: str
    credits: int
    plan: str
    status: str
    updated_at: datetime


class GitHubAppCreditConflict(RuntimeError):
    """One idempotency identity was reused with different credit semantics."""


def get_installation_credits(
    installation_id: int,
    get_connection: Callable,
) -> CreditBalance | None:
    """Get credit balance for an installation."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT installation_id, account_login, credits, plan, status, updated_at
                FROM github_app_credits
                WHERE installation_id = %s
            """, (installation_id,))
            row = cur.fetchone()
            if row:
                return CreditBalance(
                    installation_id=int(_row_value(row, "installation_id", 0)),
                    account_login=str(_row_value(row, "account_login", 1) or ""),
                    credits=int(_row_value(row, "credits", 2)),
                    plan=str(_row_value(row, "plan", 3) or "free"),
                    status=str(_row_value(row, "status", 4) or "suspended"),
                    updated_at=_row_value(row, "updated_at", 5),
                )
            return None
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def deduct_credits(
    installation_id: int,
    amount: int,
    action: str,
    idempotency_key: str,
    get_connection: Callable,
) -> dict[str, Any]:
    """Deduct credits exactly once from one locked installation account."""
    if installation_id <= 0 or amount <= 0 or not action or not idempotency_key:
        raise ValueError("installation, positive amount, action and idempotency key are required")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"github-app-credit:{idempotency_key}",),
            )
            cur.execute(
                """SELECT installation_id, amount, action
                   FROM github_app_credit_transactions
                   WHERE idempotency_key = %s::uuid
                   LIMIT 1""",
                (idempotency_key,),
            )
            existing = cur.fetchone()
            if existing:
                same_request = (
                    int(_row_value(existing, "installation_id", 0)) == installation_id
                    and int(_row_value(existing, "amount", 1)) == -amount
                    and str(_row_value(existing, "action", 2) or "") == action
                )
                conn.rollback()
                if not same_request:
                    raise GitHubAppCreditConflict(
                        "Idempotency-Key belongs to another GitHub App credit mutation"
                    )
                return {"ok": True, "duplicate": True, "remainingCredits": None}

            cur.execute(
                """SELECT credits, status FROM github_app_credits
                   WHERE installation_id = %s
                   FOR UPDATE""",
                (installation_id,),
            )
            row = cur.fetchone()
            current_credits = int(_row_value(row, "credits", 0)) if row else 0
            account_status = str(_row_value(row, "status", 1) or "suspended") if row else "missing"
            if not row or account_status != "active" or current_credits < amount:
                conn.rollback()
                return {
                    "ok": False,
                    "duplicate": False,
                    "remainingCredits": current_credits if row else None,
                }

            remaining_credits = current_credits - amount
            cur.execute(
                """UPDATE github_app_credits
                   SET credits = %s, updated_at = NOW()
                   WHERE installation_id = %s""",
                (remaining_credits, installation_id),
            )
            cur.execute(
                """INSERT INTO github_app_credit_transactions
                       (idempotency_key, installation_id, amount, action, created_at)
                   VALUES (%s::uuid, %s, %s, %s, NOW())""",
                (idempotency_key, installation_id, -amount, action),
            )
        conn.commit()
        return {
            "ok": True,
            "duplicate": False,
            "remainingCredits": remaining_credits,
        }
    except GitHubAppCreditConflict:
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_credit_account(
    installation_id: int,
    account_id: int,
    account_login: str,
    get_connection: Callable,
    plan: str = "free",
    initial_credits: int = 10,
) -> bool:
    """Create a credit account for a new installation."""
    if installation_id <= 0 or account_id <= 0 or not account_login or initial_credits < 0:
        return False
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO github_app_credits
                (installation_id, account_id, account_login, credits, plan, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (installation_id) DO UPDATE SET
                    account_id=EXCLUDED.account_id,
                    account_login=EXCLUDED.account_login,
                    status='active',
                    updated_at=NOW()
            """, (installation_id, account_id, account_login, initial_credits, plan))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


# ── Event Handlers ────────────────────────────────────────────────────────────

def handle_installation_event(
    action: str,
    installation: dict,
    get_connection: Callable,
) -> dict:
    """Handle installation lifecycle events."""
    installation_id = installation.get("id")
    account_login = installation.get("account", {}).get("login", "")
    account_type = installation.get("account", {}).get("type", "User")
    
    if action == "created":
        # New installation - create credit account
        plan = "free"
        initial_credits = 10
        
        # Check for Pro/Team plan
        # This would come from marketplace purchase
        
        created = create_credit_account(
            installation_id=int(installation_id or 0),
            account_id=int(installation.get("account", {}).get("id") or 0),
            account_login=account_login,
            plan=plan,
            initial_credits=initial_credits,
            get_connection=get_connection,
        )
        if not created:
            return {
                "ok": False,
                "action": "installation_account_create_failed",
                "installation_id": installation_id,
                "account": account_login,
            }
        return {
            "ok": True,
            "action": "installation_created",
            "installation_id": installation_id,
            "account": account_login,
            "plan": plan,
            "initial_credits": initial_credits,
        }
    
    elif action == "deleted":
        # Installation removed
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM github_app_credits
                    WHERE installation_id = %s
                """, (installation_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        
        return {
            "ok": True,
            "action": "installation_deleted",
            "installation_id": installation_id,
        }
    
    elif action in {"suspended", "unsuspended"}:
        target_status = "suspended" if action == "suspended" else "active"
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE github_app_credits
                       SET status=%s, updated_at=NOW()
                       WHERE installation_id=%s
                       RETURNING installation_id""",
                    (target_status, installation_id),
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return {
                        "ok": False,
                        "action": "installation_not_found",
                        "installation_id": installation_id,
                    }
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return {
            "ok": True,
            "action": f"installation_{action}",
            "installation_id": installation_id,
            "status": target_status,
        }
    
    return {
        "ok": True,
        "action": "installation_updated",
        "installation_id": installation_id,
    }


def handle_marketplace_purchase(
    action: str,
    marketplace_purchase: dict,
    get_connection: Callable,
) -> dict:
    """Handle marketplace purchase events."""
    account = marketplace_purchase.get("account", {})
    account_login = str(account.get("login") or "")
    account_id = int(account.get("id") or 0)
    plan = marketplace_purchase.get("plan", {}).get("name", "free")
    unit_count = marketplace_purchase.get("unit_count", 1)
    
    # Map plans to credits
    plan_credits = {
        "free": 10,
        "pro": 100,
        "team": 500,
        "enterprise": 2000,
    }
    
    credits = plan_credits.get(plan.lower(), 10) * unit_count
    
    if action == "purchased" or action == "changed":
        if account_id <= 0 or not account_login:
            return {
                "ok": False,
                "action": "marketplace_account_invalid",
                "account": account_login,
            }
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE github_app_credits
                    SET account_login = %s, plan = %s, updated_at = NOW()
                    WHERE account_id = %s
                    RETURNING installation_id
                """, (account_login, plan, account_id))
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return {
                        "ok": False,
                        "action": "installation_required",
                        "account": account_login,
                        "account_id": account_id,
                    }
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        
        return {
            "ok": True,
            "action": "plan_updated",
            "account": account_login,
            "account_id": account_id,
            "plan": plan,
            "plan_credit_allowance": credits,
            "credits_applied": 0,
        }
    
    return {"ok": True, "action": "ignored"}


# ── Flask Routes ─────────────────────────────────────────────────────────────

def register_github_app_routes(
    app: Any,
    *,
    require_admin: Callable,
    get_connection: Callable,
) -> None:
    """Register GitHub App routes."""
    
    @app.route("/api/webhooks/github-app", methods=["POST"])
    @require_github_app_webhook
    def github_app_webhook():
        """Handle GitHub App webhook events."""
        event = request.headers.get("X-GitHub-Event", "")
        payload = request.get_json() or {}
        installation = payload.get("installation", {})
        
        if event == "installation" or event == "installation_repositories":
            result = handle_installation_event(
                action=payload.get("action", ""),
                installation=installation,
                get_connection=get_connection,
            )
            return jsonify(result), 200 if result.get("ok") else 409
        
        elif event == "marketplace_purchase":
            result = handle_marketplace_purchase(
                action=payload.get("action", ""),
                marketplace_purchase=payload.get("marketplace_purchase", {}),
                get_connection=get_connection,
            )
            return jsonify(result), 200 if result.get("ok") else 409
        
        elif event == "pull_request":
            # Handle PR events if needed
            return jsonify({"ok": True, "event": event})
        
        return jsonify({"ok": True, "event": event})
    
    @app.route("/api/github-app/installations", methods=["GET"])
    @require_admin
    def github_app_list_installations():
        """List all app installations (admin only)."""
        installations = list_installations()
        return jsonify({
            "ok": True,
            "installations": [
                {
                    "id": i.id,
                    "account_login": i.account_login,
                    "account_type": i.account_type,
                    "created_at": i.created_at.isoformat(),
                }
                for i in installations
            ],
        })
    
    @app.route("/api/github-app/installations/<int:installation_id>", methods=["GET"])
    @require_admin
    def github_app_get_installation(installation_id: int):
        """Get installation details."""
        installation = get_installation(installation_id)
        if not installation:
            return jsonify({"error": "Installation not found"}), 404
        
        return jsonify({
            "ok": True,
            "installation": {
                "id": installation.id,
                "account_login": installation.account_login,
                "account_type": installation.account_type,
                "permissions": installation.permissions,
                "events": installation.events,
            },
        })
    
    @app.route("/api/github-app/installations/<int:installation_id>/credits", methods=["GET"])
    @require_admin
    def github_app_get_credits(installation_id: int):
        """Get credit balance for an installation."""
        balance = get_installation_credits(
            installation_id=installation_id,
            get_connection=get_connection,
        )
        
        if not balance:
            return jsonify({"error": "Credit account not found"}), 404
        
        return jsonify({
            "ok": True,
            "credits": {
                "installation_id": balance.installation_id,
                "account": balance.account_login,
                "balance": balance.credits,
                "plan": balance.plan,
                "status": balance.status,
                "updated_at": balance.updated_at.isoformat(),
            },
        })
    
    @app.route("/api/github-app/installations/<int:installation_id>/deduct", methods=["POST"])
    @require_admin
    def github_app_deduct_credits(installation_id: int):
        """Deduct credits from an installation."""
        body = request.get_json() or {}
        try:
            amount = int(body.get("amount", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Amount must be an integer"}), 400
        action = str(body.get("action") or "").strip()[:160]
        raw_idempotency_key = str(request.headers.get("Idempotency-Key") or "").strip()
        try:
            idempotency_key = str(uuid.UUID(raw_idempotency_key))
        except (ValueError, AttributeError, TypeError):
            return jsonify({"error": "Idempotency-Key must be a UUID"}), 400
        if amount <= 0 or not action:
            return jsonify({"error": "Positive amount and action are required"}), 400
        try:
            result = deduct_credits(
                installation_id=installation_id,
                amount=amount,
                action=action,
                idempotency_key=idempotency_key,
                get_connection=get_connection,
            )
        except GitHubAppCreditConflict as exc:
            return jsonify({"error": str(exc), "blocker": "idempotency_conflict"}), 409
        if not result["ok"]:
            return jsonify({
                "error": "Insufficient credits or installation not found",
                "remainingCredits": result.get("remainingCredits"),
            }), 402
        return jsonify({
            "ok": True,
            "deducted": 0 if result["duplicate"] else amount,
            "duplicate": bool(result["duplicate"]),
            "remainingCredits": result.get("remainingCredits"),
            "action": action,
            "idempotencyKey": idempotency_key,
        })
    
    @app.route("/api/auth/github-app/callback", methods=["GET"])
    def github_app_oauth_callback():
        """OAuth callback for GitHub App installation."""
        code = request.args.get("code", "")
        installation_id = request.args.get("installation_id", "")
        setup_action = request.args.get("setup_action", "")
        
        if setup_action == "install":
            try:
                parsed_installation_id = int(installation_id)
            except (TypeError, ValueError):
                parsed_installation_id = 0
            if parsed_installation_id <= 0:
                return jsonify({
                    "ok": False,
                    "error": "GitHub installation_id is required",
                    "blocker": "github_app_installation_id_missing",
                }), 400
            return jsonify({
                "ok": True,
                "status": "installation_redirect_received",
                "installation_id": parsed_installation_id,
                "authenticationEstablished": False,
                "nextAction": "Wait for the signed installation webhook before enabling the installation.",
                "redirect_url": "https://chat.arelorian.de/?github_app_installed=pending",
            })
        if code:
            return jsonify({
                "ok": False,
                "error": "GitHub App OAuth code exchange is not implemented on this route",
                "blocker": "github_app_oauth_exchange_unavailable",
                "authenticationEstablished": False,
            }), 501
        return jsonify({
            "ok": False,
            "error": "GitHub App callback has no verifiable installation action",
            "blocker": "github_app_callback_unverified",
            "authenticationEstablished": False,
        }), 400
    
    @app.route("/api/github-app/configured", methods=["GET"])
    def github_app_configured():
        """Check if GitHub App is configured."""
        api_configured = bool(GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY_B64)
        oauth_configured = bool(GITHUB_APP_CLIENT_ID and GITHUB_APP_CLIENT_SECRET)
        webhook_configured = bool(GITHUB_APP_WEBHOOK_SECRET)
        return jsonify({
            "configured": bool(api_configured and oauth_configured and webhook_configured),
            "apiConfigured": api_configured,
            "oauthConfigured": oauth_configured,
            "webhookConfigured": webhook_configured,
            "app_id": bool(GITHUB_APP_ID),
            "client_id": bool(GITHUB_APP_CLIENT_ID),
            "client_secret": bool(GITHUB_APP_CLIENT_SECRET),
            "private_key": bool(GITHUB_APP_PRIVATE_KEY_B64),
            "webhook_secret": webhook_configured,
        })
