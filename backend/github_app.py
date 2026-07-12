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

@dataclass(frozen=True)
class CreditBalance:
    installation_id: int
    account_login: str
    credits: int
    plan: str
    updated_at: datetime


def get_installation_credits(
    installation_id: int,
    get_connection: Callable,
) -> CreditBalance | None:
    """Get credit balance for an installation."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT installation_id, account_login, credits, plan, updated_at
                FROM github_app_credits
                WHERE installation_id = %s
            """, (installation_id,))
            row = cur.fetchone()
            if row:
                return CreditBalance(
                    installation_id=row[0],
                    account_login=row[1],
                    credits=row[2],
                    plan=row[3],
                    updated_at=row[4],
                )
    finally:
        conn.close()
    return None


def deduct_credits(
    installation_id: int,
    amount: int,
    action: str,
    get_connection: Callable,
) -> bool:
    """Deduct credits from an installation."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Check current balance
            cur.execute("""
                SELECT credits FROM github_app_credits
                WHERE installation_id = %s
                FOR UPDATE
            """, (installation_id,))
            row = cur.fetchone()
            
            if not row or row[0] < amount:
                return False
            
            # Deduct credits
            cur.execute("""
                UPDATE github_app_credits
                SET credits = credits - %s, updated_at = NOW()
                WHERE installation_id = %s
            """, (amount, installation_id))
            
            # Log transaction
            cur.execute("""
                INSERT INTO github_app_credit_transactions
                (installation_id, amount, action, created_at)
                VALUES (%s, %s, %s, NOW())
            """, (installation_id, -amount, action))
            
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def create_credit_account(
    installation_id: int,
    account_login: str,
    plan: str = "free",
    initial_credits: int = 10,
    get_connection: Callable,
) -> bool:
    """Create a credit account for a new installation."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO github_app_credits
                (installation_id, account_login, credits, plan, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (installation_id) DO NOTHING
            """, (installation_id, account_login, initial_credits, plan))
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
        
        create_credit_account(
            installation_id=installation_id,
            account_login=account_login,
            plan=plan,
            initial_credits=initial_credits,
            get_connection=get_connection,
        )
        
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
        finally:
            conn.close()
        
        return {
            "ok": True,
            "action": "installation_deleted",
            "installation_id": installation_id,
        }
    
    elif action == "suspended":
        return {
            "ok": True,
            "action": "installation_suspended",
            "installation_id": installation_id,
        }
    
    elif action == "unsuspended":
        return {
            "ok": True,
            "action": "installation_unsuspended",
            "installation_id": installation_id,
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
    account_login = marketplace_purchase.get("account", {}).get("login", "")
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
        # Find or create credit account by account_login
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE github_app_credits
                    SET plan = %s, updated_at = NOW()
                    WHERE account_login = %s
                    RETURNING installation_id
                """, (plan, account_login))
                row = cur.fetchone()
                
                if not row:
                    # Create new account
                    cur.execute("""
                        INSERT INTO github_app_credits
                        (installation_id, account_login, credits, plan, updated_at)
                        SELECT 
                            COALESCE(MAX(installation_id), 0) + 1,
                            %s, %s, %s, NOW()
                        FROM github_app_credits
                    """, (account_login, credits, plan))
            conn.commit()
        finally:
            conn.close()
        
        return {
            "ok": True,
            "action": "plan_updated",
            "account": account_login,
            "plan": plan,
            "credits": credits,
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
            return jsonify(result)
        
        elif event == "marketplace_purchase":
            result = handle_marketplace_purchase(
                action=payload.get("action", ""),
                marketplace_purchase=payload.get("marketplace_purchase", {}),
                get_connection=get_connection,
            )
            return jsonify(result)
        
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
                "updated_at": balance.updated_at.isoformat(),
            },
        })
    
    @app.route("/api/github-app/installations/<int:installation_id>/deduct", methods=["POST"])
    @require_admin
    def github_app_deduct_credits(installation_id: int):
        """Deduct credits from an installation."""
        body = request.get_json() or {}
        amount = int(body.get("amount", 0))
        action = str(body.get("action", "unknown"))
        
        if amount <= 0:
            return jsonify({"error": "Amount must be positive"}), 400
        
        success = deduct_credits(
            installation_id=installation_id,
            amount=amount,
            action=action,
            get_connection=get_connection,
        )
        
        if not success:
            return jsonify({"error": "Insufficient credits"}), 402
        
        return jsonify({"ok": True, "deducted": amount, "action": action})
    
    @app.route("/api/auth/github-app/callback", methods=["GET"])
    def github_app_oauth_callback():
        """OAuth callback for GitHub App installation."""
        code = request.args.get("code", "")
        installation_id = request.args.get("installation_id", "")
        setup_action = request.args.get("setup_action", "")
        
        if setup_action == "install":
            # Installation completed
            return jsonify({
                "ok": True,
                "message": "Installation successful",
                "redirect_url": f"https://sovereign-studio.arelorian.de/dashboard?installed=true",
            })
        
        if code:
            # Exchange code for access token
            # This would typically involve the OAuth flow
            return jsonify({
                "ok": True,
                "message": "OAuth flow initiated",
                "redirect_url": "https://sovereign-studio.arelorian.de",
            })
        
        return jsonify({"ok": True, "message": "Callback received"})
    
    @app.route("/api/github-app/configured", methods=["GET"])
    def github_app_configured():
        """Check if GitHub App is configured."""
        configured = all([
            GITHUB_APP_ID,
            GITHUB_APP_CLIENT_ID,
            GITHUB_APP_CLIENT_SECRET,
        ])
        
        return jsonify({
            "configured": configured,
            "app_id": bool(GITHUB_APP_ID),
            "client_id": bool(GITHUB_APP_CLIENT_ID),
            "webhook_secret": bool(GITHUB_APP_WEBHOOK_SECRET),
        })
