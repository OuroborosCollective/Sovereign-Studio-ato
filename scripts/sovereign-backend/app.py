#!/usr/bin/env python3
"""
Sovereign Backend — Flask app.
Serves OpenHands proxy routes + Admin API routes.

Issue #460: Admin API (psycopg2, real DB)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading
import time
import urllib.parse
import uuid
from functools import wraps

import psycopg2
import psycopg2.extras
import psycopg2.pool
from flask import Flask, jsonify, request, make_response, g
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app,
     origins=[
         "https://chat.arelorian.de",
         "https://arelorian.de",
         "https://sovereign-backend.arelorian.de",
     ],
     supports_credentials=True)

# ── Config ────────────────────────────────────────────────────────────────────

ADMIN_API_KEY  = os.getenv("ADMIN_API_KEY", "")
LLM_PROXY_KEY  = os.getenv("LLM_PROXY_KEY", "")
OPENHANDS_API_URL = os.getenv("OPENHANDS_API_URL", "http://127.0.0.1:3000")

POSTGRES_HOST  = os.getenv("POSTGRES_HOST", "db")
POSTGRES_PORT  = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB    = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_USER  = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASS  = os.getenv("POSTGRES_PASSWORD", "")

# ── DB pool ───────────────────────────────────────────────────────────────────

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()

def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    1, 10,
                    host=POSTGRES_HOST,
                    port=POSTGRES_PORT,
                    dbname=POSTGRES_DB,
                    user=POSTGRES_USER,
                    password=POSTGRES_PASS,
                )
    return _pool


def query(sql: str, params=None, *, one=False, write=False):
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if write:
                conn.commit()
                return None
            if one:
                return cur.fetchone()
            return cur.fetchall()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ── Auth ──────────────────────────────────────────────────────────────────────


def _admin_payload(row, auth_mode: str) -> dict:
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "role": row["role"],
        "authMode": auth_mode,
    }


def _lookup_admin_api_key(token: str) -> dict | None:
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    admin = query(
        """SELECT a.id, a.email, a.role
           FROM admin_users a
           JOIN admin_api_keys k ON k.admin_id = a.id
           WHERE k.key_hash = %s AND a.role IN ('admin','superadmin')
           LIMIT 1""",
        (key_hash,), one=True,
    )
    if not admin:
        return None
    query(
        "UPDATE admin_api_keys SET last_used_at = NOW() WHERE key_hash = %s",
        (key_hash,), write=True,
    )
    return _admin_payload(admin, "admin_api_key")


def _lookup_bootstrap_admin(token: str) -> dict | None:
    if not ADMIN_API_KEY or not hmac.compare_digest(token, ADMIN_API_KEY):
        return None

    bootstrap_email = os.getenv("ADMIN_BOOTSTRAP_ADMIN_EMAIL", "").strip()
    if bootstrap_email:
        admin = query(
            """SELECT id, email, role
               FROM admin_users
               WHERE email = %s AND role IN ('admin','superadmin')
               LIMIT 1""",
            (bootstrap_email,), one=True,
        )
        return _admin_payload(admin, "bootstrap_env_admin") if admin else None

    count_row = query(
        "SELECT COUNT(*) AS n FROM admin_users WHERE role IN ('admin','superadmin')",
        one=True,
    )
    if int(count_row["n"]) != 1:
        return None

    admin = query(
        """SELECT id, email, role
           FROM admin_users
           WHERE role IN ('admin','superadmin')
           LIMIT 1""",
        one=True,
    )
    return _admin_payload(admin, "bootstrap_single_admin") if admin else None


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        g.current_admin = None
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if not token:
            return jsonify({"error": "Nicht autorisiert"}), 401

        admin = _lookup_admin_api_key(token)
        if not admin:
            admin = _lookup_bootstrap_admin(token)

        if not admin:
            return jsonify({
                "error": "API-Key keinem Admin zugeordnet",
                "hint": "Admin-Key in admin_api_keys hinterlegen oder ADMIN_BOOTSTRAP_ADMIN_EMAIL eindeutig setzen",
            }), 401

        g.current_admin = admin
        return f(*args, **kwargs)
    return decorated


def get_current_admin() -> dict | None:
    """Get the currently authenticated admin from request-local Flask context."""
    return getattr(g, "current_admin", None)


# ── Pagination helper ─────────────────────────────────────────────────────────

def paginate(page_raw, limit_raw, default_limit=50):
    try:
        page  = max(1, int(page_raw))
    except (ValueError, TypeError):
        page  = 1
    try:
        limit = max(1, min(200, int(limit_raw)))
    except (ValueError, TypeError):
        limit = default_limit
    offset = (page - 1) * limit
    return page, limit, offset


# ── Audit helper ──────────────────────────────────────────────────────────────

def audit(action: str, target_id: str | None, changes: dict):
    """Write an audit log entry with the REAL current admin actor."""
    admin = get_current_admin()
    
    if admin:
        admin_id = admin["id"]
        admin_email = admin["email"]
    else:
        # System-initiated actions (e.g., from non-authenticated endpoints)
        admin_id = "system"
        admin_email = "system"
    
    query(
        """INSERT INTO audit_log (admin_id, admin_email, action, target_id, changes)
           VALUES (%s, %s, %s, %s, %s::jsonb)""",
        (admin_id, admin_email, action, target_id,
         psycopg2.extras.Json(changes)),
        write=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN API
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/admin/ping")
@require_admin
def admin_ping():
    return jsonify({"ok": True, "role": "admin"})


# ── Users ─────────────────────────────────────────────────────────────────────

@app.route("/api/admin/users")
@require_admin
def admin_users():
    page, limit, offset = paginate(
        request.args.get("page", 1),
        request.args.get("limit", 50),
    )
    search = request.args.get("search", "").strip()

    if search:
        where  = "WHERE email ILIKE %s OR display_name ILIKE %s"
        like   = "%" + search + "%"
        params = (like, like, limit, offset)
        cparams = (like, like)
    else:
        where = cparams = ""
        params = (limit, offset)

    if search:
        total_row = query(
            f"SELECT COUNT(*) AS n FROM admin_users {where}",
            cparams, one=True,
        )
        rows = query(
            f"""SELECT id::text, email, display_name AS "displayName", role,
                       credits, subscription_status AS "subscriptionStatus",
                       is_banned AS "isBanned",
                       to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "createdAt",
                       NULL AS "lastActiveAt"
                FROM admin_users {where}
                ORDER BY created_at DESC LIMIT %s OFFSET %s""",
            params,
        )
    else:
        total_row = query("SELECT COUNT(*) AS n FROM admin_users", one=True)
        rows = query(
            """SELECT id::text, email, display_name AS "displayName", role,
                      credits, subscription_status AS "subscriptionStatus",
                      is_banned AS "isBanned",
                      to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "createdAt",
                      NULL AS "lastActiveAt"
               FROM admin_users
               ORDER BY created_at DESC LIMIT %s OFFSET %s""",
            (limit, offset),
        )

    return jsonify({
        "users": [dict(r) for r in rows],
        "total": int(total_row["n"]),
        "page":  page,
    })


@app.route("/api/admin/users/<uid>", methods=["PATCH"])
@require_admin
def admin_update_user(uid):
    body = request.get_json(force=True) or {}
    if "credits" in body:
        return jsonify({
            "error": "credits dürfen nur über credit-adjustment und append-only ledger geändert werden",
            "blocker": "credit_ledger_required",
        }), 400
    allowed = {"role", "subscriptionStatus", "isBanned"}
    col_map = {
        "role":               "role",
        "subscriptionStatus": "subscription_status",
        "isBanned":           "is_banned",
    }
    sets, vals = [], []
    for k, v in body.items():
        if k in allowed and k in col_map:
            sets.append(f"{col_map[k]} = %s")
            vals.append(v)
    if not sets:
        return jsonify({"error": "Keine Felder zum Aktualisieren"}), 400

    vals.append(uid)
    query(
        f"UPDATE admin_users SET {', '.join(sets)} WHERE id = %s::uuid",
        vals, write=True,
    )
    audit("admin_update_user", uid, body)
    user = query(
        """SELECT id::text, email, display_name AS "displayName", role,
                  credits, subscription_status AS "subscriptionStatus",
                  is_banned AS "isBanned",
                  to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "createdAt",
                  NULL AS "lastActiveAt"
           FROM admin_users WHERE id = %s::uuid""",
        (uid,), one=True,
    )
    return jsonify({"ok": True, "user": dict(user)})


@app.route("/api/admin/users/<uid>/credit-adjustment", methods=["POST"])
@require_admin
def admin_credit_adjustment(uid):
    """
    Credit adjustment via append-only ledger.
    Amounts are ALWAYS recorded in the ledger with the real value.
    Balance is computed from ledger entries, not stored directly.
    """
    body   = request.get_json(force=True) or {}
    amount = body.get("amount", 0)
    reason = body.get("reason", "")
    
    if not amount:
        return jsonify({"error": "amount darf nicht 0 sein"}), 400
    if not reason:
        return jsonify({"error": "reason fehlt"}), 400

    # Get user info
    user = query(
        "SELECT id, email, credits FROM admin_users WHERE id = %s::uuid",
        (uid,), one=True,
    )
    if not user:
        return jsonify({"error": "User nicht gefunden"}), 404

    # Create append-only ledger entry with the REAL amount
    sign_desc = "+" if amount > 0 else ""
    ledger_type = "manual_adjustment"
    if amount > 0:
        ledger_type = "bonus"
    else:
        ledger_type = "correction"
    
    ledger_desc = f"Admin {sign_desc}{amount}: {reason}"
    
    # Insert ledger entry with the ACTUAL amount (not 0!)
    query(
        """INSERT INTO credit_ledger
              (user_id, type, amount, reason, created_by)
           VALUES (%s::uuid, %s, %s, %s, %s)""",
        (uid, ledger_type, amount, ledger_desc, get_current_admin()["id"]),
        write=True,
    )
    
    # Calculate new balance from ledger (append-only principle)
    balance_row = query(
        """SELECT COALESCE(SUM(amount), 0) as balance FROM credit_ledger WHERE user_id = %s::uuid""",
        (uid,), one=True,
    )
    new_balance = max(0, int(balance_row["balance"]))
    
    # Update admin_users.credits as a CACHED value (for fast reads)
    # The CACHE MUST be consistent with the ledger
    query(
        "UPDATE admin_users SET credits = %s WHERE id = %s::uuid",
        (new_balance, uid), write=True,
    )
    
    audit("admin_credit_adjustment", uid, {
        "amount": amount,
        "reason": reason,
        "ledgerType": ledger_type,
        "newBalance": new_balance,
    })
    
    return jsonify({
        "ok": True,
        "newBalance": new_balance,
        "ledgerEntry": {
            "type": ledger_type,
            "amount": amount,
            "reason": ledger_desc,
        }
    })


# ── Transactions ──────────────────────────────────────────────────────────────

@app.route("/api/admin/transactions")
@require_admin
def admin_transactions():
    page, limit, offset = paginate(
        request.args.get("page", 1),
        request.args.get("limit", 50),
    )
    wheres, params = [], []
    if uid := request.args.get("user_id"):
        wheres.append("user_id = %s::uuid")
        params.append(uid)
    if ttype := request.args.get("type"):
        wheres.append("type = %s")
        params.append(ttype)
    w = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    total_row = query(
        f"SELECT COUNT(*) AS n FROM transactions {w}",
        params or None, one=True,
    )
    rows = query(
        f"""SELECT id::text, user_id::text AS "userId", user_email AS "userEmail",
                   type, amount, currency, status, description,
                   to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "createdAt"
            FROM transactions {w}
            ORDER BY created_at DESC LIMIT %s OFFSET %s""",
        params + [limit, offset],
    )
    return jsonify({
        "transactions": [dict(r) for r in rows],
        "total": int(total_row["n"]),
        "page":  page,
    })


# ── Billing stats ─────────────────────────────────────────────────────────────

@app.route("/api/admin/billing/stats")
@require_admin
def admin_billing_stats():
    active_subs = query(
        "SELECT COUNT(*) AS n FROM admin_users WHERE subscription_status = 'active'",
        one=True,
    )
    total_credits = query(
        "SELECT COALESCE(SUM(credits), 0) AS n FROM admin_users",
        one=True,
    )
    total_rev = query(
        "SELECT COALESCE(SUM(amount), 0) AS n FROM transactions WHERE status = 'completed' AND amount > 0",
        one=True,
    )
    return jsonify({
        "mrr":                 0,
        "activeSubscriptions": int(active_subs["n"]),
        "totalCredits":        int(total_credits["n"]),
        "totalRevenue":        float(total_rev["n"]),
        "churnRate":           0.0,
    })


# ── Launcher tools ────────────────────────────────────────────────────────────

@app.route("/api/admin/launcher/tools")
@require_admin
def admin_launcher_tools():
    rows = query(
        """SELECT id::text, label, disabled,
                  badge, sort_order AS "sortOrder"
           FROM launcher_overrides
           ORDER BY sort_order ASC"""
    )
    return jsonify({"tools": [dict(r) for r in rows]})


@app.route("/api/admin/launcher/tools/<tid>", methods=["PATCH"])
@require_admin
def admin_update_launcher_tool(tid):
    body = request.get_json(force=True) or {}
    col_map = {
        "disabled":  "disabled",
        "badge":     "badge",
        "sortOrder": "sort_order",
    }
    sets, vals = [], []
    for k, v in body.items():
        if k in col_map:
            sets.append(f"{col_map[k]} = %s")
            vals.append(v)
    if not sets:
        return jsonify({"error": "Keine Felder"}), 400
    sets.append("updated_at = NOW()")
    vals.append(tid)
    query(
        f"UPDATE launcher_overrides SET {', '.join(sets)} WHERE id = %s::uuid",
        vals, write=True,
    )
    audit("admin_update_launcher_tool", tid, body)
    return jsonify({"ok": True})


# ── LLM routes ────────────────────────────────────────────────────────────────

@app.route("/api/admin/llm/routes")
@require_admin
def admin_llm_routes():
    rows = query(
        """SELECT id::text, model_id AS "modelId", model_name AS "modelName",
                  provider, credits_per_unit AS "creditsPerUnit",
                  disabled, priority
           FROM llm_routes
           ORDER BY priority ASC"""
    )
    return jsonify({"routes": [dict(r) for r in rows]})


@app.route("/api/admin/llm/routes/<rid>", methods=["PATCH"])
@require_admin
def admin_update_llm_route(rid):
    body = request.get_json(force=True) or {}
    col_map = {
        "creditsPerUnit": "credits_per_unit",
        "disabled":       "disabled",
        "priority":       "priority",
    }
    sets, vals = [], []
    for k, v in body.items():
        if k in col_map:
            sets.append(f"{col_map[k]} = %s")
            vals.append(v)
    if not sets:
        return jsonify({"error": "Keine Felder"}), 400
    sets.append("updated_at = NOW()")
    vals.append(rid)
    query(
        f"UPDATE llm_routes SET {', '.join(sets)} WHERE id = %s::uuid",
        vals, write=True,
    )
    audit("admin_update_llm_route", rid, body)
    return jsonify({"ok": True})


# ── Audit log ─────────────────────────────────────────────────────────────────

@app.route("/api/admin/audit-log")
@require_admin
def admin_audit_log():
    page, limit, offset = paginate(
        request.args.get("page", 1),
        request.args.get("limit", 50),
    )
    total_row = query("SELECT COUNT(*) AS n FROM audit_log", one=True)
    rows = query(
        """SELECT id::text, admin_id AS "adminId", admin_email AS "adminEmail",
                  action, target_id AS "targetId", changes,
                  to_char(created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "createdAt"
           FROM audit_log
           ORDER BY created_at DESC LIMIT %s OFFSET %s""",
        (limit, offset),
    )
    return jsonify({
        "entries": [dict(r) for r in rows],
        "total":   int(total_row["n"]),
        "page":    page,
    })


# ═════════════════════════════════════════════════════════════════════════════
# RUNTIME SETTINGS - Worker, BYOK, CORS (Persisted + Dynamic)
# ═════════════════════════════════════════════════════════════════════════════

import json as _json

# Config file path (can be overridden via environment)
_CONFIG_FILE = os.getenv("RUNTIME_CONFIG_FILE", "/opt/sovereign/config/runtime.json")

# Default runtime config
_DEFAULT_RUNTIME_CONFIG: dict = {
    "byok_mode": "user-key",  # system-key, user-key, disabled
    "cors_origins": [
        "https://chat.arelorian.de",
        "https://arelorian.de",
        "https://sovereign-backend.arelorian.de",
    ],
    "worker_health": "healthy",
    "last_deploy_at": None,
    "version": "1.0",
}

# Load config from file or use defaults
def _load_runtime_config() -> dict:
    """Load runtime config from file with fallback to defaults."""
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, "r") as f:
                loaded = _json.load(f)
                # Merge with defaults for any missing keys
                config = dict(_DEFAULT_RUNTIME_CONFIG)
                config.update(loaded)
                return config
    except Exception:
        pass
    return dict(_DEFAULT_RUNTIME_CONFIG)

# Save config to file
def _save_runtime_config(config: dict) -> bool:
    """Save runtime config to file. Returns True on success."""
    try:
        # Ensure directory exists
        config_dir = os.path.dirname(_CONFIG_FILE)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
        
        with open(_CONFIG_FILE, "w") as f:
            _json.dump(config, f, indent=2)
        return True
    except Exception:
        return False

# Load initial config
_RUNTIME_CONFIG: dict = _load_runtime_config()


def _mask_secrets(config: dict) -> dict:
    """Mask sensitive values in config for display."""
    masked = dict(config)
    for key in masked:
        if "secret" in key.lower() or "key" in key.lower() or "token" in key.lower():
            val = str(masked[key] or "")
            if len(val) > 4:
                masked[key] = val[:2] + "*" * (len(val) - 4) + val[-2:]
            else:
                masked[key] = "****"
    return masked


def _update_cors_from_config():
    """Update Flask-CORS middleware with current runtime config origins."""
    global app
    try:
        from flask import Flask
        # Rebuild CORS with current origins
        origins = _RUNTIME_CONFIG.get("cors_origins", [])
        if origins:
            # Create new CORS instance with updated origins
            from flask_cors import CORS
            # Remove existing CORS
            app.extensions = {k: v for k, v in app.extensions.items() if k != 'CORS'}
            # Re-apply with new origins
            CORS(app, origins=origins, supports_credentials=True)
            return True
    except Exception:
        return False
    return False


@app.route("/api/admin/runtime/config")
@require_admin
def admin_runtime_config():
    """Get runtime configuration (secrets masked)."""
    return jsonify({
        "ok": True,
        "config": _mask_secrets(_RUNTIME_CONFIG),
        "persisted": os.path.exists(_CONFIG_FILE),
        "configFile": _CONFIG_FILE,
        "corsActive": True,  # Indicates if CORS is being applied from config
    })


@app.route("/api/admin/runtime/config", methods=["PATCH"])
@require_admin
def admin_update_runtime_config():
    """Update runtime configuration with validation, persistence, and CORS update."""
    global _RUNTIME_CONFIG
    
    body = request.get_json(force=True) or {}
    allowed_keys = {"byok_mode", "cors_origins"}
    
    # Filter allowed fields
    updates = {k: v for k, v in body.items() if k in allowed_keys}
    
    if not updates:
        return jsonify({"error": "Keine erlaubten Felder zum Aktualisieren"}), 400
    
    # Validate BYOK mode
    if "byok_mode" in updates:
        if updates["byok_mode"] not in ("system-key", "user-key", "disabled"):
            return jsonify({"error": "Ungültiger BYOK-Modus. Erlaubt: system-key, user-key, disabled"}), 400
    
    # Validate CORS origins - block wildcard with credentials
    if "cors_origins" in updates:
        origins = updates["cors_origins"]
        if not isinstance(origins, list):
            return jsonify({"error": "cors_origins muss eine Liste sein"}), 400
        
        for origin in origins:
            if origin.strip() == "*":
                return jsonify({
                    "error": "Wildcard-Origin (*) ist nicht erlaubt. Bitte spezifische Domains angeben.",
                    "blocker": "cors_wildcard_blocked"
                }), 400
            
            # Check for credentials/authorization with suspicious patterns
            if any(pattern in origin.lower() for pattern in ["token=", "key=", "auth="]):
                return jsonify({
                    "error": "Origin darf keine Auth-Parameter enthalten.",
                    "blocker": "cors_auth_in_origin_blocked"
                }), 400
    
    # Apply updates to in-memory config
    _RUNTIME_CONFIG.update(updates)
    
    # Persist to file
    if not _save_runtime_config(_RUNTIME_CONFIG):
        return jsonify({
            "error": "Konfiguration gespeichert, aber Persistenz fehlgeschlagen",
            "ok": True,
            "config": _mask_secrets(_RUNTIME_CONFIG),
            "persisted": False,
        }), 200
    
    # ACTUALLY update CORS middleware if origins changed
    cors_updated = False
    if "cors_origins" in updates:
        cors_updated = _update_cors_from_config()
        if not cors_updated:
            # Return warning but still succeed
            audit("admin_update_runtime_config_cors_failed", None, updates)
            return jsonify({
                "ok": True,
                "config": _mask_secrets(_RUNTIME_CONFIG),
                "persisted": True,
                "corsUpdated": False,
                "corsWarning": "CORS-Middleware konnte nicht dynamisch aktualisiert werden. Server-Restart erforderlich."
            })
    
    audit("admin_update_runtime_config", None, updates)
    
    return jsonify({
        "ok": True,
        "config": _mask_secrets(_RUNTIME_CONFIG),
        "persisted": True,
        "corsUpdated": cors_updated,
    })


@app.route("/api/admin/runtime/validate-cors", methods=["POST"])
@require_admin
def admin_validate_cors():
    """Validate CORS configuration before applying."""
    body = request.get_json(force=True) or {}
    origins = body.get("origins", [])
    
    errors = []
    warnings = []
    
    if not isinstance(origins, list):
        return jsonify({"error": "origins muss eine Liste sein"}), 400
    
    for origin in origins:
        origin = origin.strip()
        
        # Block wildcards
        if origin == "*":
            errors.append({
                "origin": origin,
                "error": "Wildcard nicht erlaubt",
                "blocker": "cors_wildcard_blocked"
            })
            continue
        
        # Block auth in origin
        if any(pattern in origin.lower() for pattern in ["token=", "key=", "auth="]):
            errors.append({
                "origin": origin,
                "error": "Origin darf keine Auth-Parameter enthalten",
                "blocker": "cors_auth_in_origin_blocked"
            })
            continue
        
        # Warn about http (non-HTTPS)
        if origin.startswith("http://") and not origin.startswith("http://localhost"):
            warnings.append({
                "origin": origin,
                "warning": "Non-HTTPS Origin erkannt. Empfehlung: HTTPS verwenden."
            })
    
    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
    
    audit("admin_validate_cors", None, {"origins": origins, "result": result})
    
    return jsonify(result)


@app.route("/api/admin/runtime/health")
@require_admin
def admin_runtime_health():
    """Check runtime/worker health status with real checks."""
    health_status = "healthy"
    blockers = []
    
    # Check if config is valid
    byok = _RUNTIME_CONFIG.get("byok_mode", "user-key")
    if byok not in ("system-key", "user-key", "disabled"):
        health_status = "degraded"
        blockers.append("invalid_byok_config")
    
    # Check CORS origins count
    cors_count = len(_RUNTIME_CONFIG.get("cors_origins", []))
    if cors_count == 0:
        health_status = "degraded"
        blockers.append("no_cors_origins")
    elif cors_count > 20:
        health_status = "degraded"
        blockers.append("too_many_cors_origins")
    
    # Check config file persistence
    if not os.path.exists(_CONFIG_FILE):
        blockers.append("config_not_persisted")
    
    # Check database connection
    try:
        test_query = query("SELECT 1 as test", one=True)
        if not test_query:
            health_status = "degraded"
            blockers.append("db_connection_issue")
    except Exception:
        health_status = "degraded"
        blockers.append("db_unavailable")
    
    return jsonify({
        "ok": True,
        "health": health_status,
        "byokMode": byok,
        "corsOriginsCount": cors_count,
        "blockers": blockers,
        "configFile": _CONFIG_FILE,
        "configPersisted": os.path.exists(_CONFIG_FILE),
    })


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN API KEYS TABLE (for audit trail)
# ═════════════════════════════════════════════════════════════════════════════
# Run this once to create the admin_api_keys table:
#   CREATE TABLE IF NOT EXISTS admin_api_keys (
#     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#     admin_id UUID REFERENCES admin_users(id),
#     key_hash TEXT UNIQUE NOT NULL,
#     label TEXT,
#     created_at TIMESTAMPTZ DEFAULT NOW(),
#     last_used_at TIMESTAMPTZ
#   );

# Admin API key management endpoints
@app.route("/api/admin/api-keys", methods=["GET"])
@require_admin
def admin_list_api_keys():
    """List all API keys for the current admin."""
    admin = get_current_admin()
    if not admin:
        return jsonify({"error": "Nicht autorisiert"}), 401
    
    keys = query(
        """SELECT id::text, label, key_hash, created_at, last_used_at
           FROM admin_api_keys WHERE admin_id = %s::uuid
           ORDER BY created_at DESC""",
        (admin["id"],),
    )
    return jsonify({
        "keys": [
            {
                "id": k["id"],
                "label": k["label"],
                "keyHint": k["key_hash"][:8] + "...",  # Only show hint
                "createdAt": k["created_at"],
                "lastUsedAt": k["last_used_at"],
            }
            for k in keys
        ]
    })


@app.route("/api/admin/api-keys", methods=["POST"])
@require_admin
def admin_create_api_key():
    """Create a new API key for the current admin. Returns the raw key ONCE."""
    import secrets
    
    admin = get_current_admin()
    if not admin:
        return jsonify({"error": "Nicht autorisiert"}), 401
    
    body = request.get_json(force=True) or {}
    label = body.get("label", "Admin Key")
    
    # Generate a secure random key
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    # Store the hash, not the key
    query(
        """INSERT INTO admin_api_keys (admin_id, key_hash, label)
           VALUES (%s::uuid, %s, %s)""",
        (admin["id"], key_hash, label),
        write=True,
    )
    
    audit("admin_create_api_key", None, {"label": label})
    
    # Return the RAW key ONCE - it cannot be recovered!
    return jsonify({
        "ok": True,
        "key": raw_key,  # Only returned ONCE at creation
        "keyHint": key_hash[:8] + "...",
        "warning": "Speichere diesen Key sicher. Er wird nie wieder angezeigt!"
    })


@app.route("/api/admin/llm/routes/<rid>/healthcheck", methods=["POST"])
@require_admin
def admin_llm_route_healthcheck(rid):
    """Perform health check on an LLM route by actually pinging the endpoint."""
    # Get route details
    route = query(
        """SELECT id::text, model_id AS "modelId", model_name AS "modelName",
                  provider, base_url AS "baseUrl", api_key AS "apiKey"
           FROM llm_routes WHERE id = %s::uuid""",
        (rid,), one=True,
    )
    
    if not route:
        return jsonify({"error": "Route nicht gefunden"}), 404
    
    provider = route.get("provider", "").lower()
    base_url = route.get("baseUrl") or ""
    model_name = route.get("modelName") or route.get("modelId") or "gpt-4"
    health_status = "healthy"
    blocker = None
    response_time_ms = None
    error_message = None
    
    try:
        # Build the appropriate health check request based on provider
        headers = {"Content-Type": "application/json"}
        
        if provider == "openai":
            if not base_url:
                base_url = "https://api.openai.com"
            # Simple models list request for health check
            url = f"{base_url.rstrip('/')}/v1/models"
            if route.get("apiKey"):
                headers["Authorization"] = f"Bearer {route['apiKey']}"
            timeout = 10
        elif provider == "anthropic":
            if not base_url:
                base_url = "https://api.anthropic.com"
            # Health check via models endpoint
            url = f"{base_url.rstrip('/')}/v1/models"
            if route.get("apiKey"):
                headers["x-api-key"] = route["apiKey"]
                headers["anthropic-version"] = "2023-06-01"
            timeout = 10
        elif provider == "deepseek":
            if not base_url:
                base_url = "https://api.deepseek.com"
            url = f"{base_url.rstrip('/')}/v1/models"
            if route.get("apiKey"):
                headers["Authorization"] = f"Bearer {route['apiKey']}"
            timeout = 10
        elif provider == "gemini":
            if not base_url:
                base_url = "https://generativelanguage.googleapis.com"
            # Gemini health check via model list
            url = f"{base_url.rstrip('/')}/v1beta1/models?pageSize=1"
            if route.get("apiKey"):
                headers["x-goog-api-key"] = route["apiKey"]
            timeout = 10
        else:
            # Generic health check for unknown providers
            if not base_url:
                health_status = "degraded"
                blocker = "missing_base_url"
                url = None
            else:
                url = f"{base_url.rstrip('/')}/health"
                timeout = 10
        
        if url:
            start_time = time.time()
            resp = requests.get(url, headers=headers, timeout=timeout)
            response_time_ms = int((time.time() - start_time) * 1000)
            
            if resp.status_code >= 500:
                health_status = "degraded"
                blocker = "server_error"
                error_message = f"HTTP {resp.status_code}"
            elif resp.status_code >= 400:
                health_status = "degraded"
                blocker = "client_error"
                error_message = f"HTTP {resp.status_code}"
            else:
                health_status = "healthy"
    
    except requests.exceptions.Timeout:
        health_status = "degraded"
        blocker = "timeout"
        error_message = f"Request timeout after {timeout}s"
    except requests.exceptions.ConnectionError as e:
        health_status = "degraded"
        blocker = "connection_error"
        error_message = "Verbindung fehlgeschlagen"
    except Exception as e:
        health_status = "degraded"
        blocker = "unknown_error"
        error_message = str(e)[:100]
    
    audit("admin_llm_healthcheck", rid, {
        "provider": provider,
        "model": model_name,
        "status": health_status,
        "blocker": blocker,
        "responseTimeMs": response_time_ms,
    })
    
    return jsonify({
        "ok": True,
        "routeId": rid,
        "provider": provider,
        "model": model_name,
        "health": health_status,
        "blocker": blocker,
        "error": error_message,
        "responseTimeMs": response_time_ms,
        "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


@app.route("/api/admin/launcher/tools/<tid>/healthcheck", methods=["POST"])
@require_admin
def admin_tool_healthcheck(tid):
    """Perform health check on a launcher tool by actually testing the endpoint."""
    # Get tool details
    tool = query(
        """SELECT id::text, label, base_url AS "baseUrl", auth_mode AS "authMode"
           FROM launcher_overrides WHERE id = %s::uuid""",
        (tid,), one=True,
    )
    
    if not tool:
        return jsonify({"error": "Tool nicht gefunden"}), 404
    
    label = tool.get("label", "")
    base_url = tool.get("baseUrl") or ""
    auth_mode = tool.get("authMode") or "none"
    health_status = "healthy"
    blocker = None
    response_time_ms = None
    error_message = None
    
    try:
        # Special handling for OpenHands - must actually check if it's reachable
        if label == "OpenHands":
            # Check if OpenHands API is reachable
            oh_url = os.getenv("OPENHANDS_API_URL", "http://127.0.0.1:3000")
            try:
                start_time = time.time()
                resp = requests.get(f"{oh_url.rstrip('/')}/api/agents", timeout=10)
                response_time_ms = int((time.time() - start_time) * 1000)
                if resp.status_code < 500:
                    health_status = "healthy"
                else:
                    health_status = "degraded"
                    blocker = "openhands_unreachable"
                    error_message = f"OpenHands returned HTTP {resp.status_code}"
            except requests.exceptions.Timeout:
                health_status = "degraded"
                blocker = "timeout"
                error_message = "OpenHands antwortet nicht"
            except requests.exceptions.ConnectionError:
                health_status = "degraded"
                blocker = "connection_error"
                error_message = "OpenHands nicht erreichbar"
        
        elif not base_url:
            # For non-OpenHands tools without URL, mark as unknown
            health_status = "unknown"
            blocker = "missing_base_url"
        
        else:
            # Perform actual HTTP health check
            health_paths = ["/health", "/api/health", "/status", "/api/status", ""]
            timeout = 10
            
            for path in health_paths:
                try:
                    url = f"{base_url.rstrip('/')}{path}"
                    start_time = time.time()
                    resp = requests.get(url, timeout=timeout)
                    response_time_ms = int((time.time() - start_time) * 1000)
                    
                    if resp.status_code < 500:
                        health_status = "healthy"
                        break
                except requests.exceptions.RequestException:
                    continue
            else:
                # If no health endpoint worked, try the base URL itself
                try:
                    url = base_url.rstrip('/')
                    start_time = time.time()
                    resp = requests.get(url, timeout=timeout, allow_redirects=True)
                    response_time_ms = int((time.time() - start_time) * 1000)
                    
                    if resp.status_code < 500:
                        health_status = "healthy"
                    else:
                        health_status = "degraded"
                        blocker = "server_error"
                        error_message = f"HTTP {resp.status_code}"
                except requests.exceptions.Timeout:
                    health_status = "degraded"
                    blocker = "timeout"
                    error_message = f"Request timeout after {timeout}s"
                except requests.exceptions.ConnectionError:
                    health_status = "degraded"
                    blocker = "connection_error"
                    error_message = "Verbindung fehlgeschlagen"
    
    except Exception as e:
        health_status = "degraded"
        blocker = "unknown_error"
        error_message = str(e)[:100]
    
    audit("admin_tool_healthcheck", tid, {
        "label": label,
        "status": health_status,
        "blocker": blocker,
        "responseTimeMs": response_time_ms,
    })
    
    return jsonify({
        "ok": True,
        "toolId": tid,
        "label": label,
        "health": health_status,
        "blocker": blocker,
        "error": error_message,
        "responseTimeMs": response_time_ms,
        "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


# ═════════════════════════════════════════════════════════════════════════════
# OPENHANDS PROXY
# ═════════════════════════════════════════════════════════════════════════════

jobs: dict = {}
events_lock = threading.Lock()


def get_oh_key():
    if os.path.exists("/opt/secure/openhands_api_key.txt"):
        with open("/opt/secure/openhands_api_key.txt") as f:
            return f.read().strip()
    return os.getenv("OPENHANDS_API_KEY", "")


def oh_headers():
    return {
        "Content-Type": "application/json",
        "X-Session-API-Key": get_oh_key(),
    }


def poll_oh_events(job_id, oh_conv_id):
    try:
        resp = requests.get(
            f"{OPENHANDS_API_URL}/api/conversations/{oh_conv_id}/events/search"
            "?limit=50&sort_order=TIMESTAMP_DESC",
            headers=oh_headers(), timeout=30,
        )
        if not resp.ok:
            return
        events = resp.json().get("items", [])
        with events_lock:
            if job_id not in jobs:
                return
            job = jobs[job_id]
            runtime_events = []
            for e in events[:20]:
                kind = e.get("kind", "")
                msg  = ""
                level = "info"
                if kind == "ActionEvent":
                    msg = "Agent action: " + e.get("tool_name", "unknown")
                elif kind == "ObservationEvent":
                    msg = "Tool result: " + e.get("tool_name", "")
                elif kind == "ErrorEvent":
                    msg   = e.get("message", "Error")
                    level = "error"
                elif kind == "MessageEvent":
                    msg = e.get("role", "") + ": " + e.get("message", "")[:100]
                elif kind == "ConversationStatusEvent":
                    status = e.get("status", "")
                    msg    = "Status: " + status
                    if status in ("stopped", "finished"):
                        level = "success"
                runtime_events.append({
                    "at": int(time.time()), "level": level,
                    "stage": "openhands", "message": msg or f"Event: {kind}",
                })
            if job["status"] == "running":
                for e in events:
                    if e.get("kind") == "ConversationStatusEvent" and \
                            e.get("status") in ("stopped", "finished", "failed"):
                        job["status"] = "completed"
                        runtime_events.append({
                            "at": int(time.time()), "level": "success",
                            "stage": "openhands", "message": "OpenHands completed",
                        })
                        break
            job["events"] = runtime_events
    except Exception as exc:
        with events_lock:
            if job_id in jobs:
                jobs[job_id]["events"].append({
                    "at": int(time.time()), "level": "error",
                    "stage": "openhands",
                    "message": "Poll error: " + str(exc)[:50],
                })


@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/openhands/jobs", methods=["POST"])
def create_job():
    body = request.get_json(force=True) or {}
    # Accept both legacy contract (mission/repoUrl) and simple task field
    task = (
        body.get("task")
        or body.get("mission")
        or ""
    )
    if not task:
        return jsonify({"error": "task or mission required"}), 400

    repo_url    = body.get("repoUrl", "")
    branch      = body.get("branch", "main")
    draft_only  = body.get("draftPrOnly", True)

    job_id     = str(uuid.uuid4())
    oh_conv_id = None
    conv_error  = None

    try:
        resp = requests.post(
            f"{OPENHANDS_API_URL}/api/conversations",
            headers=oh_headers(),
            json={
                "initial_message": task,
                "runtime_image": "docker.all-hands.ai/all-hands-ai/runtime:0.39-nikolaik",
            },
            timeout=30,
        )
        if resp.ok:
            oh_conv_id = resp.json().get("conversation_id")
        else:
            conv_error = f"OpenHands HTTP {resp.status_code}"
    except Exception as exc:
        conv_error = str(exc)[:120]

    initial_status = "running" if oh_conv_id else "failed"
    init_event = {
        "at": int(time.time()),
        "level": "info" if oh_conv_id else "error",
        "stage": "init",
        "message": "Job gestartet" if oh_conv_id else ("OpenHands-Fehler: " + (conv_error or "unbekannt")),
    }

    job = {
        "id":         job_id,
        "jobId":      job_id,
        "status":     initial_status,
        "task":       task,
        "repoUrl":    repo_url,
        "branch":     branch,
        "ohConvId":   oh_conv_id,
        "openHandsId": oh_conv_id,
        "events":     [init_event],
        "result":     None,
        "lastError":  conv_error,
        "draftPrUrl": None,
        "changedFiles": [],
        "createdAt":  int(time.time()),
    }

    with events_lock:
        jobs[job_id] = job

    if oh_conv_id:
        t = threading.Thread(target=poll_oh_events, args=(job_id, oh_conv_id), daemon=True)
        t.start()

    return jsonify(job), 201


@app.route("/openhands/jobs/<job_id>")
def get_job(job_id):
    with events_lock:
        if job_id not in jobs:
            return jsonify({"error": "Job not found"}), 404
        job = jobs[job_id].copy()
        if job.get("ohConvId") and job["status"] == "running":
            try:
                resp = requests.get(
                    f"{OPENHANDS_API_URL}/api/conversations/{job['ohConvId']}/events/search"
                    "?limit=10&sort_order=TIMESTAMP_DESC",
                    headers=oh_headers(), timeout=10,
                )
                if resp.ok:
                    for e in resp.json().get("items", []):
                        if e.get("kind") == "ConversationStatusEvent" and \
                                e.get("status") in ("stopped", "finished", "failed"):
                            job["status"] = "completed"
                            break
            except Exception:
                pass
        return jsonify(job)


@app.route("/openhands/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    with events_lock:
        if job_id not in jobs:
            return jsonify({"error": "Job not found"}), 404
        jobs[job_id]["status"] = "blocked"
        jobs[job_id]["events"].append({
            "at": int(time.time()), "level": "warning",
            "stage": "openhands", "message": "Cancelled by user",
        })
        return jsonify(jobs[job_id])


# ═════════════════════════════════════════════════════════════════════════════
# PAYMENT METHODS — Issue #457 (PayPal), #456 (Google Play)
#
# Required DB schema (run once on the Postgres instance):
#
#   CREATE TABLE IF NOT EXISTS payment_methods (
#     id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#     type       VARCHAR(50) UNIQUE NOT NULL,
#     label      TEXT NOT NULL,
#     enabled    BOOLEAN NOT NULL DEFAULT false,
#     config     JSONB NOT NULL DEFAULT '{}'::jsonb,
#     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
#     updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
#   );
#
#   CREATE TABLE IF NOT EXISTS credit_packages (
#     id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#     name        TEXT NOT NULL,
#     credits     INTEGER NOT NULL,
#     price_eur   NUMERIC(10,2) NOT NULL,
#     description TEXT,
#     enabled     BOOLEAN NOT NULL DEFAULT true,
#     sort_order  INTEGER NOT NULL DEFAULT 0,
#     created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
#   );
# ═════════════════════════════════════════════════════════════════════════════


# ── Payment helpers ────────────────────────────────────────────────────────────

def _get_payment_method(ptype: str) -> dict | None:
    try:
        row = query(
            """SELECT id::text, type, label, enabled, config
               FROM payment_methods WHERE type = %s LIMIT 1""",
            (ptype,), one=True,
        )
        return dict(row) if row else None
    except Exception:
        return None


def _get_credit_package(pkg_id: str) -> dict | None:
    if not pkg_id:
        return None
    try:
        row = query(
            """SELECT id::text, name, credits,
                      price_eur::float AS price_eur, description, enabled
               FROM credit_packages
               WHERE id = %s::uuid AND enabled = true LIMIT 1""",
            (pkg_id,), one=True,
        )
        return dict(row) if row else None
    except Exception:
        return None


def _get_user_credits(user_id: str) -> int:
    if not user_id:
        return 0
    try:
        row = query(
            "SELECT credits FROM admin_users WHERE id = %s::uuid LIMIT 1",
            (user_id,), one=True,
        )
        return int(row["credits"]) if row else 0
    except Exception:
        return 0


def _add_credits_and_log(user_id: str, credits: int, amount_eur: float,
                          method: str, description: str) -> None:
    """Add credits to user account and write a completed transaction record."""
    if user_id and credits > 0:
        query(
            "UPDATE admin_users SET credits = credits + %s WHERE id = %s::uuid",
            (credits, user_id), write=True,
        )
    user_row = None
    if user_id:
        try:
            user_row = query(
                "SELECT email FROM admin_users WHERE id = %s::uuid LIMIT 1",
                (user_id,), one=True,
            )
        except Exception:
            pass
    query(
        """INSERT INTO transactions
               (user_id, user_email, type, amount, currency, status, description)
           VALUES (%s::uuid, %s, 'credit_purchase', %s, 'EUR', 'completed', %s)""",
        (user_id or None,
         user_row["email"] if user_row else "anonymous",
         amount_eur, description),
        write=True,
    )


# ── Admin: Payment Methods ─────────────────────────────────────────────────────

@app.route("/api/admin/payment-methods")
@require_admin
def admin_get_payment_methods():
    try:
        rows = query(
            """SELECT id::text, type, label, enabled, config,
                      to_char(updated_at,'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "updatedAt"
               FROM payment_methods ORDER BY type ASC"""
        )
        return jsonify({"paymentMethods": [dict(r) for r in (rows or [])]})
    except Exception as exc:
        return jsonify({"paymentMethods": [], "error": str(exc)}), 200


@app.route("/api/admin/payment-methods/<mid>", methods=["PATCH"])
@require_admin
def admin_update_payment_method(mid):
    body = request.get_json(force=True) or {}
    sets, vals = [], []
    if "enabled" in body:
        sets.append("enabled = %s")
        vals.append(bool(body["enabled"]))
    if "label" in body:
        sets.append("label = %s")
        vals.append(str(body["label"])[:120])
    if "config" in body and isinstance(body["config"], dict):
        # Merge-patch: extend existing config, preserve unset keys
        sets.append("config = config || %s::jsonb")
        vals.append(psycopg2.extras.Json(body["config"]))
    if not sets:
        return jsonify({"error": "Keine Felder"}), 400
    sets.append("updated_at = NOW()")
    vals.append(mid)
    query(
        f"UPDATE payment_methods SET {', '.join(sets)} WHERE id = %s::uuid",
        vals, write=True,
    )
    safe_log = {k: v for k, v in body.items() if k not in ("config",)}
    audit("admin_update_payment_method", mid, safe_log)
    return jsonify({"ok": True})


@app.route("/api/admin/payment-methods/init", methods=["POST"])
@require_admin
def admin_init_payment_methods():
    """Seed payment_methods table with default rows (idempotent)."""
    defaults = [
        ("paypal",       "PayPal",             {"client_id": "", "client_secret": "", "mode": "live"}),
        ("skrill",       "Skrill",              {"merchant_email": "", "secret_word": ""}),
        ("crypto_btc",   "Bitcoin (BTC)",       {"wallet_address": "", "network": "mainnet"}),
        ("crypto_eth",   "Ethereum (ETH)",      {"wallet_address": "", "network": "mainnet"}),
        ("crypto_usdt",  "USDT (TRC20)",        {"wallet_address": "", "network": "tron"}),
        ("google_play",  "Google Play IAP",     {"package_name": "de.arelorian.sovereign",
                                                 "service_account_json": ""}),
    ]
    inserted = 0
    for ptype, label, cfg in defaults:
        existing = query(
            "SELECT id FROM payment_methods WHERE type = %s LIMIT 1", (ptype,), one=True,
        )
        if not existing:
            query(
                """INSERT INTO payment_methods (type, label, enabled, config)
                   VALUES (%s, %s, false, %s::jsonb)""",
                (ptype, label, psycopg2.extras.Json(cfg)), write=True,
            )
            inserted += 1
    return jsonify({"ok": True, "inserted": inserted})


# ── Admin: Credit Packages ─────────────────────────────────────────────────────

@app.route("/api/admin/credit-packages")
@require_admin
def admin_get_credit_packages():
    try:
        rows = query(
            """SELECT id::text, name, credits,
                      price_eur::float AS "priceEur",
                      description, enabled,
                      sort_order AS "sortOrder"
               FROM credit_packages ORDER BY sort_order ASC, price_eur ASC"""
        )
        return jsonify({"packages": [dict(r) for r in (rows or [])]})
    except Exception as exc:
        return jsonify({"packages": [], "error": str(exc)}), 200


@app.route("/api/admin/credit-packages/init", methods=["POST"])
@require_admin
def admin_init_credit_packages():
    """Seed default credit packages (idempotent)."""
    defaults = [
        ("Starter",   500,    1.99, "500 Credits – ideal zum Ausprobieren",    0),
        ("Pro",      2500,    7.99, "2.500 Credits – für regelmäßige Nutzung", 1),
        ("Power",   10000,   24.99, "10.000 Credits – für Power-User",         2),
        ("Studio",  50000,   89.99, "50.000 Credits – für Studios und Teams",  3),
    ]
    inserted = 0
    for name, creds, price, desc, order in defaults:
        existing = query(
            "SELECT id FROM credit_packages WHERE name = %s LIMIT 1", (name,), one=True,
        )
        if not existing:
            query(
                """INSERT INTO credit_packages
                       (name, credits, price_eur, description, enabled, sort_order)
                   VALUES (%s, %s, %s, %s, true, %s)""",
                (name, creds, price, desc, order), write=True,
            )
            inserted += 1
    return jsonify({"ok": True, "inserted": inserted})


@app.route("/api/admin/credit-packages/<pid>", methods=["PATCH"])
@require_admin
def admin_update_credit_package(pid):
    body = request.get_json(force=True) or {}
    col_map = {
        "name":       "name",
        "credits":    "credits",
        "priceEur":   "price_eur",
        "description":"description",
        "enabled":    "enabled",
        "sortOrder":  "sort_order",
    }
    sets, vals = [], []
    for k, v in body.items():
        if k in col_map:
            sets.append(f"{col_map[k]} = %s")
            vals.append(v)
    if not sets:
        return jsonify({"error": "Keine Felder"}), 400
    vals.append(pid)
    query(
        f"UPDATE credit_packages SET {', '.join(sets)} WHERE id = %s::uuid",
        vals, write=True,
    )
    audit("admin_update_credit_package", pid, body)
    return jsonify({"ok": True})


# ── Admin: Crypto Confirmation ─────────────────────────────────────────────────

@app.route("/api/admin/payment-methods/crypto/confirm", methods=["POST"])
@require_admin
def admin_confirm_crypto_payment():
    """Admin manually confirms a crypto payment and credits the user."""
    body       = request.get_json(force=True) or {}
    user_id    = str(body.get("userId", ""))
    package_id = str(body.get("packageId", ""))
    tx_hash    = str(body.get("txHash", ""))[:80]

    if not user_id or not package_id:
        return jsonify({"error": "userId und packageId erforderlich"}), 400

    pkg = _get_credit_package(package_id)
    if not pkg:
        return jsonify({"error": "Paket nicht gefunden"}), 404

    _add_credits_and_log(
        user_id, int(pkg["credits"]), float(pkg["price_eur"]),
        "crypto", f"Crypto: {pkg['name']} ({pkg['credits']} Credits) | TX: {tx_hash or 'manuell'}",
    )
    audit("admin_confirm_crypto_payment", user_id,
          {"packageId": package_id, "txHash": tx_hash, "credits": pkg["credits"]})
    return jsonify({"ok": True, "creditsAdded": pkg["credits"],
                    "newBalance": _get_user_credits(user_id)})


# ── Public: Billing data ────────────────────────────────────────────────────────

@app.route("/api/billing")
def user_billing_overview():
    """Return available credit packages + current subscription for the user."""
    user_id = request.headers.get("X-User-Id", "").strip()
    try:
        pkg_rows = query(
            """SELECT id::text, name, credits,
                      price_eur::float AS price, description, sort_order
               FROM credit_packages WHERE enabled = true
               ORDER BY sort_order ASC, price_eur ASC"""
        )
        packages = []
        for r in (pkg_rows or []):
            d = dict(r)
            packages.append({
                "id":       d["id"],
                "name":     d["name"],
                "price":    d["price"],
                "currency": "EUR",
                "interval": "once",
                "features": [f"{d['credits']} Credits",
                             d.get("description") or ""],
                "tier":     "custom",
                "credits":  d["credits"],
            })
    except Exception:
        packages = []

    subscription = None
    if user_id:
        try:
            row = query(
                """SELECT subscription_status FROM admin_users
                   WHERE id = %s::uuid LIMIT 1""",
                (user_id,), one=True,
            )
            if row and row["subscription_status"] in ("active", "trialing"):
                subscription = {
                    "id":               user_id,
                    "status":           row["subscription_status"],
                    "planId":           "pro",
                    "tier":             "pro",
                    "currentPeriodEnd": "",
                    "cancelAtPeriodEnd": False,
                }
        except Exception:
            pass

    return jsonify({
        "availablePackages": packages,
        "packages":          packages,
        "subscription":      subscription,
        "invoices":          [],
    })


# ── PayPal ─────────────────────────────────────────────────────────────────────

def _paypal_base_url(mode: str) -> str:
    return ("https://api-m.paypal.com"
            if mode == "live" else "https://api-m.sandbox.paypal.com")


def _paypal_access_token(client_id: str, client_secret: str, mode: str) -> str:
    resp = requests.post(
        _paypal_base_url(mode) + "/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@app.route("/api/billing/purchase/paypal/create-order", methods=["POST"])
def paypal_create_order():
    """Create a PayPal checkout order and return the approval URL."""
    body       = request.get_json(force=True) or {}
    package_id = str(body.get("packageId", ""))
    user_id    = request.headers.get("X-User-Id", "").strip()
    return_url = str(body.get("returnUrl", ""))
    cancel_url = str(body.get("cancelUrl", ""))

    pm = _get_payment_method("paypal")
    if not pm or not pm.get("enabled"):
        return jsonify({"error": "PayPal ist nicht aktiviert"}), 503

    cfg           = pm.get("config") or {}
    client_id     = cfg.get("client_id", "")
    client_secret = cfg.get("client_secret", "")
    mode          = cfg.get("mode", "live")
    if not client_id or not client_secret:
        return jsonify({"error": "PayPal-Zugangsdaten nicht konfiguriert"}), 503

    pkg = _get_credit_package(package_id)
    if not pkg:
        return jsonify({"error": "Credit-Paket nicht gefunden"}), 404

    try:
        token    = _paypal_access_token(client_id, client_secret, mode)
        price    = float(pkg["price_eur"])
        resp     = requests.post(
            _paypal_base_url(mode) + "/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "amount": {"currency_code": "EUR", "value": f"{price:.2f}"},
                    "description": f"Sovereign Credits — {pkg['name']}",
                    "custom_id":   f"{user_id}|{package_id}",
                }],
                "application_context": {
                    "return_url": return_url or
                        "https://sovereign-backend.arelorian.de/billing/paypal/return",
                    "cancel_url": cancel_url or
                        "https://sovereign-backend.arelorian.de/billing/paypal/cancel",
                },
            },
            timeout=20,
        )
        resp.raise_for_status()
        data        = resp.json()
        order_id    = data["id"]
        approve_url = next(
            (lnk["href"] for lnk in data.get("links", []) if lnk["rel"] == "approve"),
            None,
        )
        return jsonify({"orderId": order_id, "approvalUrl": approve_url})
    except Exception as exc:
        return jsonify({"error": f"PayPal-Fehler: {str(exc)[:120]}"}), 502


@app.route("/api/billing/purchase/paypal/capture", methods=["POST"])
def paypal_capture_order():
    """Capture a PayPal order after user approval and credit the user."""
    body     = request.get_json(force=True) or {}
    order_id = str(body.get("orderId", ""))
    user_id  = request.headers.get("X-User-Id", "").strip()
    if not order_id:
        return jsonify({"error": "orderId fehlt"}), 400

    pm = _get_payment_method("paypal")
    if not pm or not pm.get("enabled"):
        return jsonify({"error": "PayPal nicht aktiviert"}), 503

    cfg           = pm.get("config") or {}
    client_id     = cfg.get("client_id", "")
    client_secret = cfg.get("client_secret", "")
    mode          = cfg.get("mode", "live")
    try:
        token = _paypal_access_token(client_id, client_secret, mode)
        # Fetch order to read back custom_id (user_id|package_id)
        order_resp = requests.get(
            _paypal_base_url(mode) + f"/v2/checkout/orders/{order_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        order_resp.raise_for_status()
        order_data = order_resp.json()
        custom_id  = (
            (order_data.get("purchase_units") or [{}])[0].get("custom_id", "")
        )
        parts      = (custom_id + "||").split("|")
        uid, pkg_id = parts[0].strip(), parts[1].strip()
        if not uid:
            uid = user_id

        # Capture
        cap_resp = requests.post(
            _paypal_base_url(mode) + f"/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json={},
            timeout=20,
        )
        cap_resp.raise_for_status()
        cap_data = cap_resp.json()
        if cap_data.get("status") != "COMPLETED":
            return jsonify({
                "error": f"Zahlung nicht abgeschlossen: {cap_data.get('status')}",
            }), 402

        pkg     = _get_credit_package(pkg_id)
        credits = int(pkg["credits"])    if pkg else 0
        price   = float(pkg["price_eur"]) if pkg else 0.0
        label   = pkg["name"]             if pkg else pkg_id

        _add_credits_and_log(uid, credits, price, "paypal",
                             f"PayPal: {label} ({credits} Credits)")
        return jsonify({"ok": True, "creditsAdded": credits,
                        "newBalance": _get_user_credits(uid)})
    except Exception as exc:
        return jsonify({"error": f"Capture-Fehler: {str(exc)[:120]}"}), 502


@app.route("/api/billing/webhooks/paypal", methods=["POST"])
def paypal_webhook():
    """PayPal Webhook IPN — credit user on PAYMENT.CAPTURE.COMPLETED."""
    body       = request.get_json(force=True) or {}
    event_type = body.get("event_type", "")
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        resource   = body.get("resource", {})
        custom_id  = (
            (resource.get("purchase_units") or [{}])[0].get("custom_id", "")
        )
        parts      = (custom_id + "||").split("|")
        uid, pkg_id = parts[0].strip(), parts[1].strip()
        pkg = _get_credit_package(pkg_id)
        if uid and pkg:
            _add_credits_and_log(
                uid, int(pkg["credits"]), float(pkg["price_eur"]),
                "paypal_webhook", f"PayPal Webhook: {pkg['name']}",
            )
    return jsonify({"ok": True})


# ── Skrill ─────────────────────────────────────────────────────────────────────

@app.route("/api/billing/purchase/skrill/init", methods=["POST"])
def skrill_init():
    """Return a Skrill Quick Checkout redirect URL for the selected package."""
    body       = request.get_json(force=True) or {}
    package_id = str(body.get("packageId", ""))
    user_id    = request.headers.get("X-User-Id", "").strip()
    return_url = str(body.get("returnUrl", ""))
    cancel_url = str(body.get("cancelUrl", ""))
    notify_url = str(body.get(
        "notifyUrl",
        "https://sovereign-backend.arelorian.de/api/billing/webhooks/skrill",
    ))

    pm = _get_payment_method("skrill")
    if not pm or not pm.get("enabled"):
        return jsonify({"error": "Skrill nicht aktiviert"}), 503

    cfg            = pm.get("config") or {}
    merchant_email = cfg.get("merchant_email", "")
    if not merchant_email:
        return jsonify({"error": "Skrill nicht konfiguriert"}), 503

    pkg = _get_credit_package(package_id)
    if not pkg:
        return jsonify({"error": "Credit-Paket nicht gefunden"}), 404

    price = float(pkg["price_eur"])
    params = {
        "pay_to_email":        merchant_email,
        "amount":              f"{price:.2f}",
        "currency":            "EUR",
        "detail1_description": "Sovereign Credits",
        "detail1_text":        pkg["name"],
        "merchant_fields":     "user_id,package_id",
        "user_id":             user_id,
        "package_id":          package_id,
        "return_url":          return_url or
                               "https://sovereign-backend.arelorian.de/billing/skrill/return",
        "cancel_url":          cancel_url or
                               "https://sovereign-backend.arelorian.de/billing/skrill/cancel",
        "status_url":          notify_url,
    }
    redirect_url = "https://pay.skrill.com/?" + urllib.parse.urlencode(params)
    return jsonify({
        "redirectUrl": redirect_url,
        "packageName": pkg["name"],
        "amountEur":   price,
        "credits":     int(pkg["credits"]),
    })


@app.route("/api/billing/webhooks/skrill", methods=["POST"])
def skrill_webhook():
    """Skrill IPN status callback — credit user when status == 2 (processed)."""
    data       = request.form
    status     = data.get("status", "")
    user_id    = data.get("user_id", "")
    package_id = data.get("package_id", "")

    pm = _get_payment_method("skrill")
    if pm:
        cfg         = pm.get("config") or {}
        secret_word = cfg.get("secret_word", "")
        if secret_word:
            merchant_email = cfg.get("merchant_email", "")
            expected_sig = hashlib.md5(
                (merchant_email +
                 data.get("transaction_id", "") +
                 hashlib.md5(secret_word.upper().encode()).hexdigest() +
                 data.get("mb_amount", "") +
                 data.get("mb_currency", "") +
                 status).encode()
            ).hexdigest().upper()
            if expected_sig != data.get("md5sig", "").upper():
                return "INVALID_SIGNATURE", 400

    # status 2 = processed (successful payment)
    if status == "2" and user_id and package_id:
        pkg = _get_credit_package(package_id)
        if pkg:
            _add_credits_and_log(
                user_id, int(pkg["credits"]), float(pkg["price_eur"]),
                "skrill", f"Skrill: {pkg['name']} ({pkg['credits']} Credits)",
            )
    return "OK", 200


# ── Crypto Wallets ─────────────────────────────────────────────────────────────

@app.route("/api/billing/purchase/crypto/info", methods=["POST"])
def crypto_info():
    """Return wallet address and EUR amount for a crypto payment."""
    body       = request.get_json(force=True) or {}
    package_id = str(body.get("packageId", ""))
    coin_type  = str(body.get("coinType", "crypto_btc"))

    pm = _get_payment_method(coin_type)
    if not pm or not pm.get("enabled"):
        return jsonify({"error": f"{coin_type.upper()} nicht aktiviert"}), 503

    cfg     = pm.get("config") or {}
    address = cfg.get("wallet_address", "")
    network = cfg.get("network", "mainnet")
    if not address:
        return jsonify({"error": "Wallet-Adresse nicht konfiguriert"}), 503

    pkg = _get_credit_package(package_id)
    if not pkg:
        return jsonify({"error": "Paket nicht gefunden"}), 404

    return jsonify({
        "walletAddress": address,
        "network":       network,
        "coinType":      coin_type.replace("crypto_", "").upper(),
        "amountEur":     float(pkg["price_eur"]),
        "credits":       int(pkg["credits"]),
        "packageName":   pkg["name"],
        "note": (
            "Bitte überweise den EUR-Gegenwert in der gewählten Kryptowährung. "
            "Credits werden nach manueller Bestätigung durch den Admin gutgeschrieben."
        ),
    })


# ── Google Play IAP ────────────────────────────────────────────────────────────

@app.route("/api/billing/purchase/google-play/validate", methods=["POST"])
def google_play_validate():
    """Validate a Google Play purchase token via Android Developer API."""
    import json as _json

    body           = request.get_json(force=True) or {}
    purchase_token = str(body.get("purchaseToken", ""))
    product_id     = str(body.get("productId", ""))
    user_id        = request.headers.get("X-User-Id", "").strip()

    if not purchase_token or not product_id:
        return jsonify({"error": "purchaseToken und productId erforderlich"}), 400

    pm = _get_payment_method("google_play")
    if not pm or not pm.get("enabled"):
        return jsonify({"error": "Google Play IAP nicht aktiviert"}), 503

    cfg          = pm.get("config") or {}
    package_name = cfg.get("package_name", "de.arelorian.sovereign")
    svc_json_str = cfg.get("service_account_json", "")
    if not svc_json_str:
        return jsonify({"error": "Google Play Service Account nicht konfiguriert"}), 503

    try:
        svc   = _json.loads(svc_json_str)
        now   = int(time.time())
        hdr   = base64.urlsafe_b64encode(
            _json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        pld   = base64.urlsafe_b64encode(_json.dumps({
            "iss":   svc.get("client_email", ""),
            "scope": "https://www.googleapis.com/auth/androidpublisher",
            "aud":   "https://oauth2.googleapis.com/token",
            "iat":   now,
            "exp":   now + 3600,
        }).encode()).rstrip(b"=").decode()

        try:
            from cryptography.hazmat.primitives import hashes as _hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding as _padding
            from cryptography.hazmat.backends import default_backend as _default_backend

            priv_key   = serialization.load_pem_private_key(
                svc.get("private_key", "").encode(),
                password=None,
                backend=_default_backend(),
            )
            sig_bytes  = priv_key.sign(
                f"{hdr}.{pld}".encode(),
                _padding.PKCS1v15(),
                _hashes.SHA256(),
            )
            jwt_token  = f"{hdr}.{pld}.{base64.urlsafe_b64encode(sig_bytes).rstrip(b'=').decode()}"
        except ImportError:
            return jsonify({"error": "cryptography-Paket nicht installiert"}), 503

        tok_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                  "assertion": jwt_token},
            timeout=15,
        )
        tok_resp.raise_for_status()
        access_token = tok_resp.json()["access_token"]

        ver_resp = requests.get(
            f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
            f"/{package_name}/purchases/products/{product_id}/tokens/{purchase_token}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        ver_resp.raise_for_status()
        purchase_data = ver_resp.json()

        # purchaseState 0 = purchased
        if purchase_data.get("purchaseState") != 0:
            return jsonify({"error": "Kauf nicht bestätigt"}), 402

        # Map product_id → credit package by name similarity
        pkg = None
        try:
            pkg_row = query(
                "SELECT * FROM credit_packages WHERE name ILIKE %s AND enabled = true LIMIT 1",
                (f"%{product_id}%",), one=True,
            )
            if pkg_row:
                pkg = dict(pkg_row)
        except Exception:
            pass

        credits  = int(pkg["credits"])     if pkg else 0
        price    = float(pkg["price_eur"]) if pkg else 0.0
        pkg_name = pkg["name"]             if pkg else product_id

        if user_id and credits > 0:
            _add_credits_and_log(user_id, credits, price, "google_play",
                                 f"Google Play: {pkg_name} ({credits} Credits)")
        return jsonify({
            "ok":            True,
            "creditsAdded":  credits,
            "purchaseState": purchase_data.get("purchaseState"),
            "newBalance":    _get_user_credits(user_id),
        })
    except Exception as exc:
        return jsonify({"error": f"Google Play Validierung: {str(exc)[:120]}"}), 502


# ── Public: enabled payment methods ───────────────────────────────────────────

@app.route("/api/billing/payment-methods")
def public_payment_methods():
    """Return all currently enabled payment methods (type + label only — no secrets)."""
    try:
        rows = query(
            """SELECT type, label FROM payment_methods
               WHERE enabled = true ORDER BY type ASC"""
        )
        return jsonify({
            "methods": [{"type": r["type"], "label": r["label"]} for r in (rows or [])],
        })
    except Exception as exc:
        return jsonify({"methods": [], "error": str(exc)}), 200


# ── Generic /api/billing/purchase — routes by paymentMethod ───────────────────

@app.route("/api/billing/purchase", methods=["POST"])
def user_purchase():
    """
    Unified purchase endpoint.
    Body: { packageId, paymentMethod, ...extra }
    paymentMethod: 'paypal' | 'skrill' | 'crypto_btc' | 'crypto_eth' |
                   'crypto_usdt' | 'google_play'
    """
    body           = request.get_json(force=True) or {}
    package_id     = str(body.get("packageId", ""))
    payment_method = str(body.get("paymentMethod", ""))

    if not package_id:
        return jsonify({"error": "packageId erforderlich"}), 400
    if not payment_method:
        return jsonify({"error": "paymentMethod erforderlich"}), 400

    pkg = _get_credit_package(package_id)
    if not pkg:
        return jsonify({"error": "Credit-Paket nicht gefunden"}), 404

    if payment_method == "paypal":
        return paypal_create_order()
    if payment_method == "skrill":
        return skrill_init()
    if payment_method.startswith("crypto_"):
        return crypto_info()
    if payment_method == "google_play":
        return google_play_validate()

    return jsonify({"error": f"Unbekannte Zahlungsmethode: {payment_method}"}), 400


# ── Public LLM Route endpoints (Issue #461) ──────────────────────────────────

@app.route("/api/llm/routes")
def public_llm_routes():
    """All active LLM routes — merged DB config for frontend clients."""
    try:
        rows = query(
            """SELECT id::text, model_id AS "modelId", model_name AS "modelName",
                      provider, credits_per_unit AS "creditsPerUnit",
                      disabled, priority
               FROM llm_routes
               ORDER BY priority ASC"""
        )
        routes = []
        for r in rows:
            d = dict(r)
            routes.append({
                "id":                  d["id"],
                "defaultModelId":      d["modelId"],
                "label":               d["modelName"],
                "description":         d["modelName"],
                "creditsPerKTokens":   float(d["creditsPerUnit"]),
                "enabled":             not d["disabled"],
                "userKeyOverride":     True,
                "maxTokensPerRequest": 32_000,
            })
        return jsonify({"routes": routes})
    except Exception as exc:
        return jsonify({"error": str(exc), "routes": []}), 500


@app.route("/api/llm/routes/<route_id>")
def public_llm_route(route_id):
    """Single LLM route by id — merged DB config for frontend clients."""
    try:
        row = query(
            """SELECT id::text, model_id AS "modelId", model_name AS "modelName",
                      provider, credits_per_unit AS "creditsPerUnit",
                      disabled, priority
               FROM llm_routes
               WHERE id::text = %s
               LIMIT 1""",
            (route_id,), one=True,
        )
        if not row:
            return jsonify({"error": "Route nicht gefunden"}), 404
        d = dict(row)
        return jsonify({
            "id":                  d["id"],
            "defaultModelId":      d["modelId"],
            "label":               d["modelName"],
            "description":         d["modelName"],
            "creditsPerKTokens":   float(d["creditsPerUnit"]),
            "enabled":             not d["disabled"],
            "userKeyOverride":     True,
            "maxTokensPerRequest": 32_000,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── User Billing endpoints (Issue #458) ──────────────────────────────────────

@app.route("/api/billing/credits")
def user_billing_credits():
    """Return credit balance for the authenticated user (X-User-Id header)."""
    user_id = request.headers.get("X-User-Id", "").strip()
    if not user_id:
        return jsonify({"credits": 0}), 200
    try:
        row = query(
            "SELECT credits FROM users WHERE id::text = %s LIMIT 1",
            (user_id,), one=True,
        )
        credits = int(row["credits"]) if row else 0
        return jsonify({"credits": credits})
    except Exception as exc:
        return jsonify({"credits": 0, "error": str(exc)}), 200


@app.route("/api/billing/deduct", methods=["POST"])
def user_billing_deduct():
    """Server-side credit deduction with validation and usage logging."""
    body        = request.get_json(force=True) or {}
    user_id     = request.headers.get("X-User-Id", "").strip()
    cost_id     = str(body.get("costId",    ""))
    amount      = int(body.get("amount",    0))
    token_count = int(body.get("tokenCount", 0))

    if amount <= 0:
        return jsonify({"ok": True, "deducted": 0})

    try:
        if user_id:
            row = query(
                "SELECT credits FROM users WHERE id::text = %s LIMIT 1",
                (user_id,), one=True,
            )
            if not row:
                return jsonify({"error": "User nicht gefunden"}), 404
            current = int(row["credits"])
            if current < amount:
                return jsonify({
                    "error":     "Nicht genug Credits",
                    "available": current,
                    "required":  amount,
                }), 402
            query(
                "UPDATE users SET credits = GREATEST(0, credits - %s) WHERE id::text = %s",
                (amount, user_id), write=True,
            )

        # Usage log — graceful if table doesn't exist yet
        try:
            query(
                """INSERT INTO credit_usage
                       (user_id, cost_id, credits_deducted, token_count, created_at)
                   VALUES (%s, %s, %s, %s, NOW())""",
                (user_id or None, cost_id, amount, token_count), write=True,
            )
        except Exception:
            pass  # Table may not exist; deduction already applied above

        return jsonify({"ok": True, "deducted": amount})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# USER AUTH  —  Issue #459
# Routes: /api/auth/register  /api/auth/login  /api/auth/me
#         /api/auth/logout    /api/auth/google
#
# DB columns required (already migrated):
#   ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS password_hash TEXT;
#   ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS google_id TEXT;
#   ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
# ═════════════════════════════════════════════════════════════════════════════

SESSION_SECRET   = os.getenv("SESSION_SECRET", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
_COOKIE          = "sovereign_session"
_COOKIE_MAX_AGE  = 7 * 24 * 3600  # 7 days


def _hash_pw(password: str) -> str:
    """PBKDF2-SHA256, 260 000 rounds — no extra deps needed."""
    salt = os.urandom(16)
    key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return base64.b64encode(salt + key).decode()


def _verify_pw(password: str, stored: str) -> bool:
    try:
        raw  = base64.b64decode(stored)
        salt = raw[:16]
        key  = raw[16:]
        new  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
        return hmac.compare_digest(key, new)
    except Exception:
        return False


def _make_jwt(user_id: str) -> str:
    import jwt as pyjwt
    return pyjwt.encode(
        {"sub": str(user_id), "exp": int(time.time()) + _COOKIE_MAX_AGE},
        SESSION_SECRET, algorithm="HS256",
    )


def _decode_jwt(token: str) -> str | None:
    try:
        import jwt as pyjwt
        data = pyjwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
        return str(data["sub"])
    except Exception:
        return None


def _user_row_to_dict(row) -> dict:
    return {
        "id":                 str(row["id"]),
        "email":              row["email"],
        "displayName":        row.get("display_name") or "",
        "role":               row.get("role") or "user",
        "credits":            int(row.get("credits") or 0),
        "subscriptionStatus": row.get("subscription_status") or "free",
        "isBanned":           bool(row.get("is_banned")),
        "createdAt":          str(row.get("created_at") or ""),
        "avatarUrl":          row.get("avatar_url"),
        "googleId":           row.get("google_id"),
    }


def _set_session_cookie(response, user_id: str):
    token = _make_jwt(user_id)
    response.set_cookie(
        _COOKIE, token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True, secure=True, samesite="None",
        path="/",
    )
    return response


def _get_session_user_id() -> str | None:
    token = request.cookies.get(_COOKIE)
    if not token:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else None
    if not token:
        return None
    return _decode_jwt(token)


def require_session(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        uid = _get_session_user_id()
        if not uid:
            return jsonify({"error": "Nicht eingeloggt"}), 401
        request.session_user_id = uid
        return f(*args, **kwargs)
    return decorated


@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    try:
        body         = request.get_json(force=True) or {}
        email        = (body.get("email") or "").strip().lower()
        password     = body.get("password") or ""
        display_name = (body.get("displayName") or body.get("display_name") or "").strip()

        if not email or not password:
            return jsonify({"error": "E-Mail und Passwort erforderlich"}), 400
        if len(password) < 8:
            return jsonify({"error": "Passwort muss mindestens 8 Zeichen haben"}), 400

        existing = query("SELECT id FROM admin_users WHERE email = %s LIMIT 1", (email,), one=True)
        if existing:
            return jsonify({"error": "E-Mail bereits registriert"}), 409

        pw_hash = _hash_pw(password)
        new_id  = str(uuid.uuid4())
        query(
            """INSERT INTO admin_users
               (id, email, display_name, role, credits, subscription_status,
                is_banned, password_hash, created_at, last_active_at)
               VALUES (%s::uuid, %s, %s, 'user', 500, 'free', false, %s, NOW(), NOW())""",
            (new_id, email, display_name or email.split("@")[0], pw_hash),
            write=True,
        )
        row = query("SELECT * FROM admin_users WHERE id = %s::uuid LIMIT 1", (new_id,), one=True)
        resp = make_response(jsonify(_user_row_to_dict(row)))
        return _set_session_cookie(resp, new_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    try:
        body     = request.get_json(force=True) or {}
        email    = (body.get("email") or "").strip().lower()
        password = body.get("password") or ""

        if not email or not password:
            return jsonify({"error": "E-Mail und Passwort erforderlich"}), 400

        row = query(
            "SELECT * FROM admin_users WHERE email = %s LIMIT 1",
            (email,), one=True,
        )
        if not row or not row.get("password_hash"):
            return jsonify({"error": "Ungültige Zugangsdaten"}), 401
        if not _verify_pw(password, row["password_hash"]):
            return jsonify({"error": "Ungültige Zugangsdaten"}), 401
        if row.get("is_banned"):
            return jsonify({"error": "Konto gesperrt"}), 403

        query(
            "UPDATE admin_users SET last_active_at = NOW() WHERE id = %s::uuid",
            (str(row["id"]),), write=True,
        )
        resp = make_response(jsonify(_user_row_to_dict(row)))
        return _set_session_cookie(resp, str(row["id"]))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/auth/me")
@require_session
def auth_me():
    try:
        row = query(
            "SELECT * FROM admin_users WHERE id = %s::uuid LIMIT 1",
            (request.session_user_id,), one=True,
        )
        if not row:
            return jsonify({"error": "User nicht gefunden"}), 404
        return jsonify(_user_row_to_dict(row))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(_COOKIE, path="/", samesite="None", secure=True)
    return resp


@app.route("/api/auth/google", methods=["POST"])
def auth_google():
    """Verify Google ID token and create/login user."""
    try:
        body     = request.get_json(force=True) or {}
        id_token = body.get("idToken") or body.get("id_token") or ""
        if not id_token:
            return jsonify({"error": "ID-Token fehlt"}), 400

        # Verify token with Google's JWKS
        try:
            import jwt as pyjwt
            from jwt import PyJWKClient
            jwks = PyJWKClient("https://www.googleapis.com/oauth2/v3/certs")
            signing_key = jwks.get_signing_key_from_jwt(id_token)
            payload = pyjwt.decode(
                id_token, signing_key.key,
                algorithms=["RS256"],
                audience=GOOGLE_CLIENT_ID if GOOGLE_CLIENT_ID else None,
                options={"verify_aud": bool(GOOGLE_CLIENT_ID)},
            )
        except Exception as verify_err:
            return jsonify({"error": f"Google-Token ungültig: {verify_err}"}), 401

        google_id   = payload.get("sub") or ""
        email       = (payload.get("email") or "").lower()
        display_name= payload.get("name") or email.split("@")[0]
        avatar_url  = payload.get("picture")

        if not google_id or not email:
            return jsonify({"error": "Unvollständige Google-Daten"}), 400

        # Find existing user by google_id or email
        row = query(
            "SELECT * FROM admin_users WHERE google_id = %s OR email = %s LIMIT 1",
            (google_id, email), one=True,
        )

        if row:
            user_id = str(row["id"])
            query(
                """UPDATE admin_users
                   SET google_id = %s, avatar_url = COALESCE(%s, avatar_url),
                       last_active_at = NOW()
                   WHERE id = %s::uuid""",
                (google_id, avatar_url, user_id), write=True,
            )
        else:
            user_id = str(uuid.uuid4())
            query(
                """INSERT INTO admin_users
                   (id, email, display_name, role, credits, subscription_status,
                    is_banned, google_id, avatar_url, created_at, last_active_at)
                   VALUES (%s::uuid, %s, %s, 'user', 500, 'free', false,
                           %s, %s, NOW(), NOW())""",
                (user_id, email, display_name, google_id, avatar_url),
                write=True,
            )

        row = query("SELECT * FROM admin_users WHERE id = %s::uuid LIMIT 1", (user_id,), one=True)
        resp = make_response(jsonify(_user_row_to_dict(row)))
        return _set_session_cookie(resp, user_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# SOVEREIGN APP TOOLCHAIN  —  Issue: Toolchain integration
#
# Automatisch laden:          Ja
# GitHub lesen:               Nur nach Login (require_session)
# Schreiben:                  Nein (confirm=True Pflicht)
# Push auf main:              Nein (Draft PR only)
# PR erstellen:               Nur mit confirm=True
# Draft PR default:           Ja
# Repo-Allowlist:             Pflicht (TOOLCHAIN_ALLOWED_REPOS env)
# Audit-Log:                  Pflicht
#
# Endpoints:
#   GET  /api/toolchain/user-tools
#   POST /api/toolchain/github/read-file
#   POST /api/toolchain/github/list-directory
#   POST /api/toolchain/github/list-branches
#   POST /api/toolchain/github/search-code
#   POST /api/toolchain/preview-patch
#   POST /api/toolchain/create-draft-pr
#   POST /api/toolchain/apply-patch-worker
#   POST /api/toolchain/sandbox-plan
#   GET  /api/toolchain/audit-log
# ═════════════════════════════════════════════════════════════════════════════

import difflib as _difflib

_TC_GITHUB_TOKEN   = os.getenv("TOOLCHAIN_GITHUB_TOKEN") or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")
_TC_ALLOWED_REPOS  = [
    r.strip().lower()
    for r in os.getenv("TOOLCHAIN_ALLOWED_REPOS", "OuroborosCollective/Sovereign-Studio-ato").split(",")
    if r.strip()
]
_TC_WORKER_URL     = os.getenv(
    "TOOLCHAIN_WORKER_URL",
    "https://sovereign-studio-worker.projectouroboroscollective.workers.dev/git/patch",
)
_TC_GH_API         = "https://api.github.com"

# ── Internal helpers ──────────────────────────────────────────────────────────

def _tc_allowed(owner: str, repo: str) -> None:
    slug = f"{owner}/{repo}".lower()
    if "*" not in _TC_ALLOWED_REPOS and slug not in _TC_ALLOWED_REPOS:
        raise PermissionError(f"Repo {owner}/{repo} ist nicht in der Allowlist")


def _tc_gh_headers() -> dict:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sovereign-studio-backend/1.0",
    }
    if _TC_GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {_TC_GITHUB_TOKEN}"
    return h


def _tc_gh_get(path: str) -> dict:
    url = f"{_TC_GH_API}{path}"
    req = requests.get(url, headers=_tc_gh_headers(), timeout=20)
    req.raise_for_status()
    return req.json()


def _tc_gh_put(path: str, body: dict) -> dict:
    if not _TC_GITHUB_TOKEN:
        raise PermissionError("TOOLCHAIN_GITHUB_TOKEN nicht konfiguriert")
    url = f"{_TC_GH_API}{path}"
    req = requests.put(url, headers=_tc_gh_headers(), json=body, timeout=30)
    req.raise_for_status()
    return req.json()


def _tc_gh_post(path: str, body: dict) -> dict:
    if not _TC_GITHUB_TOKEN:
        raise PermissionError("TOOLCHAIN_GITHUB_TOKEN nicht konfiguriert")
    url = f"{_TC_GH_API}{path}"
    req = requests.post(url, headers=_tc_gh_headers(), json=body, timeout=30)
    req.raise_for_status()
    return req.json()


def _tc_apply_blocks(content: str, blocks: list) -> tuple:
    """Apply strict SEARCH/REPLACE blocks. Each search must occur exactly once."""
    updated = content
    report = []
    for i, block in enumerate(blocks):
        search  = block.get("search", "")
        replace = block.get("replace", "")
        if not isinstance(search, str) or not isinstance(replace, str):
            raise ValueError(f"Block {i}: search/replace müssen Strings sein")
        if not search:
            raise ValueError(f"Block {i}: search darf nicht leer sein")
        count = updated.count(search)
        if count != 1:
            raise ValueError(
                f"Block {i}: search muss genau einmal vorkommen, gefunden: {count}"
            )
        updated = updated.replace(search, replace, 1)
        report.append({"index": i, "delta_chars": len(replace) - len(search)})
    return updated, report


def _tc_unified_diff(before: str, after: str, path: str) -> str:
    return "".join(_difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    ))[:60_000]


def _tc_audit(user_id: str | None, action: str, details: dict) -> None:
    """Write toolchain action to audit_log."""
    try:
        query(
            """INSERT INTO audit_log (admin_id, admin_email, action, target_id, changes)
               VALUES (%s::uuid, %s, %s, %s, %s)""",
            (
                user_id or "00000000-0000-0000-0000-000000000000",
                "toolchain",
                f"toolchain:{action}",
                details.get("repo", "unknown"),
                psycopg2.extras.Json(details),
            ),
            write=True,
        )
    except Exception:
        pass  # Audit must not break the main action


def _tc_read_github_file(owner: str, repo: str, path: str, ref: str | None = None) -> dict:
    _tc_allowed(owner, repo)
    qs = f"?ref={urllib.parse.quote(ref)}" if ref else ""
    data = _tc_gh_get(f"/repos/{owner}/{repo}/contents/{path}{qs}")
    if isinstance(data, list):
        raise ValueError(f"{path} ist ein Verzeichnis, nicht eine Datei")
    raw = base64.b64decode(data.get("content", "").replace("\n", ""))
    return {
        "sha":      data.get("sha", ""),
        "html_url": data.get("html_url", ""),
        "bytes":    len(raw),
        "content":  raw.decode("utf-8", errors="replace"),
    }


def _tc_create_draft_pr(
    owner: str, repo: str, path: str, new_content: str,
    message: str, branch_name: str | None,
    title: str | None, body: str | None, base_branch: str | None,
) -> dict:
    _tc_allowed(owner, repo)
    # Get base SHA
    base_data = _tc_gh_get(f"/repos/{owner}/{repo}")
    default_branch = base_branch or base_data.get("default_branch", "main")

    ref_data = _tc_gh_get(f"/repos/{owner}/{repo}/git/ref/heads/{default_branch}")
    base_sha = ref_data["object"]["sha"]

    # Create branch
    branch = branch_name or f"toolchain/patch-{int(time.time())}"
    _tc_gh_post(f"/repos/{owner}/{repo}/git/refs", {
        "ref": f"refs/heads/{branch}",
        "sha": base_sha,
    })

    # Get current file SHA (needed for update)
    try:
        current = _tc_gh_get(f"/repos/{owner}/{repo}/contents/{path}?ref={default_branch}")
        file_sha = current.get("sha", "")
    except Exception:
        file_sha = ""

    # Push file to new branch
    put_body: dict = {
        "message": message,
        "content": base64.b64encode(new_content.encode()).decode(),
        "branch": branch,
    }
    if file_sha:
        put_body["sha"] = file_sha
    _tc_gh_put(f"/repos/{owner}/{repo}/contents/{path}", put_body)

    # Create Draft PR
    pr = _tc_gh_post(f"/repos/{owner}/{repo}/pulls", {
        "title": title or f"[Toolchain] {message[:80]}",
        "body": body or (
            "Erstellt von **Sovereign App Toolchain**.\n\n"
            "- Kein direkter Push auf `main`\n"
            "- Muss manuell gemergt werden\n"
            "- Erstellt mit `confirm=True` nach User-Bestätigung"
        ),
        "head": branch,
        "base": default_branch,
        "draft": True,
    })
    return {
        "pr_number":  pr.get("number"),
        "pr_url":     pr.get("html_url"),
        "branch":     branch,
        "base":       default_branch,
        "draft":      True,
    }


# ── Toolchain routes ──────────────────────────────────────────────────────────

@app.route("/api/toolchain/user-tools")
@require_session
def tc_user_tools():
    """List available tools for the logged-in user (auto-loads in app)."""
    uid = request.session_user_id
    user_row = query("SELECT role FROM admin_users WHERE id = %s::uuid LIMIT 1", (uid,), one=True)
    role = (user_row["role"] if user_row else "user") or "user"

    tools = [
        {"id": "github_read_file",      "label": "GitHub Datei lesen",       "write": False},
        {"id": "github_list_directory", "label": "GitHub Verzeichnis listen", "write": False},
        {"id": "github_list_branches",  "label": "GitHub Branches listen",   "write": False},
        {"id": "github_search_code",    "label": "GitHub Code suchen",       "write": False},
        {"id": "preview_patch",         "label": "Patch-Vorschau",           "write": False},
        {"id": "sandbox_plan",          "label": "Sandbox-Plan",             "write": False},
    ]
    if role in ("admin", "superadmin"):
        tools += [
            {"id": "create_draft_pr",      "label": "Draft PR erstellen",      "write": True,  "confirm_required": True},
            {"id": "apply_patch_worker",   "label": "Patch Worker aufrufen",   "write": True,  "confirm_required": True},
        ]
    return jsonify({
        "tools":         tools,
        "allowed_repos": _TC_ALLOWED_REPOS,
        "rules": {
            "auto_load":          True,
            "github_read":        "after_login",
            "auto_write":         False,
            "push_to_main":       False,
            "pr_mode":            "draft_only",
            "confirm_required":   True,
            "audit_log":          True,
        },
    })


@app.route("/api/toolchain/github/read-file", methods=["POST"])
@require_session
def tc_github_read_file():
    try:
        b     = request.get_json(force=True) or {}
        owner = b.get("owner", "")
        repo  = b.get("repo", "")
        path  = b.get("path", "")
        ref   = b.get("ref")
        if not owner or not repo or not path:
            return jsonify({"error": "owner, repo und path erforderlich"}), 400
        data = _tc_read_github_file(owner, repo, path, ref)
        _tc_audit(request.session_user_id, "read_file", {"owner": owner, "repo": repo, "path": path})
        content = data["content"]
        if len(content) > 60_000:
            content = content[:60_000]
            data["truncated"] = True
        data["content"] = content
        return jsonify(data)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/github/list-directory", methods=["POST"])
@require_session
def tc_github_list_directory():
    try:
        b     = request.get_json(force=True) or {}
        owner = b.get("owner", "")
        repo  = b.get("repo", "")
        path  = b.get("path", "")
        ref   = b.get("ref")
        if not owner or not repo:
            return jsonify({"error": "owner und repo erforderlich"}), 400
        _tc_allowed(owner, repo)
        qs = f"?ref={urllib.parse.quote(ref)}" if ref else ""
        items = _tc_gh_get(f"/repos/{owner}/{repo}/contents/{path}{qs}")
        if not isinstance(items, list):
            items = [items]
        _tc_audit(request.session_user_id, "list_dir", {"owner": owner, "repo": repo, "path": path})
        return jsonify({"items": [
            {"name": i["name"], "type": i["type"], "path": i["path"], "size": i.get("size")}
            for i in items
        ]})
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/github/list-branches", methods=["POST"])
@require_session
def tc_github_list_branches():
    try:
        b     = request.get_json(force=True) or {}
        owner = b.get("owner", "")
        repo  = b.get("repo", "")
        if not owner or not repo:
            return jsonify({"error": "owner und repo erforderlich"}), 400
        _tc_allowed(owner, repo)
        branches = _tc_gh_get(f"/repos/{owner}/{repo}/branches?per_page=50")
        _tc_audit(request.session_user_id, "list_branches", {"owner": owner, "repo": repo})
        return jsonify({"branches": [{"name": br["name"]} for br in (branches or [])]})
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/github/search-code", methods=["POST"])
@require_session
def tc_github_search_code():
    try:
        b     = request.get_json(force=True) or {}
        owner = b.get("owner", "")
        repo  = b.get("repo", "")
        query_str = b.get("q", "")
        if not owner or not repo or not query_str:
            return jsonify({"error": "owner, repo und q erforderlich"}), 400
        _tc_allowed(owner, repo)
        q    = urllib.parse.quote(f"{query_str} repo:{owner}/{repo}")
        data = _tc_gh_get(f"/search/code?q={q}&per_page=20")
        _tc_audit(request.session_user_id, "search_code", {"owner": owner, "repo": repo, "q": query_str})
        return jsonify({"items": [
            {"path": i["path"], "html_url": i.get("html_url")}
            for i in (data.get("items") or [])
        ], "total": data.get("total_count", 0)})
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/preview-patch", methods=["POST"])
@require_session
def tc_preview_patch():
    """Preview SEARCH/REPLACE blocks against a GitHub file — read-only."""
    try:
        b      = request.get_json(force=True) or {}
        owner  = b.get("owner", "")
        repo   = b.get("repo", "")
        path   = b.get("path", "")
        blocks = b.get("blocks", [])
        ref    = b.get("ref")
        if not owner or not repo or not path or not blocks:
            return jsonify({"error": "owner, repo, path und blocks erforderlich"}), 400

        current = _tc_read_github_file(owner, repo, path, ref)
        before  = current["content"]
        after, report = _tc_apply_blocks(before, blocks)
        diff    = _tc_unified_diff(before, after, path)

        _tc_audit(request.session_user_id, "preview_patch",
                  {"owner": owner, "repo": repo, "path": path, "blocks": len(blocks)})
        return jsonify({
            "ok":           True,
            "write_action": False,
            "base_sha":     current["sha"],
            "block_report": report,
            "diff":         diff,
            "lines_before": before.count("\n"),
            "lines_after":  after.count("\n"),
        })
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/create-draft-pr", methods=["POST"])
@require_session
def tc_create_draft_pr():
    """Create a GitHub Draft PR. confirm=True required. Direct push to main: never."""
    try:
        b       = request.get_json(force=True) or {}
        owner   = b.get("owner", "")
        repo    = b.get("repo", "")
        path    = b.get("path", "")
        message = b.get("message", "")
        blocks  = b.get("blocks", [])
        confirm = b.get("confirm", False)

        if not all([owner, repo, path, message, blocks]):
            return jsonify({"error": "owner, repo, path, message und blocks erforderlich"}), 400

        if not confirm:
            # Preview only — no write
            try:
                current = _tc_read_github_file(owner, repo, path)
                after, report = _tc_apply_blocks(current["content"], blocks)
                diff = _tc_unified_diff(current["content"], after, path)
            except Exception as prev_err:
                diff, report = str(prev_err), []
            return jsonify({
                "created":       False,
                "reason":        "confirm=True ist erforderlich für Write-Actions",
                "write_mode":    "draft_pr_only",
                "preview_diff":  diff,
                "block_report":  report,
            })

        # Check admin role for write actions
        uid      = request.session_user_id
        user_row = query("SELECT role FROM admin_users WHERE id = %s::uuid LIMIT 1", (uid,), one=True)
        if not user_row or user_row.get("role") not in ("admin", "superadmin"):
            return jsonify({"error": "Nur Admins dürfen PRs erstellen"}), 403

        current  = _tc_read_github_file(owner, repo, path)
        new_content, report = _tc_apply_blocks(current["content"], blocks)
        diff     = _tc_unified_diff(current["content"], new_content, path)
        pr       = _tc_create_draft_pr(
            owner=owner, repo=repo, path=path,
            new_content=new_content, message=message,
            branch_name=b.get("branch_name"),
            title=b.get("title"),
            body=b.get("body"),
            base_branch=b.get("base_branch"),
        )
        _tc_audit(uid, "create_draft_pr", {
            "owner": owner, "repo": repo, "path": path,
            "pr_url": pr.get("pr_url"), "blocks": len(blocks),
        })
        return jsonify({
            "created":      True,
            "write_mode":   "draft_pr_only",
            "block_report": report,
            "diff":         diff,
            **pr,
        })
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/apply-patch-worker", methods=["POST"])
@require_session
def tc_apply_patch_worker():
    """Send SEARCH/REPLACE blocks to the external Sovereign patch worker. confirm=True required."""
    try:
        b       = request.get_json(force=True) or {}
        owner   = b.get("owner", "")
        repo    = b.get("repo", "")
        path    = b.get("path", "")
        message = b.get("message", "")
        blocks  = b.get("blocks", [])
        confirm = b.get("confirm", False)
        worker  = b.get("worker_url", _TC_WORKER_URL)

        if not all([owner, repo, path, message, blocks]):
            return jsonify({"error": "owner, repo, path, message und blocks erforderlich"}), 400

        payload = {"owner": owner, "repo": repo, "path": path, "message": message, "blocks": blocks}

        if not confirm:
            return jsonify({
                "sent":    False,
                "reason":  "confirm=True ist erforderlich",
                "payload": payload,
                "worker":  worker,
            })

        uid      = request.session_user_id
        user_row = query("SELECT role FROM admin_users WHERE id = %s::uuid LIMIT 1", (uid,), one=True)
        if not user_row or user_row.get("role") not in ("admin", "superadmin"):
            return jsonify({"error": "Nur Admins dürfen den Patch Worker aufrufen"}), 403

        _tc_allowed(owner, repo)
        resp = requests.post(worker, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json() if resp.content else {}
        _tc_audit(uid, "apply_patch_worker", {
            "owner": owner, "repo": repo, "path": path,
            "worker": worker, "status": resp.status_code,
        })
        return jsonify({"sent": True, "status": resp.status_code, "response": result})
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/sandbox-plan", methods=["POST"])
@require_session
def tc_sandbox_plan():
    """Plan Playwright/verify/doctor commands for a given goal — read-only."""
    b    = request.get_json(force=True) or {}
    goal = (b.get("goal") or "").strip()

    COMMANDS = {
        "verify":   "pnpm run verify",
        "typecheck":"pnpm run type-check",
        "test":     "pnpm run test:smoke",
        "build":    "pnpm run build",
        "apk":      "pnpm run build:apk:debug",
        "doctor":   "pnpm exec playwright install --with-deps && pnpm run test:e2e",
        "lint":     "pnpm run lint",
        "audit":    "pnpm run audit:sovereign",
    }
    detected = []
    goal_l   = goal.lower()
    if any(w in goal_l for w in ("type", "ts", "typescript")):  detected.append(COMMANDS["typecheck"])
    if any(w in goal_l for w in ("smoke", "test")):             detected.append(COMMANDS["test"])
    if any(w in goal_l for w in ("build", "bundle")):           detected.append(COMMANDS["build"])
    if any(w in goal_l for w in ("apk", "android", "play")):   detected.append(COMMANDS["apk"])
    if any(w in goal_l for w in ("playwright", "e2e", "doctor")): detected.append(COMMANDS["doctor"])
    if any(w in goal_l for w in ("lint",)):                     detected.append(COMMANDS["lint"])
    if any(w in goal_l for w in ("audit", "security")):         detected.append(COMMANDS["audit"])
    if not detected:                                            detected.append(COMMANDS["verify"])

    _tc_audit(request.session_user_id, "sandbox_plan", {"goal": goal, "commands": detected})
    return jsonify({
        "goal":     goal,
        "commands": detected,
        "note":     "Node 22 + pnpm 9 + Playwright. Ausführen im Repo-Root.",
        "rules": {
            "push_to_main": False,
            "draft_pr":     True,
            "confirm":      True,
        },
    })


@app.route("/api/toolchain/audit-log")
@require_session
def tc_audit_log():
    """Return toolchain audit log entries for the current user."""
    try:
        uid      = request.session_user_id
        user_row = query("SELECT role FROM admin_users WHERE id = %s::uuid LIMIT 1", (uid,), one=True)
        role     = (user_row["role"] if user_row else "user") or "user"

        if role in ("admin", "superadmin"):
            rows = query(
                """SELECT id::text, admin_email, action, target_id, changes,
                          to_char(created_at,'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS ts
                   FROM audit_log WHERE action LIKE 'toolchain:%'
                   ORDER BY created_at DESC LIMIT 100"""
            )
        else:
            rows = query(
                """SELECT id::text, admin_email, action, target_id, changes,
                          to_char(created_at,'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS ts
                   FROM audit_log WHERE action LIKE 'toolchain:%' AND admin_id = %s::uuid
                   ORDER BY created_at DESC LIMIT 50""",
                (uid,),
            )
        return jsonify({"entries": [dict(r) for r in (rows or [])]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# SOVEREIGN SKILL SYSTEM  —  /api/toolchain/skills/*
#
# Scannt beliebige Repos nach Skills (Replit, Cursor, Claude, MCP, Custom),
# adaptiert sie ans Sovereign-System und speichert sie als user_skills.
# Keine Schreibzugriffe auf GitHub — nur Lesen + lokale DB-Speicherung.
# ═════════════════════════════════════════════════════════════════════════════

import re as _re
import unicodedata as _unicodedata

# Erkennungsmuster je Framework
_SKILL_PATTERNS = [
    # (glob-pattern, framework, is_dir_listing)
    (".agents/skills",         "replit",  True),   # .agents/skills/*/SKILL.md
    (".cursor/rules",          "cursor",  True),    # .cursor/rules/*.md
    ("prompts",                "generic", True),    # prompts/*.md
    ("skills",                 "generic", True),    # skills/*.md
    ("tools",                  "generic", True),    # tools/*.md
    (".cursorrules",           "cursor",  False),
    ("CLAUDE.md",              "claude",  False),
    ("AGENTS.md",              "openai",  False),
    ("GEMINI.md",              "gemini",  False),
    ("server.py",              "fastmcp", False),
    ("src/agents",             "generic", True),
    ("agents",                 "generic", True),
]

_SKILL_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".json"}


def _slugify(text: str) -> str:
    text = _unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if c.isascii())
    text = _re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:48] or "skill"


def _detect_framework_from_content(content: str) -> str:
    if "FastMCP" in content or "@mcp.tool" in content:
        return "fastmcp"
    if "SOVEREIGN" in content or "sovereign" in content.lower():
        return "replit"
    if "cursor" in content.lower():
        return "cursor"
    return "generic"


def _extract_skill_meta(content: str, path: str, framework: str) -> dict:
    """Rule-based extraction: name, description, adapted_prompt from any skill content."""
    lines = content.splitlines()

    # Name from first heading or filename
    name = None
    for line in lines[:20]:
        m = _re.match(r"^#+\s+(.+)", line.strip())
        if m:
            name = m.group(1).strip().strip("*_")
            break
    if not name:
        name = path.split("/")[-1].replace(".md", "").replace("_", " ").replace("-", " ").title()

    # Description: first non-empty, non-heading paragraph
    description = ""
    in_para = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---"):
            if in_para:
                break
            continue
        if stripped.startswith(("```", "<!--", ">", "|", "-", "*", "1.")):
            continue
        description += " " + stripped
        in_para = True
        if len(description) > 300:
            break
    description = description.strip()[:280]

    # For FastMCP: extract @mcp.tool function names as description
    if framework == "fastmcp":
        tools = _re.findall(r"@mcp\.tool\(\)\s*\ndef (\w+)", content)
        if tools:
            description = f"MCP Tools: {', '.join(tools[:6])}"

    # Adapted prompt: cleaned version of the full content (capped at 4000 chars)
    adapted = content[:4000].strip()

    slug = _slugify(name)
    return {"name": name, "slug": slug, "description": description or name, "adapted_prompt": adapted}


def _gh_list_tree(owner: str, repo: str, ref: str | None = None, max_items: int = 300) -> list[dict]:
    """Fetch full file tree from GitHub (recursive). Returns list of {path, type, size}."""
    qs = f"?recursive=1"
    if ref:
        qs += f"&ref={urllib.parse.quote(ref)}"
    data = _tc_gh_get(f"/repos/{owner}/{repo}/git/trees/{ref or 'HEAD'}{qs}")
    return [
        {"path": item["path"], "type": item["type"], "size": item.get("size", 0)}
        for item in (data.get("tree") or [])
        if item.get("type") == "blob"
    ][:max_items]


def _scan_tree_for_skills(tree: list[dict]) -> list[dict]:
    """Detect skill files from a repo tree using known patterns."""
    found = []
    seen_paths = set()

    for item in tree:
        path = item["path"]
        if path in seen_paths:
            continue
        pl = path.lower()
        framework = None
        name = None

        # Exact known files
        basename = path.split("/")[-1]
        if basename in ("CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules", "server.py"):
            if basename == "server.py":
                framework = "fastmcp"
            elif basename == "CLAUDE.md":
                framework = "claude"
            elif basename == "AGENTS.md":
                framework = "openai"
            elif basename == "GEMINI.md":
                framework = "gemini"
            elif basename == ".cursorrules":
                framework = "cursor"

        # Pattern: .agents/skills/*/SKILL.md
        if ".agents/skills/" in path and basename.upper() == "SKILL.MD":
            framework = "replit"
            # Name from parent folder
            parts = path.split("/")
            idx = parts.index("skills") if "skills" in parts else -1
            if idx >= 0 and idx + 1 < len(parts):
                name = parts[idx + 1].replace("-", " ").replace("_", " ").title()

        # Pattern: .cursor/rules/*.md
        elif ".cursor/rules/" in path and path.endswith(".md"):
            framework = "cursor"

        # Pattern: skills/*.md, prompts/*.md, tools/*.md, agents/*.md
        elif not framework:
            top_dir = path.split("/")[0].lower() if "/" in path else ""
            if top_dir in ("skills", "prompts", "tools", "agents", "src/agents") and \
               any(path.endswith(ext) for ext in _SKILL_EXTENSIONS):
                framework = "generic"
            elif path.endswith(".skill.md"):
                framework = "generic"

        if framework:
            ext = "." + path.rsplit(".", 1)[-1] if "." in basename else ""
            if ext and ext not in _SKILL_EXTENSIONS and framework != "fastmcp":
                continue
            if not name:
                name = basename.replace(".md", "").replace(".txt", "").replace("_", " ").replace("-", " ").title()
            found.append({
                "path": path,
                "name": name or basename,
                "framework": framework,
                "size": item.get("size", 0),
                "preview": "",
            })
            seen_paths.add(path)

    return found[:40]  # cap at 40 results


@app.route("/api/toolchain/skills/scan", methods=["POST"])
@require_session
def tc_skills_scan():
    """Scan a GitHub repo for skill files — detect any framework/structure."""
    try:
        b     = request.get_json(force=True) or {}
        owner = b.get("owner", "").strip()
        repo  = b.get("repo", "").strip()
        ref   = b.get("ref")
        if not owner or not repo:
            return jsonify({"error": "owner und repo erforderlich"}), 400
        _tc_allowed(owner, repo)

        tree  = _gh_list_tree(owner, repo, ref)
        found = _scan_tree_for_skills(tree)

        # Get previews (first 200 chars) for top 10 results
        for item in found[:10]:
            try:
                data = _tc_gh_get(
                    f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(item['path'])}"
                    + (f"?ref={urllib.parse.quote(ref)}" if ref else "")
                )
                raw = base64.b64decode(data.get("content", "").replace("\n", ""))
                preview = raw.decode("utf-8", errors="replace")[:200]
                item["preview"] = preview
            except Exception:
                pass

        frameworks = list({f["framework"] for f in found})
        _tc_audit(request.session_user_id, "skill_scan",
                  {"owner": owner, "repo": repo, "found": len(found)})
        return jsonify({
            "owner": owner, "repo": repo,
            "found": found, "total": len(found),
            "frameworks_detected": frameworks,
        })
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/skills/read", methods=["POST"])
@require_session
def tc_skills_read():
    """Read a specific skill file from GitHub and detect its framework."""
    try:
        b     = request.get_json(force=True) or {}
        owner = b.get("owner", "")
        repo  = b.get("repo", "")
        path  = b.get("path", "")
        if not owner or not repo or not path:
            return jsonify({"error": "owner, repo und path erforderlich"}), 400
        data = _tc_read_github_file(owner, repo, path)
        content = data["content"]
        # Detect framework from path + content
        framework = "generic"
        if ".agents/skills/" in path and path.endswith("SKILL.md"):
            framework = "replit"
        elif ".cursor/rules/" in path or path.endswith(".cursorrules"):
            framework = "cursor"
        elif path.endswith("CLAUDE.md"):
            framework = "claude"
        elif path.endswith("AGENTS.md"):
            framework = "openai"
        elif path.endswith("server.py"):
            framework = _detect_framework_from_content(content)
        else:
            framework = _detect_framework_from_content(content)
        _tc_audit(request.session_user_id, "skill_read",
                  {"owner": owner, "repo": repo, "path": path})
        return jsonify({"content": content[:8000], "framework": framework, "sha": data["sha"]})
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/skills/adapt", methods=["POST"])
@require_session
def tc_skills_adapt():
    """Rule-based adaptation of a skill to the Sovereign system."""
    try:
        b       = request.get_json(force=True) or {}
        owner   = b.get("owner", "")
        repo    = b.get("repo", "")
        path    = b.get("path", "")
        content = b.get("raw_content", "")
        framework = b.get("framework", "generic")
        if not content:
            return jsonify({"error": "raw_content erforderlich"}), 400
        meta = _extract_skill_meta(content, path, framework)
        _tc_audit(request.session_user_id, "skill_adapt",
                  {"owner": owner, "repo": repo, "path": path, "name": meta["name"]})
        return jsonify({**meta, "framework": framework})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/skills/install", methods=["POST"])
@require_session
def tc_skills_install():
    """Save an adapted skill to the user's library (user_skills table)."""
    try:
        b   = request.get_json(force=True) or {}
        uid = request.session_user_id
        name  = (b.get("name") or "").strip()[:120]
        slug  = _slugify(name or b.get("slug", "skill"))
        descr = (b.get("description") or "")[:500]
        srepo = (b.get("source_repo") or "")[:200]
        spath = (b.get("source_path") or "")[:500]
        frame = (b.get("framework") or "generic")[:40]
        prompt= (b.get("adapted_prompt") or "")[:8000]
        if not name:
            return jsonify({"error": "name erforderlich"}), 400

        existing = query(
            "SELECT id FROM user_skills WHERE user_id=%s::uuid AND slug=%s LIMIT 1",
            (uid, slug), one=True,
        )
        if existing:
            query(
                """UPDATE user_skills SET name=%s, description=%s, source_repo=%s,
                   source_path=%s, framework=%s, adapted_prompt=%s, is_active=true
                   WHERE id=%s::uuid""",
                (name, descr, srepo, spath, frame, prompt, str(existing["id"])),
                write=True,
            )
            skill_id = str(existing["id"])
        else:
            rows = query(
                """INSERT INTO user_skills
                   (user_id, name, slug, description, source_repo, source_path, framework, adapted_prompt)
                   VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (uid, name, slug, descr, srepo, spath, frame, prompt),
                write=True,
            )
            skill_id = str(rows[0]["id"]) if rows else "unknown"

        _tc_audit(uid, "skill_install", {"name": name, "slug": slug, "framework": frame})
        return jsonify({"id": skill_id, "slug": slug, "installed": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/skills/list")
@require_session
def tc_skills_list():
    """List all installed skills for the current user."""
    try:
        uid  = request.session_user_id
        rows = query(
            """SELECT id::text, name, slug, description, source_repo, source_path,
                      framework, adapted_prompt, is_active,
                      to_char(created_at,'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS created_at
               FROM user_skills WHERE user_id=%s::uuid ORDER BY created_at DESC""",
            (uid,),
        )
        return jsonify({"skills": [dict(r) for r in (rows or [])]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/skills/<skill_id>/toggle", methods=["POST"])
@require_session
def tc_skills_toggle(skill_id: str):
    """Toggle a skill on/off."""
    try:
        uid       = request.session_user_id
        b         = request.get_json(force=True) or {}
        is_active = bool(b.get("is_active", True))
        query(
            "UPDATE user_skills SET is_active=%s WHERE id=%s::uuid AND user_id=%s::uuid",
            (is_active, skill_id, uid), write=True,
        )
        return jsonify({"ok": True, "is_active": is_active})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/toolchain/skills/<skill_id>", methods=["DELETE"])
@require_session
def tc_skills_delete(skill_id: str):
    """Delete a skill from the user's library."""
    try:
        uid = request.session_user_id
        query(
            "DELETE FROM user_skills WHERE id=%s::uuid AND user_id=%s::uuid",
            (skill_id, uid), write=True,
        )
        _tc_audit(uid, "skill_delete", {"skill_id": skill_id})
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# WEB ADMIN PANEL  —  /admin
# Self-contained single-page admin UI served directly from Flask.
# No build step required. Auth via ADMIN_API_KEY (Bearer token).
# ═════════════════════════════════════════════════════════════════════════════

_ADMIN_PANEL_HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Sovereign Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--surface:#161b22;--border:#30363d;--accent:#58a6ff;
  --accent2:#3fb950;--danger:#f85149;--warn:#d29922;
  --text:#e6edf3;--muted:#8b949e;--radius:8px;
}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh}
a{color:var(--accent);text-decoration:none}

/* ── Login ── */
#login{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:16px}
.login-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:40px;width:100%;max-width:420px}
.login-card h1{font-size:22px;margin-bottom:6px}
.login-card p{color:var(--muted);font-size:14px;margin-bottom:24px}
.login-err{background:#2d1117;border:1px solid var(--danger);border-radius:var(--radius);color:var(--danger);font-size:13px;padding:10px 14px;margin-bottom:14px;display:none}

/* ── Layout ── */
#app{display:none;flex-direction:column;min-height:100vh}
header{background:var(--surface);border-bottom:1px solid var(--border);padding:0 24px;display:flex;align-items:center;gap:16px;height:56px}
header .logo{font-weight:700;font-size:16px;letter-spacing:.5px}
header .logo span{color:var(--accent)}
header nav{display:flex;gap:2px;margin-left:8px}
header nav button{background:none;border:none;color:var(--muted);cursor:pointer;font-size:14px;padding:6px 14px;border-radius:6px;transition:all .15s}
header nav button.active{background:#21262d;color:var(--text)}
header nav button:hover:not(.active){color:var(--text)}
.logout{margin-left:auto;background:none;border:1px solid var(--border);color:var(--muted);cursor:pointer;font-size:13px;padding:5px 12px;border-radius:6px}
.logout:hover{border-color:var(--danger);color:var(--danger)}

main{padding:28px 24px;max-width:960px;width:100%}

/* ── Sections ── */
.section{display:none}
.section.active{display:block}

h2{font-size:18px;margin-bottom:20px;font-weight:600}
.subtitle{color:var(--muted);font-size:13px;margin-top:2px;margin-bottom:20px}

/* ── Cards ── */
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:12px}
.card-header{display:flex;align-items:center;gap:12px;cursor:pointer;user-select:none}
.card-title{font-weight:600;font-size:15px;flex:1}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;font-weight:600}
.badge.on{background:#1a3a1a;color:var(--accent2)}
.badge.off{background:#2d1a1a;color:var(--muted)}
.card-body{margin-top:18px;border-top:1px solid var(--border);padding-top:18px;display:none}
.card.open .card-body{display:block}
.chevron{color:var(--muted);font-size:12px;transition:transform .2s}
.card.open .chevron{transform:rotate(180deg)}

/* ── Toggle ── */
.toggle-row{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.toggle-label{font-size:14px;color:var(--muted)}
.toggle{position:relative;display:inline-block;width:42px;height:24px}
.toggle input{opacity:0;width:0;height:0}
.slider{position:absolute;inset:0;background:#30363d;border-radius:24px;cursor:pointer;transition:.2s}
.slider:before{content:'';position:absolute;width:18px;height:18px;left:3px;bottom:3px;background:#8b949e;border-radius:50%;transition:.2s}
input:checked+.slider{background:#1a3a1a}
input:checked+.slider:before{transform:translateX(18px);background:var(--accent2)}

/* ── Form ── */
.form-group{margin-bottom:14px}
.form-group label{display:block;font-size:12px;color:var(--muted);margin-bottom:5px;text-transform:uppercase;letter-spacing:.5px}
.form-group input,.form-group select,.form-group textarea{
  width:100%;background:#0d1117;border:1px solid var(--border);border-radius:6px;
  color:var(--text);font-size:14px;padding:8px 12px;outline:none;transition:border .15s;
  font-family:inherit
}
.form-group textarea{min-height:90px;resize:vertical}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{border-color:var(--accent)}
.form-group select option{background:#161b22}

.btn{border:none;border-radius:6px;cursor:pointer;font-size:14px;font-weight:600;padding:8px 18px;transition:opacity .15s}
.btn:hover{opacity:.85}
.btn-primary{background:var(--accent);color:#0d1117}
.btn-danger{background:var(--danger);color:#fff}
.btn-ghost{background:#21262d;color:var(--text);border:1px solid var(--border)}
.btn-row{display:flex;gap:8px;margin-top:18px}

.msg{font-size:13px;padding:8px 12px;border-radius:6px;margin-top:10px;display:none}
.msg.ok{background:#1a3a1a;color:var(--accent2)}
.msg.err{background:#2d1117;color:var(--danger)}

/* ── Package table ── */
.pkg-grid{display:grid;grid-template-columns:2fr 1fr 1fr 1fr 80px;gap:1px;background:var(--border);border-radius:var(--radius);overflow:hidden}
.pkg-grid .cell{background:var(--surface);padding:10px 14px;font-size:14px;display:flex;align-items:center}
.pkg-grid .head{background:#21262d;color:var(--muted);font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}

/* ── Spinner ── */
.spin{display:inline-block;width:16px;height:16px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle;margin-left:6px}
@keyframes spin{to{transform:rotate(360deg)}}

/* inputs */
input[type=text],input[type=password]{-webkit-appearance:none}
</style>
</head>
<body>

<!-- LOGIN -->
<div id="login">
  <div class="login-card">
    <h1>⚙️ Sovereign Admin</h1>
    <p>Bitte Admin-API-Key eingeben.</p>
    <div class="login-err" id="loginErr"></div>
    <div class="form-group">
      <label>Admin API Key</label>
      <input type="password" id="keyInput" placeholder="8516ae…" autocomplete="off"/>
    </div>
    <button class="btn btn-primary" style="width:100%" onclick="doLogin()">Anmelden</button>
  </div>
</div>

<!-- APP -->
<div id="app">
  <header>
    <div class="logo">Sovereign <span>Admin</span></div>
    <nav>
      <button class="active" onclick="showSection('payments',this)">💳 Zahlungen</button>
      <button onclick="showSection('packages',this)">📦 Credit-Pakete</button>
      <button onclick="showSection('users',this)">👥 Users</button>
      <button onclick="showSection('billing',this)">📋 Billing</button>
      <button onclick="showSection('llm',this)">🤖 LLM Routes</button>
      <button onclick="showSection('tools',this)">🛠️ Tools</button>
      <button onclick="showSection('runtime',this)">🔧 Runtime</button>
      <button onclick="showSection('audit',this)">📊 Audit</button>
    </nav>
    <button class="logout" onclick="doLogout()">Abmelden</button>
  </header>
  <main>

    <!-- PAYMENTS -->
    <div id="s-payments" class="section active">
      <h2>Zahlungsmethoden</h2>
      <div class="subtitle">Methoden aktivieren und Zugangsdaten hinterlegen.</div>
      <div id="pmList"><div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div></div>
    </div>

    <!-- PACKAGES -->
    <div id="s-packages" class="section">
      <h2>Credit-Pakete</h2>
      <div class="subtitle">Verfügbare Käufe für Nutzer.</div>
      <div id="pkgList"><div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div></div>
    </div>

    <!-- USERS -->
    <div id="s-users" class="section">
      <h2>User Manager</h2>
      <div class="subtitle">User suchen, bearbeiten, Credits anpassen.</div>
      <div class="form-group" style="margin-bottom:16px">
        <input type="text" id="userSearch" placeholder="Suche nach E-Mail, Name…" onkeydown="if(event.key==='Enter')loadUsers()"/>
        <button class="btn btn-primary" style="margin-top:8px" onclick="loadUsers()">Suchen</button>
      </div>
      <div id="userList"><div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div></div>
    </div>

    <!-- BILLING -->
    <div id="s-billing" class="section">
      <h2>Billing History</h2>
      <div class="subtitle">Alle Transaktionen und Zahlungen.</div>
      <div class="form-group" style="display:flex;gap:8px;margin-bottom:16px">
        <input type="text" id="billingUserId" placeholder="User ID (optional)" style="flex:1"/>
        <select id="billingType" style="width:160px">
          <option value="">Alle Typen</option>
          <option value="purchase">Purchase</option>
          <option value="adjustment">Adjustment</option>
          <option value="refund">Refund</option>
          <option value="spend">Spend</option>
        </select>
        <button class="btn btn-primary" onclick="loadBilling()">Filtern</button>
      </div>
      <div id="billingList"><div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div></div>
    </div>

    <!-- LLM ROUTES -->
    <div id="s-llm" class="section">
      <h2>LLM Routes</h2>
      <div class="subtitle">Provider aktivieren, deaktivieren, Reihenfolge ändern.</div>
      <div id="llmList"><div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div></div>
    </div>

    <!-- TOOLS -->
    <div id="s-tools" class="section">
      <h2>Tools & Executors</h2>
      <div class="subtitle">Workspace-Tools und Executor-Routen verwalten.</div>
      <div id="toolsList"><div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div></div>
    </div>

    <!-- RUNTIME -->
    <div id="s-runtime" class="section">
      <h2>Runtime Settings</h2>
      <div class="subtitle">Worker, BYOK-Modus und CORS-Konfiguration.</div>
      <div id="runtimeList"><div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div></div>
    </div>

    <!-- AUDIT -->
    <div id="s-audit" class="section">
      <h2>Audit Log</h2>
      <div class="subtitle">Alle Admin-Aktionen im Überblick.</div>
      <div id="auditList"><div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div></div>
    </div>

  </main>
</div>

<script>
const BASE = '';
let API_KEY = sessionStorage.getItem('sov_admin_key') || '';
if (API_KEY) initApp();

function hdr(){ return {'Authorization':'Bearer '+API_KEY,'Content-Type':'application/json'}; }

async function doLogin(){
  const k = document.getElementById('keyInput').value.trim();
  if(!k) return;
  const r = await fetch(BASE+'/api/admin/payment-methods',{headers:{'Authorization':'Bearer '+k}});
  if(r.status===401||r.status===403||r.status===503){
    const e = document.getElementById('loginErr');
    e.textContent='Ungültiger API-Key.'; e.style.display='block'; return;
  }
  API_KEY = k;
  sessionStorage.setItem('sov_admin_key', k);
  initApp();
}

document.getElementById('keyInput').addEventListener('keydown',e=>{ if(e.key==='Enter') doLogin(); });

function doLogout(){
  sessionStorage.removeItem('sov_admin_key');
  API_KEY='';
  document.getElementById('app').style.display='none';
  document.getElementById('login').style.display='flex';
}

function initApp(){
  document.getElementById('login').style.display='none';
  document.getElementById('app').style.display='flex';
  loadPaymentMethods();
  loadPackages();
  loadUsers();
  loadBilling();
  loadLLMRoutes();
  loadTools();
  loadRuntime();
  loadAudit();
}

function showSection(id, btn){
  document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));
  document.querySelectorAll('header nav button').forEach(b=>b.classList.remove('active'));
  document.getElementById('s-'+id).classList.add('active');
  btn.classList.add('active');
}

/* ────── PAYMENT METHODS ────── */
const CONFIG_FIELDS = {
  paypal:[
    {key:'client_id',label:'Client ID',type:'text'},
    {key:'client_secret',label:'Client Secret',type:'password'},
    {key:'mode',label:'Modus',type:'select',options:['sandbox','live']},
    {key:'webhook_id',label:'Webhook ID (optional)',type:'text'},
  ],
  skrill:[
    {key:'merchant_email',label:'Merchant Email',type:'text'},
    {key:'secret_word',label:'Secret Word',type:'password'},
  ],
  crypto_btc:[{key:'wallet_address',label:'BTC Wallet-Adresse',type:'text'}],
  crypto_eth:[{key:'wallet_address',label:'ETH Wallet-Adresse',type:'text'}],
  crypto_usdt:[
    {key:'wallet_address',label:'USDT Wallet-Adresse',type:'text'},
    {key:'network',label:'Netzwerk',type:'select',options:['TRC20','ERC20']},
  ],
  google_play:[
    {key:'package_name',label:'Package Name',type:'text'},
    {key:'service_account_json',label:'Service Account JSON',type:'textarea'},
  ],
};

let pmData = [];

async function loadPaymentMethods(){
  const r = await fetch(BASE+'/api/admin/payment-methods',{headers:hdr()});
  const d = await r.json();
  pmData = d.paymentMethods || [];
  renderPM();
}

function renderPM(){
  const el = document.getElementById('pmList');
  if(!pmData.length){ el.innerHTML='<div style="color:var(--muted);font-size:14px">Keine Methoden gefunden. Seed-Endpunkt bereits aufgerufen?</div>'; return; }
  el.innerHTML = pmData.map((m,i)=>pmCard(m,i)).join('');
}

function pmCard(m,i){
  const fields = CONFIG_FIELDS[m.type] || [];
  const fieldsHtml = fields.map(f=>{
    const val = (m.config||{})[f.key]||'';
    if(f.type==='select'){
      const opts = f.options.map(o=>`<option value="${o}"${val===o?' selected':''}>${o}</option>`).join('');
      return `<div class="form-group"><label>${f.label}</label><select id="f_${m.id}_${f.key}">${opts}</select></div>`;
    }
    if(f.type==='textarea'){
      return `<div class="form-group"><label>${f.label}</label><textarea id="f_${m.id}_${f.key}" placeholder="{ … }">${esc(val)}</textarea></div>`;
    }
    return `<div class="form-group"><label>${f.label}</label><input type="${f.type}" id="f_${m.id}_${f.key}" value="${esc(val)}" autocomplete="off"/></div>`;
  }).join('');
  return `<div class="card" id="card_${m.id}">
    <div class="card-header" onclick="toggleCard('${m.id}')">
      <span class="card-title">${esc(m.label)}</span>
      <span class="badge ${m.enabled?'on':'off'}">${m.enabled?'Aktiv':'Inaktiv'}</span>
      <span class="chevron">▼</span>
    </div>
    <div class="card-body">
      <div class="toggle-row">
        <span class="toggle-label">Methode aktivieren</span>
        <label class="toggle">
          <input type="checkbox" id="tog_${m.id}" ${m.enabled?'checked':''} onchange="toggleEnabled('${m.id}',this.checked)"/>
          <span class="slider"></span>
        </label>
      </div>
      ${fieldsHtml}
      <div class="btn-row">
        <button class="btn btn-primary" onclick="saveConfig('${m.id}','${m.type}')">Speichern</button>
      </div>
      <div class="msg" id="msg_${m.id}"></div>
    </div>
  </div>`;
}

function toggleCard(id){
  document.getElementById('card_'+id).classList.toggle('open');
}

async function toggleEnabled(id, enabled){
  const r = await fetch(BASE+'/api/admin/payment-methods/'+id,{method:'PATCH',headers:hdr(),body:JSON.stringify({enabled})});
  const m = pmData.find(x=>x.id===id);
  if(m) m.enabled = enabled;
  const badge = document.querySelector('#card_'+id+' .badge');
  if(badge){ badge.textContent=enabled?'Aktiv':'Inaktiv'; badge.className='badge '+(enabled?'on':'off'); }
}

async function saveConfig(id, type){
  const fields = CONFIG_FIELDS[type]||[];
  const config = {};
  fields.forEach(f=>{ const el=document.getElementById('f_'+id+'_'+f.key); if(el) config[f.key]=el.value; });
  const r = await fetch(BASE+'/api/admin/payment-methods/'+id,{method:'PATCH',headers:hdr(),body:JSON.stringify({config})});
  showMsg(id, r.ok, r.ok?'Gespeichert ✓':'Fehler beim Speichern');
  if(r.ok){ const m=pmData.find(x=>x.id===id); if(m) m.config=config; }
}

function showMsg(id, ok, text){
  const el = document.getElementById('msg_'+id);
  if(!el) return;
  el.textContent=text; el.className='msg '+(ok?'ok':'err'); el.style.display='block';
  setTimeout(()=>{ el.style.display='none'; }, 3000);
}

/* ────── CREDIT PACKAGES ────── */
let pkgData = [];

async function loadPackages(){
  const r = await fetch(BASE+'/api/admin/credit-packages',{headers:hdr()});
  const d = await r.json();
  pkgData = d.packages || [];
  renderPkg();
}

function renderPkg(){
  const el = document.getElementById('pkgList');
  if(!pkgData.length){ el.innerHTML='<div style="color:var(--muted);font-size:14px">Keine Pakete gefunden.</div>'; return; }
  el.innerHTML = pkgData.map(p=>pkgCard(p)).join('');
}

function pkgCard(p){
  return `<div class="card" id="pkg_${p.id}">
    <div class="card-header" onclick="toggleCard2('${p.id}')">
      <span class="card-title">${esc(p.name)}</span>
      <span style="color:var(--muted);font-size:13px;margin-right:8px">${p.credits} Credits · €${parseFloat(p.price_eur).toFixed(2)}</span>
      <span class="badge ${p.enabled?'on':'off'}">${p.enabled?'Aktiv':'Inaktiv'}</span>
      <span class="chevron">▼</span>
    </div>
    <div class="card-body">
      <div class="toggle-row">
        <span class="toggle-label">Paket aktivieren</span>
        <label class="toggle">
          <input type="checkbox" id="ptog_${p.id}" ${p.enabled?'checked':''} onchange="togglePkg('${p.id}',this.checked)"/>
          <span class="slider"></span>
        </label>
      </div>
      <div class="form-group"><label>Name</label><input type="text" id="pn_${p.id}" value="${esc(p.name)}"/></div>
      <div class="form-group"><label>Credits</label><input type="text" id="pc_${p.id}" value="${p.credits}"/></div>
      <div class="form-group"><label>Preis (EUR)</label><input type="text" id="pp_${p.id}" value="${parseFloat(p.price_eur).toFixed(2)}"/></div>
      <div class="form-group"><label>Beschreibung</label><input type="text" id="pd_${p.id}" value="${esc(p.description||'')}"/></div>
      <div class="btn-row">
        <button class="btn btn-primary" onclick="savePkg('${p.id}')">Speichern</button>
      </div>
      <div class="msg" id="pmsg_${p.id}"></div>
    </div>
  </div>`;
}

function toggleCard2(id){
  document.getElementById('pkg_'+id).classList.toggle('open');
}

async function togglePkg(id, enabled){
  await fetch(BASE+'/api/admin/credit-packages/'+id,{method:'PATCH',headers:hdr(),body:JSON.stringify({enabled})});
  const p=pkgData.find(x=>x.id===id); if(p) p.enabled=enabled;
  const badge=document.querySelector('#pkg_'+id+' .badge');
  if(badge){ badge.textContent=enabled?'Aktiv':'Inaktiv'; badge.className='badge '+(enabled?'on':'off'); }
}

async function savePkg(id){
  const body={
    name: document.getElementById('pn_'+id).value,
    credits: parseInt(document.getElementById('pc_'+id).value)||0,
    price_eur: parseFloat(document.getElementById('pp_'+id).value)||0,
    description: document.getElementById('pd_'+id).value,
  };
  const r = await fetch(BASE+'/api/admin/credit-packages/'+id,{method:'PATCH',headers:hdr(),body:JSON.stringify(body)});
  const ok = r.ok;
  showPkgMsg(id, ok, ok?'Gespeichert ✓':'Fehler');
}

function showPkgMsg(id, ok, text){
  const el=document.getElementById('pmsg_'+id);
  if(!el) return;
  el.textContent=text; el.className='msg '+(ok?'ok':'err'); el.style.display='block';
  setTimeout(()=>{ el.style.display='none'; },3000);
}

/* ────── USERS ────── */
let userPage = 1;

async function loadUsers(pg=1){
  userPage = pg;
  const search = encodeURIComponent(document.getElementById('userSearch').value);
  const el = document.getElementById('userList');
  el.innerHTML='<div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div>';
  try {
    const r = await fetch(BASE+'/api/admin/users?page='+pg+'&search='+search,{headers:hdr()});
    const d = await r.json();
    renderUsers(d);
  } catch(e){ el.innerHTML='<div style="color:var(--danger)">Fehler: '+e.message+'</div>'; }
}

function renderUsers(d){
  const el = document.getElementById('userList');
  if(!d.users || !d.users.length){
    el.innerHTML='<div style="color:var(--muted);font-size:14px">Keine User gefunden.</div>';
    return;
  }
  el.innerHTML = d.users.map(u=>userRow(u)).join('') +
    '<div style="margin-top:16px;display:flex;gap:8px;align-items:center">' +
    (d.page>1?'<button class="btn btn-ghost" onclick="loadUsers('+(d.page-1)+')">← Zurück</button>':'') +
    '<span style="color:var(--muted);font-size:13px">Seite '+d.page+' von '+Math.ceil(d.total/50)+'</span>' +
    (d.page*50<d.total?'<button class="btn btn-ghost" onclick="loadUsers('+(d.page+1)+')">Weiter →</button>':'') +
    '</div>';
}

function userRow(u){
  const status = u.isBanned?'banned':u.subscriptionStatus||'active';
  const statusCls = u.isBanned?'off':status==='active'?'on':'off';
  return `<div class="card" id="ur_${u.id}">
    <div class="card-header">
      <span class="card-title">${esc(u.email||'')}</span>
      <span style="color:var(--muted);font-size:13px">${esc(u.displayName||'')}</span>
      <span class="badge ${statusCls}">${status}</span>
    </div>
    <div class="card-body">
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Credits</label><div style="font-size:18px;font-weight:600">${u.credits||0}</div></div>
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Rolle</label><div>${esc(u.role||'user')}</div></div>
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Erstellt</label><div style="font-size:12px">${u.createdAt?(new Date(u.createdAt)).toLocaleDateString():''}</div></div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-ghost" onclick="toggleBan('${u.id}',${!u.isBanned})">${u.isBanned?'Entsperren':'Sperren'}</button>
        <button class="btn btn-ghost" onclick="adjustCredits('${u.id}')">Credits anpassen</button>
      </div>
    </div>
  </div>`;
}

async function toggleBan(uid, ban){
  if(!confirm('User wirklich '+ (ban?'sperren':'entsperren') +'?')) return;
  await fetch(BASE+'/api/admin/users/'+uid,{method:'PATCH',headers:hdr(),body:JSON.stringify({isBanned:ban})});
  loadUsers(userPage);
}

async function adjustCredits(uid){
  const amount = prompt('Credit-Änderung (positiv = hinzufügen, negativ = abziehen):','0');
  if(amount===null) return;
  const amountInt = parseInt(amount);
  if(isNaN(amountInt)||amountInt===0){ alert('Ungültiger Betrag.'); return; }
  const reason = prompt('Grund für die Anpassung:');
  if(!reason) return;
  const r = await fetch(BASE+'/api/admin/users/'+uid+'/credit-adjustment',{
    method:'POST',headers:hdr(),body:JSON.stringify({amount:amountInt,reason})
  });
  const d = await r.json();
  if(d.error) alert('Fehler: '+d.error);
  else { alert('Credits angepasst ✓'); loadUsers(userPage); }
}

/* ────── BILLING ────── */
let billingPage = 1;

async function loadBilling(pg=1){
  billingPage = pg;
  const uid = encodeURIComponent(document.getElementById('billingUserId').value||'');
  const ttype = encodeURIComponent(document.getElementById('billingType').value||'');
  const el = document.getElementById('billingList');
  el.innerHTML='<div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div>';
  try {
    let url = BASE+'/api/admin/transactions?page='+pg;
    if(uid) url += '&user_id='+uid;
    if(ttype) url += '&type='+ttype;
    const r = await fetch(url,{headers:hdr()});
    const d = await r.json();
    renderBilling(d);
  } catch(e){ el.innerHTML='<div style="color:var(--danger)">Fehler: '+e.message+'</div>'; }
}

function renderBilling(d){
  const el = document.getElementById('billingList');
  if(!d.transactions || !d.transactions.length){
    el.innerHTML='<div style="color:var(--muted);font-size:14px">Keine Transaktionen gefunden.</div>';
    return;
  }
  const html = d.transactions.map(t=>`<tr>
    <td style="padding:8px 12px;border-bottom:1px solid var(--border)">${t.createdAt?(new Date(t.createdAt)).toLocaleString():''}</td>
    <td style="padding:8px 12px;border-bottom:1px solid var(--border)"><code style="font-size:11px">${esc(t.userId||'').substring(0,8)}…</code></td>
    <td style="padding:8px 12px;border-bottom:1px solid var(--border)"><span class="badge ${t.type==='purchase'?'on':'off'}">${t.type}</span></td>
    <td style="padding:8px 12px;border-bottom:1px solid var(--border)">${t.amount||0}</td>
    <td style="padding:8px 12px;border-bottom:1px solid var(--border)"><span class="badge ${t.status==='completed'?'on':'off'}">${t.status}</span></td>
    <td style="padding:8px 12px;border-bottom:1px solid var(--border);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(t.description||'')}">${esc(t.description||'')}</td>
  </tr>`).join('');
  el.innerHTML = `<table style="width:100%;border-collapse:collapse"><thead><tr style="background:#21262d;text-align:left">
    <th style="padding:8px 12px;font-size:11px;color:var(--muted);text-transform:uppercase">Datum</th>
    <th style="padding:8px 12px;font-size:11px;color:var(--muted);text-transform:uppercase">User</th>
    <th style="padding:8px 12px;font-size:11px;color:var(--muted);text-transform:uppercase">Typ</th>
    <th style="padding:8px 12px;font-size:11px;color:var(--muted);text-transform:uppercase">Betrag</th>
    <th style="padding:8px 12px;font-size:11px;color:var(--muted);text-transform:uppercase">Status</th>
    <th style="padding:8px 12px;font-size:11px;color:var(--muted);text-transform:uppercase">Beschreibung</th>
  </tr></thead><tbody>${html}</tbody></table>` +
    '<div style="margin-top:16px;display:flex;gap:8px;align-items:center">' +
    (d.page>1?'<button class="btn btn-ghost" onclick="loadBilling('+(d.page-1)+')">← Zurück</button>':'') +
    '<span style="color:var(--muted);font-size:13px">Seite '+d.page+'</span>' +
    (d.page*50<d.total?'<button class="btn btn-ghost" onclick="loadBilling('+(d.page+1)+')">Weiter →</button>':'') +
    '</div>';
}

/* ────── LLM ROUTES ────── */
async function loadLLMRoutes(){
  const el = document.getElementById('llmList');
  el.innerHTML='<div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div>';
  try {
    const r = await fetch(BASE+'/api/admin/llm/routes',{headers:hdr()});
    const d = await r.json();
    renderLLMRoutes(d);
  } catch(e){ el.innerHTML='<div style="color:var(--danger)">Fehler: '+e.message+'</div>'; }
}

function renderLLMRoutes(d){
  const el = document.getElementById('llmList');
  if(!d.routes || !d.routes.length){
    el.innerHTML='<div style="color:var(--muted);font-size:14px">Keine LLM Routes konfiguriert.</div>';
    return;
  }
  el.innerHTML = d.routes.map(r=>`<div class="card" id="lr_${r.id}">
    <div class="card-header">
      <span class="card-title">${esc(r.provider||'')} / ${esc(r.modelName||r.modelId||'')}</span>
      <span class="badge ${r.disabled?'off':'on'}">${r.disabled?'Deaktiviert':'Aktiv'}</span>
    </div>
    <div class="card-body">
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Provider</label><div>${esc(r.provider||'')}</div></div>
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Credits/Unit</label><div>${r.creditsPerUnit||0}</div></div>
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Priorität</label><div>${r.priority||0}</div></div>
      </div>
      <div class="toggle-row">
        <span class="toggle-label">Route aktivieren</span>
        <label class="toggle">
          <input type="checkbox" id="ltog_${r.id}" ${r.disabled?'':'checked'} onchange="toggleLLM('${r.id}',!this.checked)"/>
          <span class="slider"></span>
        </label>
      </div>
      <div style="margin-top:12px">
        <button class="btn btn-ghost" onclick="healthcheckLLM('${r.id}')" id="hcbtn_${r.id}">🔍 Healthcheck</button>
        <span id="hcstatus_${r.id}" style="margin-left:12px;font-size:13px"></span>
      </div>
    </div>
  </div>`).join('');
}

async function toggleLLM(rid, disabled){
  await fetch(BASE+'/api/admin/llm/routes/'+rid,{method:'PATCH',headers:hdr(),body:JSON.stringify({disabled})});
  loadLLMRoutes();
}

async function healthcheckLLM(rid){
  const btn = document.getElementById('hcbtn_'+rid);
  const status = document.getElementById('hcstatus_'+rid);
  btn.disabled = true;
  btn.innerHTML = '⏳ Teste…';
  status.textContent = '';
  try {
    const r = await fetch(BASE+'/api/admin/llm/routes/'+rid+'/healthcheck',{method:'POST',headers:hdr()});
    const d = await r.json();
    if(d.health === 'healthy'){
      status.textContent = '✓ Gesund';
      status.style.color = 'var(--accent2)';
    } else if(d.health === 'degraded'){
      status.textContent = '⚠️ '+(d.blocker||'Beeinträchtigt');
      status.style.color = 'var(--warn)';
    } else {
      status.textContent = '? Unbekannt';
      status.style.color = 'var(--muted)';
    }
  } catch(e){
    status.textContent = '✗ Fehler: '+e.message;
    status.style.color = 'var(--danger)';
  }
  btn.disabled = false;
  btn.innerHTML = '🔍 Healthcheck';
}

/* ────── TOOLS ────── */
async function loadTools(){
  const el = document.getElementById('toolsList');
  el.innerHTML='<div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div>';
  try {
    const r = await fetch(BASE+'/api/admin/launcher/tools',{headers:hdr()});
    const d = await r.json();
    renderTools(d);
  } catch(e){ el.innerHTML='<div style="color:var(--danger)">Fehler: '+e.message+'</div>'; }
}

function renderTools(d){
  const el = document.getElementById('toolsList');
  if(!d.tools || !d.tools.length){
    el.innerHTML='<div style="color:var(--muted);font-size:14px">Keine Tools konfiguriert.</div>';
    return;
  }
  el.innerHTML = d.tools.map(t=>`<div class="card" id="tr_${t.id}">
    <div class="card-header">
      <span class="card-title">${esc(t.label||'')}</span>
      ${t.badge?'<span class="badge on">'+esc(t.badge)+'</span>':''}
      <span class="badge ${t.disabled?'off':'on'}">${t.disabled?'Deaktiviert':'Aktiv'}</span>
    </div>
    <div class="card-body">
      <div class="toggle-row">
        <span class="toggle-label">Tool aktivieren</span>
        <label class="toggle">
          <input type="checkbox" id="ttog_${t.id}" ${t.disabled?'':'checked'} onchange="toggleTool('${t.id}',!this.checked)"/>
          <span class="slider"></span>
        </label>
      </div>
      <div style="margin-top:12px">
        <button class="btn btn-ghost" onclick="healthcheckTool('${t.id}')" id="thcbtn_${t.id}">🔍 Healthcheck</button>
        <span id="thcstatus_${t.id}" style="margin-left:12px;font-size:13px"></span>
      </div>
    </div>
  </div>`).join('');
}

async function toggleTool(tid, disabled){
  await fetch(BASE+'/api/admin/launcher/tools/'+tid,{method:'PATCH',headers:hdr(),body:JSON.stringify({disabled})});
  loadTools();
}

async function healthcheckTool(tid){
  const btn = document.getElementById('thcbtn_'+tid);
  const status = document.getElementById('thcstatus_'+tid);
  btn.disabled = true;
  btn.innerHTML = '⏳ Teste…';
  status.textContent = '';
  try {
    const r = await fetch(BASE+'/api/admin/launcher/tools/'+tid+'/healthcheck',{method:'POST',headers:hdr()});
    const d = await r.json();
    if(d.health === 'healthy'){
      status.textContent = '✓ Gesund';
      status.style.color = 'var(--accent2)';
    } else if(d.health === 'degraded'){
      status.textContent = '⚠️ '+(d.blocker||'Beeinträchtigt');
      status.style.color = 'var(--warn)';
    } else {
      status.textContent = '? '+d.blocker||'Unbekannt';
      status.style.color = 'var(--muted)';
    }
  } catch(e){
    status.textContent = '✗ Fehler: '+e.message;
    status.style.color = 'var(--danger)';
  }
  btn.disabled = false;
  btn.innerHTML = '🔍 Healthcheck';
}

/* ────── RUNTIME ────── */
let runtimeConfig = {};

async function loadRuntime(){
  const el = document.getElementById('runtimeList');
  el.innerHTML='<div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div>';
  try {
    const [cfgR, hlthR] = await Promise.all([
      fetch(BASE+'/api/admin/runtime/config',{headers:hdr()}),
      fetch(BASE+'/api/admin/runtime/health',{headers:hdr()})
    ]);
    const cfg = await cfgR.json();
    const hlth = await hlthR.json();
    runtimeConfig = cfg.config || {};
    renderRuntime(cfg.config, hlth);
  } catch(e){ el.innerHTML='<div style="color:var(--danger)">Fehler: '+e.message+'</div>'; }
}

function renderRuntime(cfg, hlth){
  const el = document.getElementById('runtimeList');
  if(!cfg) return;
  const byokMode = cfg.byok_mode || 'user-key';
  const health = hlth?.health || 'unknown';
  const healthColor = health==='healthy'?'var(--accent2)':health==='degraded'?'var(--warn)':'var(--muted)';
  const healthIcon = health==='healthy'?'✓':health==='degraded'?'⚠':'?';
  el.innerHTML = `<div class="card">
    <div class="card-header"><span class="card-title">Worker Status</span><span class="badge ${health==='healthy'?'on':'off'}">${healthIcon} ${health}</span></div>
    <div class="card-body">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">BYOK Modus</label>
          <select id="rt_byok" style="margin-top:4px" onchange="updateRuntime('byok')">
            <option value="user-key" ${byokMode==='user-key'?'selected':''}>user-key</option>
            <option value="system-key" ${byokMode==='system-key'?'selected':''}>system-key</option>
            <option value="disabled" ${byokMode==='disabled'?'selected':''}>disabled</option>
          </select>
        </div>
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">CORS Origins</label><div style="font-size:14px;margin-top:4px">${cfg.cors_origins?.length||0} konfiguriert</div></div>
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Worker Health</label><div style="color:${healthColor}">${healthIcon} ${health}</div></div>
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Blocker</label><div style="font-size:12px">${hlth?.blockers?.length||0} aktiv</div></div>
      </div>
      <button class="btn btn-ghost" onclick="showCorsEditor()" style="margin-bottom:12px">✏️ CORS Origins bearbeiten</button>
      <div id="corsEditor" style="display:none">
        <div class="form-group">
          <label>Origins (eine pro Zeile)</label>
          <textarea id="corsTextarea" rows="6" placeholder="https://example.com">${(cfg.cors_origins||[]).join('\n')}</textarea>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" onclick="validateAndSaveCors()">Validieren & Speichern</button>
          <button class="btn btn-ghost" onclick="document.getElementById('corsEditor').style.display='none'">Abbrechen</button>
        </div>
        <div id="corsMsg" class="msg" style="margin-top:8px"></div>
      </div>
    </div>
  </div>`;
}

function showCorsEditor(){
  document.getElementById('corsEditor').style.display='block';
}

async function updateRuntime(field){
  let body = {};
  if(field === 'byok'){
    body.byok_mode = document.getElementById('rt_byok').value;
  }
  try {
    const r = await fetch(BASE+'/api/admin/runtime/config',{
      method:'PATCH',headers:hdr(),body:JSON.stringify(body)
    });
    const d = await r.json();
    if(!d.ok) alert('Fehler: '+(d.error||'Unbekannt'));
    else loadRuntime();
  } catch(e){ alert('Fehler: '+e.message); }
}

async function validateAndSaveCors(){
  const textarea = document.getElementById('corsTextarea');
  const msg = document.getElementById('corsMsg');
  const origins = textarea.value.split('\n').map(o=>o.trim()).filter(o=>o);
  
  // Validate first
  const vr = await fetch(BASE+'/api/admin/runtime/validate-cors',{
    method:'POST',headers:hdr(),body:JSON.stringify({origins})
  });
  const vd = await vr.json();
  
  if(!vd.valid && vd.errors?.length){
    const errMsgs = vd.errors.map(e=>e.error).join(', ');
    msg.textContent = '✗ Validierungsfehler: '+errMsgs;
    msg.className='msg err'; msg.style.display='block';
    return;
  }
  
  // Save
  const sr = await fetch(BASE+'/api/admin/runtime/config',{
    method:'PATCH',headers:hdr(),body:JSON.stringify({cors_origins:origins})
  });
  const sd = await sr.json();
  
  if(sd.ok){
    msg.textContent = '✓ Gespeichert!';
    msg.className='msg ok'; msg.style.display='block';
    setTimeout(()=>{ msg.style.display='none'; document.getElementById('corsEditor').style.display='none'; loadRuntime(); },1500);
  } else {
    msg.textContent = '✗ Fehler: '+(sd.error||'Unbekannt');
    msg.className='msg err'; msg.style.display='block';
  }
}

/* ────── AUDIT ────── */
async function loadAudit(){
  const el = document.getElementById('auditList');
  el.innerHTML='<div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div>';
  try {
    const r = await fetch(BASE+'/api/admin/audit-log',{headers:hdr()});
    const d = await r.json();
    renderAudit(d);
  } catch(e){ el.innerHTML='<div style="color:var(--danger)">Fehler: '+e.message+'</div>'; }
}

function renderAudit(d){
  const el = document.getElementById('auditList');
  if(!d.entries || !d.entries.length){
    el.innerHTML='<div style="color:var(--muted);font-size:14px">Keine Audit-Einträge gefunden.</div>';
    return;
  }
  const html = d.entries.map(e=>`<tr>
    <td style="padding:8px 12px;border-bottom:1px solid var(--border)">${e.createdAt?(new Date(e.createdAt)).toLocaleString():''}</td>
    <td style="padding:8px 12px;border-bottom:1px solid var(--border)">${esc(e.adminEmail||'system')}</td>
    <td style="padding:8px 12px;border-bottom:1px solid var(--border)"><code style="font-size:11px">${esc(e.action||'')}</code></td>
    <td style="padding:8px 12px;border-bottom:1px solid var(--border)"><code style="font-size:11px">${esc((e.targetId||'').substring(0,8))}…</code></td>
    <td style="padding:8px 12px;border-bottom:1px solid var(--border);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(JSON.stringify(e.changes||{}))}">${esc(JSON.stringify(e.changes||{}))}</td>
  </tr>`).join('');
  el.innerHTML = `<table style="width:100%;border-collapse:collapse"><thead><tr style="background:#21262d;text-align:left">
    <th style="padding:8px 12px;font-size:11px;color:var(--muted);text-transform:uppercase">Zeit</th>
    <th style="padding:8px 12px;font-size:11px;color:var(--muted);text-transform:uppercase">Admin</th>
    <th style="padding:8px 12px;font-size:11px;color:var(--muted);text-transform:uppercase">Aktion</th>
    <th style="padding:8px 12px;font-size:11px;color:var(--muted);text-transform:uppercase">Target</th>
    <th style="padding:8px 12px;font-size:11px;color:var(--muted);text-transform:uppercase">Änderungen</th>
  </tr></thead><tbody>${html}</tbody></table>` +
    '<div style="margin-top:16px;display:flex;gap:8px;align-items:center">' +
    (d.page>1?'<button class="btn btn-ghost" onclick="loadAuditPage('+(d.page-1)+')">← Zurück</button>':'') +
    '<span style="color:var(--muted);font-size:13px">Seite '+d.page+'</span>' +
    (d.page*50<d.total?'<button class="btn btn-ghost" onclick="loadAuditPage('+(d.page+1)+')">Weiter →</button>':'') +
    '</div>';
}

async function loadAuditPage(pg){
  const el = document.getElementById('auditList');
  el.innerHTML='<div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div>';
  try {
    const r = await fetch(BASE+'/api/admin/audit-log?page='+pg,{headers:hdr()});
    const d = await r.json();
    renderAudit(d);
  } catch(e){ el.innerHTML='<div style="color:var(--danger)">Fehler: '+e.message+'</div>'; }
}

function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
</script>
</body>
</html>"""


@app.route("/admin")
@app.route("/admin/")
def admin_panel():
    resp = make_response(_ADMIN_PANEL_HTML)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    return resp



# ── Universal Toolchain Proxy ─────────────────────────────────────────────────
# Proxies requests to the sovereign-universal-toolchain FastAPI/FastMCP server
# running at TOOLCHAIN_BASE_URL (default: http://127.0.0.1:8001).
# The TOOLCHAIN_API_KEY is injected server-side — never exposed to frontend.
# ─────────────────────────────────────────────────────────────────────────────

import json as _json

_UTOOLCHAIN_BASE = os.getenv("TOOLCHAIN_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
_UTOOLCHAIN_KEY  = os.getenv("TOOLCHAIN_API_KEY", "")


def _utc_request(method: str, path: str, body=None):
    """HTTP helper for proxying to the universal toolchain server."""
    import urllib.request as _ur
    import urllib.error   as _ue
    url = f"{_UTOOLCHAIN_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if _UTOOLCHAIN_KEY:
        headers["X-Toolchain-Key"] = _UTOOLCHAIN_KEY
    data = _json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = _ur.Request(url, data=data, headers=headers, method=method)
    try:
        with _ur.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return _json.loads(raw) if raw else {}
    except _ue.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Toolchain {e.code}: {raw[:500]}") from e


@app.route("/api/toolchain/universal/status")
def utc_status():
    """Health check for the universal toolchain server (public)."""
    try:
        data = _utc_request("GET", "/")
        return jsonify({**data, "proxy_via": _UTOOLCHAIN_BASE})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "proxy_via": _UTOOLCHAIN_BASE}), 502


@app.route("/api/toolchain/universal/manifest")
def utc_manifest():
    """Return the tool manifest from the universal toolchain (public)."""
    try:
        data = _utc_request("GET", "/api/v1/manifest")
        return jsonify(data)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


@app.route("/api/toolchain/universal/briefing")
def utc_briefing():
    """Return the toolchain briefing for LLM agents (public)."""
    try:
        data = _utc_request("GET", "/api/v1/briefing")
        return jsonify(data)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


@app.route("/api/toolchain/universal/invoke", methods=["POST"])
@require_session
def utc_invoke():
    """
    Proxy a tool call to the universal toolchain server.
    Body: { "tool": "<tool_name>", "args": { ... } }
    Write tools (write_action=true) require confirm=true in args.
    """
    try:
        b        = request.get_json(force=True) or {}
        tool     = (b.get("tool") or "").strip()
        args     = b.get("args") or {}
        if not tool:
            return jsonify({"error": "tool name erforderlich"}), 400

        data = _utc_request("POST", f"/api/v1/tools/{tool}", {"args": args})

        # Audit write actions
        if data.get("ok") and data.get("result", {}) if isinstance(data.get("result"), dict) else False:
            write_action = isinstance(data.get("result"), dict) and data["result"].get("created")
            if write_action:
                _tc_audit(
                    request.session_user_id,
                    f"utc_write_{tool}",
                    {"tool": tool, "args_keys": list(args.keys())},
                )

        return jsonify(data)
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════
# NOTE: This must be at the END of the file!
# Routes defined after this block will NOT be registered when running directly.
# For production, use gunicorn: gunicorn -w 4 -b 0.0.0.0:8787 app:app
if __name__ == "__main__":
    # Validate required tables exist before starting
    try:
        query("SELECT 1", one=True)
    except Exception as e:
        print(f"[WARN] Database connection failed: {e}")
        print("[WARN] Starting anyway - routes may fail if DB is required.")
    
    app.run(host="0.0.0.0", port=8787, debug=False)

