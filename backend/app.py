#!/usr/bin/env python3
"""
Sovereign Backend — Flask app.
Serves the internal Sovereign Agent API and Admin API routes.

Issue #460: Admin API (psycopg2, real DB)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
import urllib.parse
import uuid
from functools import wraps

# Import OAuth Security Module
from security_oauth import (
    _check_rate_limit,
    _audit_event,
    init_token_encryption,
    _encrypt_token,
    _decrypt_token,
    _validate_pkce,
    _generate_state,
    _generate_pkce,
)

import psycopg2
import psycopg2.extras
import psycopg2.pool
from flask import Flask, jsonify, request, make_response, g
from flask_cors import CORS
import requests

from agent_runtime.routes import register_sovereign_agent_routes
from agent_runtime.cognitive_swarm_routes import register_cognitive_swarm_routes
from agent_runtime.contracts import sanitize_agent_text, normalize_agent_path, is_safe_branch
from are_inference import register_are_inference_routes
from knowledge_library import register_admin_knowledge_routes, register_knowledge_routes
from security_runtime import consume_step_up_approval, register_security_routes

# GitHub App integration (Marketplace)
try:
    from github_app import register_github_app_routes
    HAS_GITHUB_APP = True
except ImportError:
    HAS_GITHUB_APP = False
    register_github_app_routes = None

# ── Worker AI Helper ───────────────────────────────────────────────────────────

WORKER_AI_BASE = os.getenv("WORKER_AI_PROXY_URL", "https://sovereign-llm-proxy.projectouroboroscollective.workers.dev")
WORKER_AI_TIMEOUT = 15  # seconds

def _worker_headers() -> dict:
    """Standard headers for Worker AI API calls."""
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("WORKER_AI_PROXY_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers

def fetch_worker_ai(path: str, method: str = "GET", json_data: dict = None) -> tuple[requests.Response | None, str]:
    """
    Centralized Worker AI fetch with consistent base URL, headers, timeout, and error handling.
    Returns (response, error_message). If error_message is empty, response is valid.
    """
    url = f"{WORKER_AI_BASE.rstrip('/')}/{path.lstrip('/')}"
    try:
        if method == "GET":
            resp = requests.get(url, headers=_worker_headers(), timeout=WORKER_AI_TIMEOUT)
        elif method == "POST":
            resp = requests.post(url, headers=_worker_headers(), json=json_data, timeout=WORKER_AI_TIMEOUT)
        else:
            return None, f"Unsupported method: {method}"
        
        return resp, ""  # Success (caller checks resp.ok)
    except requests.exceptions.Timeout:
        return None, f"Request to Worker AI timed out after {WORKER_AI_TIMEOUT}s"
    except requests.exceptions.ConnectionError as e:
        return None, f"Cannot connect to Worker AI: {e}"
    except Exception as e:
        return None, f"Worker AI request failed: {e}"

app = Flask(__name__)

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
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
            if one:
                result = cur.fetchone()
            elif cur.description is not None:
                result = cur.fetchall()
            else:
                result = None
            if write:
                conn.commit()
            return result
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


_OAUTH_STATE_TTL_SECONDS = 600


def _oauth_state_hash(state: str) -> str:
    normalized = str(state or "").strip()
    if not normalized:
        raise ValueError("OAuth State fehlt")
    return hashlib.sha256(normalized.encode()).hexdigest()


def _oauth_state_payload(row) -> dict | None:
    if not row:
        return None
    payload = row.get("payload")
    return dict(payload) if isinstance(payload, dict) else None


def _store_oauth_state(state: str, data: dict) -> None:
    """Persist OAuth state for all Gunicorn workers without storing the raw state."""
    state_hash = _oauth_state_hash(state)
    payload = dict(data or {})
    query("DELETE FROM github_oauth_states WHERE expires_at <= NOW()", write=True)
    query(
        """INSERT INTO github_oauth_states (state_hash, payload, expires_at)
           VALUES (%s, %s::jsonb, NOW() + (%s * INTERVAL '1 second'))
           ON CONFLICT (state_hash) DO UPDATE SET
               payload = EXCLUDED.payload,
               expires_at = EXCLUDED.expires_at,
               created_at = NOW()""",
        (state_hash, psycopg2.extras.Json(payload), _OAUTH_STATE_TTL_SECONDS),
        write=True,
    )


def _peek_oauth_state(state: str) -> dict | None:
    """Read callback routing context without consuming the one-time state."""
    row = query(
        """SELECT payload
           FROM github_oauth_states
           WHERE state_hash = %s AND expires_at > NOW()
           LIMIT 1""",
        (_oauth_state_hash(state),),
        one=True,
    )
    return _oauth_state_payload(row)


def _get_oauth_state(state: str) -> dict | None:
    """Atomically consume one unexpired OAuth state across all backend workers."""
    row = query(
        """DELETE FROM github_oauth_states
           WHERE state_hash = %s AND expires_at > NOW()
           RETURNING payload""",
        (_oauth_state_hash(state),),
        one=True,
        write=True,
    )
    return _oauth_state_payload(row)


class PooledAgentConnection:
    """DB-API compatible connection wrapper for agent_runtime job store.

    The neutral agent runtime owns SQL for sovereign_agent_jobs. This wrapper
    provides a real pooled connection and returns it to the Flask pool on close.
    """

    def __init__(self):
        self._pool = get_pool()
        self._conn = self._pool.getconn()
        self._closed = False

    def cursor(self):
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if not self._closed:
            self._pool.putconn(self._conn)
            self._closed = True


def get_agent_runtime_connection() -> PooledAgentConnection:
    return PooledAgentConnection()


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
                "error": sanitize_agent_text("API-Key keinem Admin zugeordnet"),
                "hint": "Admin-Key in admin_api_keys hinterlegen oder ADMIN_BOOTSTRAP_ADMIN_EMAIL eindeutig setzen",
            }), 401

        g.current_admin = admin
        return f(*args, **kwargs)
    return decorated


def get_current_admin() -> dict | None:
    """Get the currently authenticated admin from request-local Flask context."""
    return getattr(g, "current_admin", None)


def get_current_admin_user_id() -> str:
    admin = get_current_admin() or {}
    return str(admin.get("id") or "")


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
    admin = get_current_admin() or {}
    admin_id = str(admin.get("id") or "")
    if not admin_id:
        return jsonify({"error": "Authentifizierter Admin hat keine persistente ID"}), 500
    row = query(
        "SELECT * FROM admin_users WHERE id = %s::uuid LIMIT 1",
        (admin_id,), one=True,
    )
    if not row:
        return jsonify({"error": "Authentifizierter Admin wurde nicht gefunden"}), 404
    return jsonify({
        "ok": True,
        "authMode": admin.get("authMode") or "unknown",
        **_user_row_to_dict(row),
    })


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
    """Apply one verified admin delta to ledger, cache and audit atomically."""
    body = request.get_json(force=True) or {}
    try:
        amount = int(body.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount muss eine ganze Zahl sein"}), 400
    reason = str(body.get("reason") or "").strip()
    if amount == 0:
        return jsonify({"error": "amount darf nicht 0 sein"}), 400
    if not reason:
        return jsonify({"error": "reason fehlt"}), 400

    admin = get_current_admin() or {}
    ledger_type = "bonus" if amount > 0 else "correction"
    sign = "+" if amount > 0 else ""
    ledger_reason = f"Admin {sign}{amount}: {reason}"
    audit_changes = {
        "amount": amount,
        "reason": reason,
        "ledgerType": ledger_type,
    }
    try:
        result = _apply_credit_delta(
            uid,
            amount,
            ledger_type=ledger_type,
            reason=ledger_reason,
            created_by=str(admin.get("id") or ""),
            audit_action="admin_credit_adjustment",
            audit_admin_email=str(admin.get("email") or ""),
            audit_changes=audit_changes,
        )
    except LookupError:
        return jsonify({"error": "User nicht gefunden"}), 404
    except CreditStateConflict as exc:
        return jsonify({
            "error": str(exc),
            "blocker": "credit_state_verification_failed",
        }), 409
    except InsufficientCredits as exc:
        return jsonify({
            "error": str(exc),
            "available": exc.available,
            "required": exc.required,
        }), 402
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "ok": True,
        "newBalance": result["newBalance"],
        "ledgerEntry": {
            "type": ledger_type,
            "amount": amount,
            "reason": ledger_reason,
        },
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


# ── Toolchain Tools ───────────────────────────────────────────────────────────

@app.route("/api/admin/toolchain/tools")
@require_admin
def admin_toolchain_tools():
    """List all toolchain tools from database."""
    rows = query(
        """SELECT id::text, name, description, input_schema,
                  enabled, write_action, requires_confirm,
                  sort_order
           FROM toolchain_tools
           ORDER BY sort_order ASC"""
    )
    return jsonify({
        "tools": [{
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "inputSchema": r["input_schema"],
            "enabled": r["enabled"],
            "writeAction": r["write_action"],
            "requiresConfirm": r["requires_confirm"],
            "sortOrder": r["sort_order"]
        } for r in rows]
    })


@app.route("/api/admin/toolchain/tools", methods=["POST"])
@require_admin
def admin_create_toolchain_tool():
    """Create a new toolchain tool."""
    body = request.get_json(force=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name ist erforderlich"}), 400

    # Check if already exists
    existing = query(
        "SELECT id FROM toolchain_tools WHERE name = %s",
        (name,), one=True
    )
    if existing:
        return jsonify({"error": f"Tool '{name}' existiert bereits"}), 409

    description = body.get("description", "")
    input_schema = body.get("inputSchema") or {}
    enabled = body.get("enabled", True)
    write_action = body.get("writeAction", False)
    requires_confirm = body.get("requiresConfirm", False)
    sort_order = body.get("sortOrder", 0)

    # Use write=True and get the returning id
    cur_row = query(
        """INSERT INTO toolchain_tools
              (name, description, input_schema, enabled, write_action, requires_confirm, sort_order)
           VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)
           RETURNING id::text""",
        (name, description, _json.dumps(input_schema), enabled, write_action, requires_confirm, sort_order),
        one=True, write=True
    )
    if cur_row is None:
        raise RuntimeError("Failed to insert tool")
    tool_id = cur_row["id"]
    audit("admin_create_toolchain_tool", tool_id, body)
    return jsonify({"ok": True, "id": tool_id}), 201


@app.route("/api/admin/toolchain/tools/<tid>", methods=["PATCH"])
@require_admin
def admin_update_toolchain_tool(tid):
    """Update a toolchain tool."""
    body = request.get_json(force=True) or {}
    col_map = {
        "name": "name",
        "description": "description",
        "inputSchema": "input_schema",
        "enabled": "enabled",
        "writeAction": "write_action",
        "requiresConfirm": "requires_confirm",
        "sortOrder": "sort_order",
    }
    sets, vals = [], []
    for k, v in body.items():
        if k in col_map:
            sets.append(f"{col_map[k]} = %s")
            if k == "inputSchema":
                vals.append(_json.dumps(v))
            else:
                vals.append(v)
    if not sets:
        return jsonify({"error": "Keine Felder"}), 400
    sets.append("updated_at = NOW()")
    vals.append(tid)
    query(
        f"UPDATE toolchain_tools SET {', '.join(sets)} WHERE id = %s::uuid",
        vals, write=True,
    )
    audit("admin_update_toolchain_tool", tid, body)
    return jsonify({"ok": True})


@app.route("/api/admin/toolchain/tools/<tid>", methods=["DELETE"])
@require_admin
def admin_delete_toolchain_tool(tid):
    """Delete a toolchain tool."""
    row = query(
        "DELETE FROM toolchain_tools WHERE id = %s::uuid RETURNING id",
        (tid,), one=True, write=True
    )
    if not row:
        return jsonify({"error": "Tool nicht gefunden"}), 404
    audit("admin_delete_toolchain_tool", tid, {"deleted": True})
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
        f"UPDATE llm_routes SET {', '.join(sets)} WHERE id = %s",
        vals, write=True,
    )
    audit("admin_update_llm_route", rid, body)
    return jsonify({"ok": True})


@app.route("/api/admin/llm/worker-ai/status", methods=["GET"])
@require_admin
def admin_worker_ai_status():
    """Get Worker AI health status and available models from Cloudflare."""
    start = time.time()
    
    # Test health endpoint
    resp, _err = fetch_worker_ai("health")
    response_time_ms = int((time.time() - start) * 1000)
    
    if _err:
        return jsonify({
            "status": "error",
            "error": _err,
            "configured": False,
            "availableModels": [],
            "modelCount": 0,
            "responseTimeMs": response_time_ms,
        }), 500
    
    health_data = resp.json() if resp.ok else {}

    # Get available models
    models_resp, _err = fetch_worker_ai("v1/models")
    
    available_models = []
    if models_resp and models_resp.ok:
        models_data = models_resp.json()
        available_models = models_data.get("data", [])

    return jsonify({
        "status": health_data.get("status", "unknown"),
        "configured": health_data.get("configured", False),
        "provider": "cloudflare",
        "workerUrl": WORKER_AI_BASE,
        "availableModels": available_models,
        "modelCount": len(available_models),
        "providers": health_data.get("providers", {}),
        "timestamp": health_data.get("timestamp"),
        "responseTimeMs": response_time_ms,
    })


@app.route("/api/admin/system/health", methods=["GET"])
@require_admin
def admin_system_health():
    """Comprehensive system health check for all components."""
    health = {
        "ok": True,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "components": {},
    }
    
    # 1. Database check
    try:
        start = time.time()
        result = query("SELECT 1 as test, NOW() as now", one=True)
        db_time = int((time.time() - start) * 1000)
        health["components"]["database"] = {
            "status": "healthy",
            "responseTimeMs": db_time,
        }
    except Exception as e:
        health["ok"] = False
        health["components"]["database"] = {
            "status": "unhealthy",
            "error": sanitize_agent_text(str(e))[:100],
        }
    
    # 2. Worker AI check
    try:
        worker_url = WORKER_AI_BASE
        start = time.time()
        resp, _err = fetch_worker_ai("health")
        if _err:
            return jsonify({"status": "error", "error": _err, "configured": False, "availableModels": [], "modelCount": 0}), 500
        start = time.time()
        wai_time = int((time.time() - start) * 1000)
        if resp.ok:
            data = resp.json()
            health["components"]["worker_ai"] = {
                "status": data.get("status", "healthy"),
                "configured": data.get("configured", False),
                "modelCount": data.get("modelCount", 0),
                "responseTimeMs": wai_time,
            }
        else:
            health["ok"] = False
            health["components"]["worker_ai"] = {
                "status": "degraded",
                "error": f"HTTP {resp.status_code}",
                "responseTimeMs": wai_time,
            }
    except Exception as e:
        health["ok"] = False
        health["components"]["worker_ai"] = {
            "status": "unhealthy",
            "error": sanitize_agent_text(str(e))[:100],
        }
    
    # 3. LLM Routes check
    try:
        routes = query("SELECT COUNT(*) as count FROM llm_routes WHERE disabled = false", one=True)
        total = query("SELECT COUNT(*) as count FROM llm_routes", one=True)
        active_routes = int(routes["count"] if routes else 0)
        total_routes = int(total["count"] if total else 0)
        routes_healthy = active_routes > 0
        if not routes_healthy:
            health["ok"] = False
        health["components"]["llm_routes"] = {
            "status": "healthy" if routes_healthy else "degraded",
            "activeRoutes": active_routes,
            "totalRoutes": total_routes,
            "blocker": None if routes_healthy else "llm_routes_empty",
        }
    except Exception as e:
        health["components"]["llm_routes"] = {
            "status": "degraded",
            "error": sanitize_agent_text(str(e))[:100],
        }
    
    # 4. Config file check
    config_file = _CONFIG_FILE
    if config_file:
        health["components"]["config"] = {
            "status": "healthy" if os.path.exists(config_file) else "missing",
            "path": config_file,
        }
    
    return jsonify(health)


@app.route("/api/admin/llm/worker-ai/sync", methods=["POST"])
@require_admin
def admin_worker_ai_sync():
    """Auto-discover and sync LLM routes from Worker AI.
    
    Creates/updates/deletes llm_routes entries based on available models
    in the Cloudflare Worker AI proxy.
    """
    try:
        worker_url = WORKER_AI_BASE
        
        # Get available models from Worker
        resp, _err = fetch_worker_ai("v1/models")
        if _err:
            return jsonify({"error": f"Worker AI sync failed: {_err}"}), 500
        if not resp.ok:
            return jsonify({"error": f"Worker AI nicht erreichbar: HTTP {resp.status_code}"}), 502
        
        worker_models = resp.json().get("data", [])
        
        # Map Worker models to our route format
        # Cloudflare Worker AI format: @cf/meta/llama-3.1-8b-instruct
        # We store as: llama-3.1-8b (user-friendly name)
        
        created = []
        updated = []
        deleted = []
        
        for wm in worker_models:
            model_id = wm.get("id", "")
            if not model_id:
                continue
            
            # Convert @cf/xxx/yyy to friendly name: xxx-yyy
            friendly_name = model_id
            if model_id.startswith("@cf/"):
                parts = model_id.replace("@cf/", "").split("/")
                if len(parts) >= 2:
                    friendly_name = f"{parts[0]}-{parts[1]}"
            
            # Check if route exists
            existing = query(
                """SELECT id::text, model_id FROM llm_routes WHERE model_id = %s LIMIT 1""",
                (model_id,), one=True,
            )
            
            if existing:
                # Update if needed (provider is already set)
                updated.append({"id": existing["id"], "model": model_id})
            else:
                # Create new route
                # Default credits: 0.001 (1 credit per 1000 tokens)
                # Priority: based on model size (smaller = higher priority)
                priority = 50
                if "32b" in model_id.lower() or "70b" in model_id.lower():
                    priority = 100
                elif "7b" in model_id.lower():
                    priority = 25
                
                try:
                    new_id = query(
                        """INSERT INTO llm_routes 
                           (id, model_id, model_name, provider, base_url, credits_per_unit, priority, disabled)
                           VALUES (gen_random_uuid(), %s, %s, 'cloudflare', %s, 0.001, %s, false)
                           RETURNING id::text""",
                        (model_id, friendly_name, worker_url, priority),
                        write=True, one=True,
                    )
                    created.append({"id": new_id["id"], "model": model_id, "name": friendly_name})
                except Exception as insert_err:
                    # If insert fails (e.g., duplicate), just update
                    query(
                        """UPDATE llm_routes SET model_name = %s, base_url = %s, priority = %s, updated_at = NOW()
                           WHERE model_id = %s""",
                        (friendly_name, worker_url, priority, model_id),
                        write=True,
                    )
                    existing = query("SELECT id::text FROM llm_routes WHERE model_id = %s", (model_id,), one=True)
                    if existing:
                        updated.append({"id": existing["id"], "model": model_id})
        
        # Sync: Disable routes that no longer exist in Worker AI
        all_worker_ids = [wm.get("id", "") for wm in worker_models if wm.get("id")]
        if all_worker_ids and len(all_worker_ids) > 0:
            # Use list instead of tuple for IN clause to avoid type issues
            disabled_routes = query(
                """UPDATE llm_routes SET disabled = true, updated_at = NOW()
                   WHERE provider = 'cloudflare' 
                     AND model_id != ALL(%s)
                     AND disabled = false
                   RETURNING id::text, model_id""",
                (all_worker_ids,), write=True,
            )
            deleted = [{"id": r["id"], "model": r["model_id"]} for r in disabled_routes] if disabled_routes else []
        
        audit("admin_worker_ai_sync", None, {
            "created": len(created),
            "updated": len(updated),
            "disabled": len(deleted),
            "workerModels": len(worker_models),
        })
        
        return jsonify({
            "ok": True,
            "synced": {
                "created": created,
                "updated": updated,
                "disabled": deleted,
            },
            "totalWorkerModels": len(worker_models),
            "totalRoutes": len(created) + len(updated),
        })
        
    except Exception as e:
        return jsonify({"error": sanitize_agent_text(str(e))}), 500


@app.route("/api/admin/llm/worker-ai/models", methods=["GET"])
@require_admin
def admin_worker_ai_models():
    """List models available in Worker AI with health status."""
    try:
        worker_url = WORKER_AI_BASE
        
        resp, _err = fetch_worker_ai("v1/models")
        if _err:
            return jsonify({"error": f"Worker AI sync failed: {_err}"}), 500
        if not resp.ok:
            return jsonify({"error": f"Worker AI Fehler: HTTP {resp.status_code}"}), 502
        
        worker_models = resp.json().get("data", [])
        
        # Get our configured routes
        our_routes = query(
            """SELECT model_id, model_name, disabled, priority, credits_per_unit
               FROM llm_routes WHERE provider = 'cloudflare'"""
        )
        route_map = {r["model_id"]: r for r in our_routes}
        
        # Merge info
        result = []
        for wm in worker_models:
            model_id = wm.get("id", "")
            our_route = route_map.get(model_id, {})
            
            # Friendly name
            friendly_name = model_id
            if model_id.startswith("@cf/"):
                parts = model_id.replace("@cf/", "").split("/")
                if len(parts) >= 2:
                    friendly_name = f"{parts[0]}-{parts[1]}"
            
            result.append({
                "modelId": model_id,
                "friendlyName": friendly_name,
                "ownedBy": wm.get("owned_by", "cloudflare"),
                "inDatabase": model_id in route_map,
                "enabled": our_route.get("disabled", True) == False if our_route else False,
                "priority": our_route.get("priority", 50),
                "creditsPerUnit": our_route.get("credits_per_unit", 0.001),
            })
        
        return jsonify({"models": result, "total": len(result)})
        
    except Exception as e:
        return jsonify({"error": sanitize_agent_text(str(e))}), 500


def require_session(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        uid = _get_session_user_id()
        if not uid:
            return jsonify({"error": "Nicht eingeloggt"}), 401
        request.session_user_id = uid
        return f(*args, **kwargs)
    return decorated


register_sovereign_agent_routes(
    app,
    require_session=require_session,
    get_connection=get_agent_runtime_connection,
)
register_cognitive_swarm_routes(
    app,
    require_session=require_session,
    get_connection=get_agent_runtime_connection,
)

# ── User OpenHands Jobs (Tool Section) ───────────────────────────────────────















# ── Admin: List all user OpenHands jobs ──────────────────────────────────────



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
    "byok_mode": "system-key",  # provider credentials remain behind the backend proxy
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
    """Mask sensitive values in config for display using defensive pattern recognition."""
    masked = {}
    for key, value in config.items():
        if isinstance(value, str):
            # Apply both label-based and pattern-based redaction
            if any(k in key.lower() for k in ("secret", "key", "token", "password", "auth")):
                masked[key] = sanitize_agent_text(f"{key}: {value}").split(": ", 1)[-1]
            else:
                masked[key] = sanitize_agent_text(value)
        elif isinstance(value, dict):
            masked[key] = _mask_secrets(value)
        else:
            masked[key] = value
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
    
    candidate_config = dict(_RUNTIME_CONFIG)
    candidate_config.update(updates)

    # Persistence is the commit point. Do not mutate the live runtime first.
    if not _save_runtime_config(candidate_config):
        return jsonify({
            "error": "Konfiguration konnte nicht persistent gespeichert werden",
            "ok": False,
            "config": _mask_secrets(_RUNTIME_CONFIG),
            "persisted": os.path.exists(_CONFIG_FILE),
        }), 500
    _RUNTIME_CONFIG = candidate_config
    
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
        health_status = "degraded"
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
        "ok": health_status == "healthy",
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
    # Get route details (id is text, not uuid)
    route = query(
        """SELECT id::text, model_id AS "modelId", model_name AS "modelName",
                  provider, base_url AS "baseUrl", api_key AS "apiKey"
           FROM llm_routes WHERE id = %s""",
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
        elif provider == "mistral":
            if not base_url:
                base_url = "https://api.mistral.ai"
            # Mistral health check via models endpoint
            url = f"{base_url.rstrip('/')}/v1/models"
            if route.get("apiKey"):
                headers["Authorization"] = f"Bearer {route['apiKey']}"
            timeout = 10
        elif provider == "cloudflare":
            # Cloudflare Worker AI health check
            worker_url = WORKER_AI_BASE
            url = f"{worker_url}/health"
            timeout = 15
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
            
            # Validate response is JSON (API returned valid data)
            content_type = resp.headers.get("content-type", "")
            if "application/json" not in content_type and resp.status_code >= 400:
                health_status = "degraded"
                blocker = "invalid_response"
                error_message = f"API Fehler: HTTP {resp.status_code} (erwartet JSON)"
    
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
                if resp.ok:
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
            # Tools without a configured URL remain unknown
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
                    
                    if resp.ok:
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
                    
                    if resp.ok:
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
        "ok": health_status == "healthy",
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
                    elif status == "failed":
                        level = "error"
                runtime_events.append({
                    "at": int(time.time()), "level": level,
                    "stage": "openhands", "message": msg or f"Event: {kind}",
                })
            if job["status"] == "running":
                for e in events:
                    if e.get("kind") == "ConversationStatusEvent" and \
                            e.get("status") in ("stopped", "finished", "failed"):
                        terminal_status = e.get("status")
                        job["status"] = "failed" if terminal_status == "failed" else "completed"
                        runtime_events.append({
                            "at": int(time.time()),
                            "level": "error" if terminal_status == "failed" else "success",
                            "stage": "openhands",
                            "message": "OpenHands failed" if terminal_status == "failed" else "OpenHands completed",
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


def _credit_purchase_context(pkg: dict) -> dict:
    return {
        "packageId": str(pkg.get("id") or ""),
        "priceEur": float(pkg.get("price_eur") or 0),
        "credits": int(pkg.get("credits") or 0),
    }


def _authorize_credit_purchase(pkg: dict):
    user_id = _get_session_user_id()
    if not user_id:
        return None, (jsonify({"error": "Authentication required"}), 401)
    result = consume_step_up_approval(
        get_agent_runtime_connection,
        user_id=user_id,
        action="credit_purchase",
        context=_credit_purchase_context(pkg),
        token=request.headers.get("X-Step-Up-Token", "").strip() or None,
    )
    if not result.get("approved"):
        return user_id, (jsonify({
            "error": "step_up_required",
            "action": "credit_purchase",
            "context": result.get("context"),
            "reason": result.get("reason"),
        }), 428)
    return user_id, None


def _read_verified_credit_balance(user_id: str) -> int:
    """Return credits only when cache and append-only ledger agree."""
    if not user_id:
        raise LookupError("User für Credit-Verifikation fehlt")
    row = query(
        """SELECT account.credits::integer AS cached_balance,
                  COALESCE(SUM(ledger.amount), 0)::integer AS ledger_balance
           FROM admin_users AS account
           LEFT JOIN credit_ledger AS ledger ON ledger.user_id = account.id
           WHERE account.id = %s::uuid
           GROUP BY account.id, account.credits
           LIMIT 1""",
        (user_id,), one=True,
    )
    if not row:
        raise LookupError("User für Credit-Verifikation nicht gefunden")
    cached_balance = int(row["cached_balance"])
    ledger_balance = int(row["ledger_balance"])
    if cached_balance != ledger_balance:
        raise CreditStateConflict(
            f"Credit-State widersprüchlich: cache={cached_balance}, ledger={ledger_balance}",
        )
    return cached_balance


class CreditStateConflict(RuntimeError):
    """Persisted credit cache and append-only ledger disagree."""


class InsufficientCredits(ValueError):
    def __init__(self, required: int, available: int):
        self.required = required
        self.available = available
        super().__init__(f"Nicht genügend Credits: benötigt={required}, verfügbar={available}")


def _apply_credit_delta(
    user_id: str,
    amount: int,
    *,
    ledger_type: str,
    reason: str,
    provider: str | None = None,
    provider_tx_id: str | None = None,
    created_by: str | None = None,
    transaction_amount_eur: float | None = None,
    audit_action: str | None = None,
    audit_admin_email: str | None = None,
    audit_changes: dict | None = None,
) -> dict:
    """Atomically verify, mutate and evidence one user-credit transition."""
    if not user_id or not isinstance(amount, int) or amount == 0:
        raise ValueError("Credit-Änderung benötigt User und einen ganzzahligen Betrag ungleich null")
    normalized_provider = (provider or "").strip() or None
    normalized_tx_id = (provider_tx_id or "").strip() or None
    if transaction_amount_eur is not None and (not normalized_provider or not normalized_tx_id):
        raise ValueError("Bestätigte Käufe benötigen Provider und eindeutige Transaktions-ID")

    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id::text, email, credits FROM admin_users "
                "WHERE id = %s::uuid LIMIT 1 FOR UPDATE",
                (user_id,),
            )
            user_row = cur.fetchone()
            if not user_row:
                raise LookupError("User für Credit-Änderung nicht gefunden")

            cur.execute(
                "SELECT COALESCE(SUM(amount), 0)::integer AS balance "
                "FROM credit_ledger WHERE user_id = %s::uuid",
                (user_id,),
            )
            ledger_balance = int(cur.fetchone()["balance"])
            cached_balance = int(user_row["credits"])
            if ledger_balance != cached_balance:
                raise CreditStateConflict(
                    f"Credit-State widersprüchlich: cache={cached_balance}, ledger={ledger_balance}",
                )

            if normalized_provider and normalized_tx_id:
                cur.execute(
                    "SELECT user_id::text, credits FROM credit_receipts "
                    "WHERE provider = %s AND provider_tx_id = %s LIMIT 1",
                    (normalized_provider, normalized_tx_id),
                )
                existing_receipt = cur.fetchone()
                if existing_receipt:
                    if (
                        existing_receipt["user_id"] != user_id
                        or int(existing_receipt["credits"]) != amount
                    ):
                        raise CreditStateConflict("Provider-Receipt kollidiert mit anderem User oder Betrag")
                    conn.rollback()
                    return {"newBalance": cached_balance, "duplicate": True}
                cur.execute(
                    """INSERT INTO credit_receipts
                           (provider, provider_tx_id, user_id, credits)
                       VALUES (%s, %s, %s::uuid, %s)""",
                    (normalized_provider, normalized_tx_id, user_id, amount),
                )

            new_balance = cached_balance + amount
            if new_balance < 0:
                raise InsufficientCredits(abs(amount), cached_balance)

            cur.execute(
                """INSERT INTO credit_ledger
                       (user_id, type, amount, reason, provider, provider_tx_id, created_by)
                   VALUES (%s::uuid, %s, %s, %s, %s, %s, %s::uuid)""",
                (
                    user_id,
                    ledger_type,
                    amount,
                    reason,
                    normalized_provider,
                    normalized_tx_id,
                    created_by,
                ),
            )
            cur.execute(
                "UPDATE admin_users SET credits = %s, last_active_at = NOW() "
                "WHERE id = %s::uuid",
                (new_balance, user_id),
            )
            if transaction_amount_eur is not None:
                cur.execute(
                    """INSERT INTO transactions
                           (user_id, user_email, type, amount, currency, status,
                            provider, provider_tx_id, description)
                       VALUES (%s::uuid, %s, 'credit_purchase', %s, 'EUR', 'completed',
                               %s, %s, %s)""",
                    (
                        user_id,
                        user_row["email"],
                        transaction_amount_eur,
                        normalized_provider,
                        normalized_tx_id,
                        reason,
                    ),
                )
            if audit_action:
                if not created_by or not audit_admin_email:
                    raise ValueError("Auditierte Credit-Änderung benötigt bestätigten Admin")
                cur.execute(
                    """INSERT INTO audit_log
                           (admin_id, admin_email, action, target_id, changes)
                       VALUES (%s::uuid, %s, %s, %s, %s::jsonb)""",
                    (
                        created_by,
                        audit_admin_email,
                        audit_action,
                        user_id,
                        psycopg2.extras.Json({
                            **(audit_changes or {}),
                            "newBalance": new_balance,
                        }),
                    ),
                )
        conn.commit()
        return {"newBalance": new_balance, "duplicate": False}
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _add_credits_and_log(
    user_id: str,
    credits: int,
    amount_eur: float,
    method: str,
    provider_tx_id: str,
    description: str,
) -> dict:
    return _apply_credit_delta(
        user_id,
        credits,
        ledger_type="credit_purchase",
        reason=description,
        provider=method,
        provider_tx_id=provider_tx_id,
        transaction_amount_eur=amount_eur,
    )


def _create_user_with_initial_credits(
    *,
    user_id: str,
    email: str,
    display_name: str,
    initial_credits: int = 500,
    password_hash: str | None = None,
    google_id: str | None = None,
    github_id: str | None = None,
    github_username: str | None = None,
    github_access_token: str | None = None,
    avatar_url: str | None = None,
) -> None:
    """Create account, signup-credit ledger and cache in one transaction."""
    if initial_credits < 0:
        raise ValueError("Initial-Credits dürfen nicht negativ sein")
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO admin_users
                       (id, email, display_name, password_hash, google_id, github_id,
                        github_username, github_access_token, avatar_url, role, credits,
                        subscription_status, is_banned, created_at, last_active_at)
                   VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s,
                           'user', 0, 'free', false, NOW(), NOW())""",
                (
                    user_id,
                    email,
                    display_name,
                    password_hash,
                    google_id,
                    github_id,
                    github_username,
                    github_access_token,
                    avatar_url,
                ),
            )
            if initial_credits > 0:
                cur.execute(
                    """INSERT INTO credit_ledger
                           (user_id, type, amount, reason, provider, provider_tx_id)
                       VALUES (%s::uuid, 'signup_bonus', %s,
                               'Initial account credits', 'system', %s)""",
                    (user_id, initial_credits, f"account-create:{user_id}"),
                )
                cur.execute(
                    "UPDATE admin_users SET credits = %s WHERE id = %s::uuid",
                    (initial_credits, user_id),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


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
        return jsonify({"paymentMethods": [], "error": str(exc), "runtimeState": "failed"}), 500


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
        return jsonify({"packages": [], "error": str(exc), "runtimeState": "failed"}), 500


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
    if "credits" in body:
        try:
            body["credits"] = int(body["credits"])
        except (TypeError, ValueError):
            return jsonify({"error": "credits muss eine ganze Zahl sein"}), 400
        if body["credits"] <= 0:
            return jsonify({"error": "credits muss größer als 0 sein"}), 400
    if "priceEur" in body:
        try:
            body["priceEur"] = round(float(body["priceEur"]), 2)
        except (TypeError, ValueError):
            return jsonify({"error": "priceEur muss eine Zahl sein"}), 400
        if body["priceEur"] < 0:
            return jsonify({"error": "priceEur darf nicht negativ sein"}), 400
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
    package = query(
        f"""UPDATE credit_packages SET {', '.join(sets)} WHERE id = %s::uuid
            RETURNING id::text, name, credits, price_eur::float AS "priceEur",
                      description, enabled, sort_order AS "sortOrder"
        """,
        vals, one=True, write=True,
    )
    if not package:
        return jsonify({"error": "Credit-Paket nicht gefunden"}), 404
    audit("admin_update_credit_package", pid, body)
    return jsonify({"ok": True, "package": dict(package), "persisted": True})


@app.route("/api/admin/credit-packages/<pid>", methods=["DELETE"])
@require_admin
def admin_delete_credit_package(pid):
    """Delete a credit package (soft delete by setting enabled=false)."""
    query(
        "UPDATE credit_packages SET enabled = false WHERE id = %s::uuid",
        (pid,), write=True,
    )
    audit("admin_delete_credit_package", pid, {"deleted": True})
    return jsonify({"ok": True})


# ── Admin: Crypto Confirmation ─────────────────────────────────────────────────

@app.route("/api/admin/payment-methods/crypto/confirm", methods=["POST"])
@require_admin
def admin_confirm_crypto_payment():
    """Admin manually confirms a crypto payment and credits the user."""
    body       = request.get_json(force=True) or {}
    user_id    = str(body.get("userId", ""))
    package_id = str(body.get("packageId", ""))
    tx_hash    = str(body.get("txHash", "")).strip()[:160]

    if not user_id or not package_id or len(tx_hash) < 8:
        return jsonify({"error": "userId, packageId und eine echte Transaktions-ID erforderlich"}), 400

    pkg = _get_credit_package(package_id)
    if not pkg:
        return jsonify({"error": "Paket nicht gefunden"}), 404

    description = f"Crypto {tx_hash}: {pkg['name']} ({pkg['credits']} Credits)"
    admin = get_current_admin() or {}
    try:
        result = _apply_credit_delta(
            user_id,
            int(pkg["credits"]),
            ledger_type="credit_purchase",
            reason=description,
            provider="crypto",
            provider_tx_id=tx_hash,
            created_by=str(admin.get("id") or ""),
            transaction_amount_eur=float(pkg["price_eur"]),
            audit_action="admin_confirm_crypto_payment",
            audit_admin_email=str(admin.get("email") or ""),
            audit_changes={
                "packageId": package_id,
                "txHash": tx_hash,
                "credits": int(pkg["credits"]),
            },
        )
    except LookupError:
        return jsonify({"error": "User nicht gefunden"}), 404
    except CreditStateConflict as exc:
        return jsonify({"error": str(exc), "blocker": "credit_state_verification_failed"}), 409
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "ok": True,
        "duplicate": result["duplicate"],
        "creditsAdded": 0 if result["duplicate"] else int(pkg["credits"]),
        "newBalance": result["newBalance"],
    })


# ── Public: Billing data ────────────────────────────────────────────────────────

@app.route("/api/billing")
def user_billing_overview():
    """Return available credit packages + current subscription for the user."""
    user_id = _get_session_user_id()
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
    except Exception as exc:
        return jsonify({
            "availablePackages": [],
            "packages": [],
            "subscription": None,
            "invoices": [],
            "error": str(exc),
            "runtimeState": "failed",
        }), 500

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
        except Exception as exc:
            return jsonify({
                "availablePackages": packages,
                "packages": packages,
                "subscription": None,
                "invoices": [],
                "error": str(exc),
                "runtimeState": "failed",
            }), 500

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


def _verify_paypal_webhook_signature(raw_body: bytes, webhook_id: str) -> bool:
    """Verify PayPal's signature against the exact received request body."""
    transmission_id = request.headers.get("paypal-transmission-id", "").strip()
    transmission_time = request.headers.get("paypal-transmission-time", "").strip()
    cert_url = request.headers.get("paypal-cert-url", "").strip()
    auth_algo = request.headers.get("paypal-auth-algo", "").strip()
    transmission_sig = request.headers.get("paypal-transmission-sig", "").strip()
    if not all((raw_body, webhook_id, transmission_id, transmission_time, cert_url, auth_algo, transmission_sig)):
        return False
    if auth_algo.upper() != "SHA256WITHRSA":
        return False
    parsed_cert_url = urllib.parse.urlparse(cert_url)
    if parsed_cert_url.scheme != "https" or parsed_cert_url.hostname not in {
        "api.paypal.com",
        "api.sandbox.paypal.com",
    }:
        return False
    try:
        import zlib
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        crc32_value = zlib.crc32(raw_body) & 0xffffffff
        signed_message = f"{transmission_id}|{transmission_time}|{webhook_id}|{crc32_value}".encode()
        cert_response = requests.get(cert_url, timeout=15)
        cert_response.raise_for_status()
        certificate = x509.load_pem_x509_certificate(cert_response.content)
        signature = base64.b64decode(transmission_sig, validate=True)
        certificate.public_key().verify(
            signature,
            signed_message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


@app.route("/api/billing/purchase/paypal/create-order", methods=["POST"])
def paypal_create_order():
    """Create a PayPal checkout order and return the approval URL."""
    body       = request.get_json(force=True) or {}
    package_id = str(body.get("packageId", ""))
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
    user_id, step_up_response = _authorize_credit_purchase(pkg)
    if step_up_response:
        return step_up_response

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
        if not approve_url:
            return jsonify({"error": "PayPal lieferte keine bestätigte Freigabe-URL"}), 502
        return jsonify({"orderId": order_id, "approvalUrl": approve_url})
    except Exception as exc:
        return jsonify({"error": f"PayPal-Fehler: {str(exc)[:120]}"}), 502


@app.route("/api/billing/purchase/paypal/capture", methods=["POST"])
def paypal_capture_order():
    """Capture an authenticated user's matching PayPal order exactly once."""
    body = request.get_json(force=True) or {}
    order_id = str(body.get("orderId", "")).strip()
    session_user_id = _get_session_user_id()
    if not session_user_id:
        return jsonify({"error": "Authentication required"}), 401
    if not order_id:
        return jsonify({"error": "orderId fehlt"}), 400

    pm = _get_payment_method("paypal")
    if not pm or not pm.get("enabled"):
        return jsonify({"error": "PayPal nicht aktiviert"}), 503
    cfg = pm.get("config") or {}
    client_id = cfg.get("client_id", "")
    client_secret = cfg.get("client_secret", "")
    mode = cfg.get("mode", "live")
    if not client_id or not client_secret:
        return jsonify({"error": "PayPal-Zugangsdaten nicht konfiguriert"}), 503

    try:
        token = _paypal_access_token(client_id, client_secret, mode)
        order_resp = requests.get(
            _paypal_base_url(mode) + f"/v2/checkout/orders/{order_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        order_resp.raise_for_status()
        order_data = order_resp.json()
        purchase_unit = (order_data.get("purchase_units") or [{}])[0]
        custom_id = str(purchase_unit.get("custom_id") or "")
        parts = (custom_id + "||").split("|")
        uid, pkg_id = parts[0].strip(), parts[1].strip()
        if uid != session_user_id:
            return jsonify({"error": "PayPal-Bestellung gehört nicht zur aktiven Session"}), 403
        pkg = _get_credit_package(pkg_id)
        if not pkg:
            return jsonify({"error": "Credit-Paket der PayPal-Bestellung nicht gefunden"}), 404
        order_amount = purchase_unit.get("amount") or {}
        try:
            order_value = round(float(order_amount.get("value")), 2)
        except (TypeError, ValueError):
            order_value = -1
        if str(order_amount.get("currency_code") or "").upper() != "EUR" or abs(order_value - round(float(pkg["price_eur"]), 2)) > 0.001:
            return jsonify({"error": "PayPal-Bestellbetrag stimmt nicht mit dem Paket überein"}), 400

        cap_resp = requests.post(
            _paypal_base_url(mode) + f"/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={},
            timeout=20,
        )
        cap_resp.raise_for_status()
        cap_data = cap_resp.json()
        if cap_data.get("status") != "COMPLETED":
            return jsonify({"error": f"Zahlung nicht abgeschlossen: {cap_data.get('status')}"}), 402

        capture = (
            (((cap_data.get("purchase_units") or [{}])[0].get("payments") or {})
             .get("captures") or [{}])[0]
        )
        capture_id = str(capture.get("id") or "").strip()
        if not capture_id:
            return jsonify({"error": "PayPal Capture lieferte keine Transaktions-ID"}), 502
        credits = int(pkg["credits"])
        description = f"PayPal Capture {capture_id}: {pkg['name']} ({credits} Credits)"
        result = _add_credits_and_log(
            uid,
            credits,
            float(pkg["price_eur"]),
            "paypal",
            capture_id,
            description,
        )
        return jsonify({
            "ok": True,
            "duplicate": result["duplicate"],
            "creditsAdded": 0 if result["duplicate"] else credits,
            "newBalance": result["newBalance"],
        })
    except LookupError:
        return jsonify({"error": "PayPal User nicht gefunden"}), 404
    except CreditStateConflict as exc:
        return jsonify({"error": str(exc), "blocker": "credit_state_verification_failed"}), 409
    except Exception as exc:
        return jsonify({"error": f"Capture-Fehler: {str(exc)[:120]}"}), 502


@app.route("/api/billing/webhooks/paypal", methods=["POST"])
def paypal_webhook():
    """Credit only a cryptographically verified, matching PayPal capture."""
    raw_body = request.get_data(cache=True)
    body = request.get_json(force=True) or {}
    pm = _get_payment_method("paypal")
    cfg = (pm or {}).get("config") or {}
    webhook_id = str(cfg.get("webhook_id") or "").strip()
    if not pm or not pm.get("enabled") or not webhook_id:
        return jsonify({"error": "PayPal Webhook-Verifikation ist nicht konfiguriert"}), 503
    if not _verify_paypal_webhook_signature(raw_body, webhook_id):
        return jsonify({"error": "Ungültige PayPal Webhook-Signatur"}), 400

    if body.get("event_type") != "PAYMENT.CAPTURE.COMPLETED":
        return jsonify({"ok": True, "processed": False})

    resource = body.get("resource") or {}
    capture_id = str(resource.get("id") or "").strip()
    custom_id = str(resource.get("custom_id") or "")
    if not custom_id:
        custom_id = str((resource.get("purchase_units") or [{}])[0].get("custom_id") or "")
    parts = (custom_id + "||").split("|")
    uid, pkg_id = parts[0].strip(), parts[1].strip()
    pkg = _get_credit_package(pkg_id)
    amount = resource.get("amount") or {}
    try:
        paid_value = round(float(amount.get("value")), 2)
    except (TypeError, ValueError):
        paid_value = -1
    paid_currency = str(amount.get("currency_code") or "").upper()
    if not capture_id or not uid or not pkg:
        return jsonify({"error": "PayPal Webhook enthält keine zuordenbare Capture-Evidence"}), 400
    if paid_currency != "EUR" or abs(paid_value - round(float(pkg["price_eur"]), 2)) > 0.001:
        return jsonify({"error": "PayPal Betrag oder Währung stimmt nicht mit dem Paket überein"}), 400

    description = f"PayPal Capture {capture_id}: {pkg['name']} ({pkg['credits']} Credits)"
    try:
        result = _add_credits_and_log(
            uid,
            int(pkg["credits"]),
            float(pkg["price_eur"]),
            "paypal",
            capture_id,
            description,
        )
    except LookupError:
        return jsonify({"error": "PayPal User nicht gefunden"}), 404
    except CreditStateConflict as exc:
        return jsonify({"error": str(exc), "blocker": "credit_state_verification_failed"}), 409
    return jsonify({
        "ok": True,
        "processed": not result["duplicate"],
        "duplicate": result["duplicate"],
        "creditsAdded": 0 if result["duplicate"] else int(pkg["credits"]),
        "newBalance": result["newBalance"],
    })


# ── Skrill ─────────────────────────────────────────────────────────────────────

@app.route("/api/billing/purchase/skrill/init", methods=["POST"])
def skrill_init():
    """Return a Skrill Quick Checkout redirect URL for the selected package."""
    body       = request.get_json(force=True) or {}
    package_id = str(body.get("packageId", ""))
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
    user_id, step_up_response = _authorize_credit_purchase(pkg)
    if step_up_response:
        return step_up_response

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
    """Credit only a configured, signed and amount-matching Skrill payment."""
    data = request.form
    status = data.get("status", "")
    user_id = data.get("user_id", "").strip()
    package_id = data.get("package_id", "").strip()
    transaction_id = data.get("transaction_id", "").strip()

    pm = _get_payment_method("skrill")
    if not pm or not pm.get("enabled"):
        return "SKRILL_NOT_CONFIGURED", 503
    cfg = pm.get("config") or {}
    secret_word = str(cfg.get("secret_word") or "").strip()
    merchant_email = str(cfg.get("merchant_email") or "").strip()
    if not secret_word or not merchant_email:
        return "SKRILL_VERIFICATION_NOT_CONFIGURED", 503

    expected_sig = hashlib.md5(
        (merchant_email +
         transaction_id +
         hashlib.md5(secret_word.upper().encode()).hexdigest() +
         data.get("mb_amount", "") +
         data.get("mb_currency", "") +
         status).encode()
    ).hexdigest().upper()
    received_sig = data.get("md5sig", "").upper()
    if not received_sig or not hmac.compare_digest(expected_sig, received_sig):
        return "INVALID_SIGNATURE", 400

    if status != "2":
        return "OK_NOT_PROCESSED", 200
    pkg = _get_credit_package(package_id)
    if not transaction_id or not user_id or not pkg:
        return "UNMAPPED_PAYMENT", 400
    try:
        paid_value = round(float(data.get("mb_amount", "")), 2)
    except (TypeError, ValueError):
        paid_value = -1
    if data.get("mb_currency", "").upper() != "EUR" or abs(paid_value - round(float(pkg["price_eur"]), 2)) > 0.001:
        return "AMOUNT_MISMATCH", 400

    description = f"Skrill {transaction_id}: {pkg['name']} ({pkg['credits']} Credits)"
    try:
        result = _add_credits_and_log(
            user_id,
            int(pkg["credits"]),
            float(pkg["price_eur"]),
            "skrill",
            transaction_id,
            description,
        )
    except LookupError:
        return "USER_NOT_FOUND", 404
    except CreditStateConflict:
        return "CREDIT_STATE_CONFLICT", 409
    return ("OK_DUPLICATE" if result["duplicate"] else "OK"), 200


# ── Crypto Wallets ─────────────────────────────────────────────────────────────

@app.route("/api/billing/purchase/crypto/info", methods=["POST"])
def crypto_info():
    """Return wallet address and EUR amount for a crypto payment."""
    body       = request.get_json(force=True) or {}
    package_id = str(body.get("packageId", ""))
    coin_type  = str(body.get("coinType") or body.get("paymentMethod") or "crypto_btc")

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
    _user_id, step_up_response = _authorize_credit_purchase(pkg)
    if step_up_response:
        return step_up_response

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
@require_session
def google_play_validate():
    """Validate a Google Play purchase token via Android Developer API."""
    import json as _json

    body           = request.get_json(force=True) or {}
    purchase_token = str(body.get("purchaseToken", ""))
    product_id     = str(body.get("productId", ""))
    user_id        = request.session_user_id

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

        if not pkg:
            return jsonify({"error": "Google-Play-Produkt ist keinem aktiven Credit-Paket zugeordnet"}), 404
        credits = int(pkg["credits"])
        price = float(pkg["price_eur"])
        pkg_name = pkg["name"]
        _approved_user_id, step_up_response = _authorize_credit_purchase({
            "id": str(pkg["id"]),
            "price_eur": price,
            "credits": credits,
        })
        if step_up_response:
            return step_up_response
        if _approved_user_id != user_id:
            return jsonify({"error": "Account mismatch"}), 403

        token_fingerprint = hashlib.sha256(purchase_token.encode()).hexdigest()
        description = f"Google Play {token_fingerprint}: {pkg_name} ({credits} Credits)"
        result = _add_credits_and_log(
            user_id,
            credits,
            price,
            "google_play",
            token_fingerprint,
            description,
        )
        return jsonify({
            "ok": True,
            "duplicate": result["duplicate"],
            "creditsAdded": 0 if result["duplicate"] else credits,
            "purchaseState": purchase_data.get("purchaseState"),
            "newBalance": result["newBalance"],
        })
    except LookupError:
        return jsonify({"error": "Google-Play User nicht gefunden"}), 404
    except CreditStateConflict as exc:
        return jsonify({"error": str(exc), "blocker": "credit_state_verification_failed"}), 409
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
        return jsonify({"methods": [], "error": str(exc), "runtimeState": "failed"}), 500


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
                "userKeyOverride":     False,
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
            "userKeyOverride":     False,
            "maxTokensPerRequest": 32_000,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── User Billing endpoints (Issue #458) ──────────────────────────────────────

@app.route("/api/billing/credits")
@require_session
def user_billing_credits():
    """Return credits only after cache/ledger verification."""
    user_id = request.session_user_id
    try:
        credits = _read_verified_credit_balance(user_id)
        return jsonify({
            "credits": credits,
            "creditStateVerified": True,
        })
    except LookupError:
        return jsonify({"error": "User nicht gefunden"}), 404
    except CreditStateConflict as exc:
        return jsonify({
            "error": str(exc),
            "blocker": "credit_state_verification_failed",
            "creditStateVerified": False,
        }), 409
    except Exception as exc:
        return jsonify({"error": str(exc), "runtimeState": "failed"}), 500


@app.route("/api/billing/deduct", methods=["POST"])
@require_session
def user_billing_deduct():
    """Server-side credit deduction with validation and usage logging."""
    body = request.get_json(force=True) or {}
    user_id = request.session_user_id
    cost_id = str(body.get("costId") or "").strip()
    try:
        amount = int(body.get("amount", 0))
        token_count = max(0, int(body.get("tokenCount", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "amount und tokenCount müssen ganze Zahlen sein"}), 400
    if not cost_id:
        return jsonify({"error": "costId erforderlich"}), 400

    try:
        route = query(
            """SELECT credits_per_unit::float AS credits_per_unit
               FROM llm_routes
               WHERE id::text=%s OR model_id=%s
               ORDER BY disabled ASC, priority ASC LIMIT 1""",
            (cost_id, cost_id), one=True,
        )
        fixed_costs = {
            "tool_vps_exec": 5,
            "tool_github_pr": 10,
            "tool_repo_load": 3,
        }
        if route:
            amount = max(1, int(((max(1, token_count) / 1000) * float(route["credits_per_unit"])) + 0.999999))
        elif cost_id in fixed_costs:
            amount = fixed_costs[cost_id]
        else:
            return jsonify({"error": "unknown_cost_id", "costId": cost_id}), 400

        step_up = consume_step_up_approval(
            get_agent_runtime_connection,
            user_id=user_id,
            action="expensive_llm_route",
            context={"costId": cost_id, "credits": amount, "tokenCount": token_count},
            token=request.headers.get("X-Step-Up-Token", "").strip() or None,
        )
        if not step_up.get("approved"):
            return jsonify({
                "error": "step_up_required",
                "action": "expensive_llm_route",
                "context": step_up.get("context"),
                "reason": step_up.get("reason"),
            }), 428

        try:
            result = _apply_credit_delta(
                user_id,
                -amount,
                ledger_type="usage",
                reason=f"Runtime usage: {cost_id}; tokens={token_count}",
                provider="runtime",
            )
        except LookupError:
            return jsonify({"error": "User nicht gefunden"}), 404
        except InsufficientCredits as exc:
            return jsonify({
                "error": "Nicht genug Credits",
                "available": exc.available,
                "required": exc.required,
            }), 402
        except CreditStateConflict as exc:
            return jsonify({
                "error": str(exc),
                "blocker": "credit_state_verification_failed",
            }), 409

        return jsonify({
            "ok": True,
            "deducted": amount,
            "newBalance": result["newBalance"],
            "ledgerType": "usage",
        })
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
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

JWT_SECRET   = os.getenv("JWT_SECRET", "")
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
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET ist nicht konfiguriert")
    import jwt as pyjwt
    return pyjwt.encode(
        {"sub": str(user_id), "exp": int(time.time()) + _COOKIE_MAX_AGE},
        JWT_SECRET, algorithm="HS256",
    )


def _decode_jwt(token: str) -> str | None:
    if not JWT_SECRET:
        return None
    try:
        import jwt as pyjwt
        data = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return str(data["sub"])
    except Exception:
        return None


# ── GitHub OAuth Config ───────────────────────────────────────────────────────
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_OAUTH_REDIRECT_URI = os.getenv(
    "GITHUB_OAUTH_REDIRECT_URI",
    "https://chat.arelorian.de/auth/github/callback.html",
).strip()

_DEFAULT_GITHUB_OAUTH_OPENER_ORIGINS = {
    "https://chat.arelorian.de",
    "https://arelorian.de",
    "http://localhost",
    "https://localhost",
    "capacitor://localhost",
}


def _normalize_oauth_origin(value: str) -> str:
    """Return one canonical origin without path, credentials, query or fragment."""
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    try:
        parsed = urllib.parse.urlsplit(candidate)
    except ValueError:
        return ""
    if parsed.scheme not in {"https", "http", "capacitor"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ""
    if parsed.path not in {"", "/"}:
        return ""
    hostname = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        return ""
    default_port = (parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80)
    port_suffix = "" if port is None or default_port else f":{port}"
    return f"{parsed.scheme}://{hostname}{port_suffix}"


def _github_oauth_allowed_opener_origins() -> set[str]:
    configured = {
        _normalize_oauth_origin(item)
        for item in os.getenv("GITHUB_OAUTH_ALLOWED_OPENER_ORIGINS", "").split(",")
        if item.strip()
    }
    return _DEFAULT_GITHUB_OAUTH_OPENER_ORIGINS | {item for item in configured if item}


def _is_allowed_github_oauth_opener_origin(origin: str) -> bool:
    normalized = _normalize_oauth_origin(origin)
    if normalized in _github_oauth_allowed_opener_origins():
        return True
    parsed = urllib.parse.urlsplit(normalized) if normalized else None
    return bool(
        parsed
        and parsed.scheme in {"http", "https"}
        and parsed.hostname in {"localhost", "127.0.0.1"}
    )


def _github_oauth_callback_origin() -> str:
    parsed = urllib.parse.urlsplit(GITHUB_OAUTH_REDIRECT_URI)
    return _normalize_oauth_origin(f"{parsed.scheme}://{parsed.netloc}")

# Initialisiere Token Encryption mit Key aus Environment
_token_encryption_key = os.getenv("GITHUB_TOKEN_ENCRYPTION_KEY", JWT_SECRET)
if _token_encryption_key:
    init_token_encryption(_token_encryption_key)


def _user_row_to_dict(row) -> dict:
    """Konvertiert nur einen cache-/ledger-verifizierten User zur API-Antwort."""
    user_id = str(row["id"])
    verified_credits = _read_verified_credit_balance(user_id)
    result = {
        "id":                 user_id,
        "email":              row["email"],
        "displayName":        row.get("display_name") or "",
        "role":               row.get("role") or "user",
        "credits":            verified_credits,
        "creditStateVerified": True,
        "subscriptionStatus": row.get("subscription_status") or "free",
        "isBanned":           bool(row.get("is_banned")),
        "createdAt":          str(row.get("created_at") or ""),
        "avatarUrl":          row.get("avatar_url"),
        "googleId":           row.get("google_id"),
        # GitHub-Felder (Token wird NIE im Response gesendet!)
        "githubId":           row.get("github_id"),
        "githubUsername":     row.get("github_username"),
    }
    return result


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
        _create_user_with_initial_credits(
            user_id=new_id,
            email=email,
            display_name=display_name or email.split("@")[0],
            password_hash=pw_hash,
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
            _create_user_with_initial_credits(
                user_id=user_id,
                email=email,
                display_name=display_name,
                google_id=google_id,
                avatar_url=avatar_url,
            )

        row = query("SELECT * FROM admin_users WHERE id = %s::uuid LIMIT 1", (user_id,), one=True)
        resp = make_response(jsonify(_user_row_to_dict(row)))
        return _set_session_cookie(resp, user_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/auth/github/callback-context", methods=["GET"])
def auth_github_callback_context():
    """Expose only the approved opener origin for one still-valid OAuth state."""
    state = str(request.args.get("state") or "").strip()
    if not state:
        return jsonify({"error": "OAuth State fehlt"}), 400
    stored_state = _peek_oauth_state(state)
    if not stored_state:
        return jsonify({"error": "Ungültiger oder abgelaufener State"}), 404
    opener_origin = _normalize_oauth_origin(str(stored_state.get("opener_origin") or ""))
    if not opener_origin or not _is_allowed_github_oauth_opener_origin(opener_origin):
        return jsonify({"error": "OAuth Rückkanal ist nicht erlaubt"}), 403
    response = make_response(jsonify({
        "openerOrigin": opener_origin,
        "callbackOrigin": _github_oauth_callback_origin(),
    }))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/auth/github", methods=["POST"])
def auth_github():
    """
    GitHub OAuth Login Endpoint.
    
    Security:
    - Token wird verschlüsselt in DB gespeichert
    - Token wird NIE im Response zurückgegeben
    - State-Validierung gegen CSRF
    - PKCE-Validierung (optional)
    
    Request Body:
        {
            "code": "oauth_authorization_code",
            "state": "csrf_state",          // Optional aber empfohlen
            "code_verifier": "pkce_verifier" // Optional (PKCE)
        }
    
    Response:
        User-Objekt (OHNE Token!) + Session Cookie
    """
    try:
        # Get client IP for rate-limiting and audit
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()
        
        # Rate limiting for OAuth callback
        allowed, remaining = _check_rate_limit(f"github_callback:{client_ip}", max_requests=20)
        if not allowed:
            _audit_event("RATE_LIMIT_EXCEEDED", False, "github_callback", client_ip)
            return jsonify({"error": "Zu viele Anfragen. Bitte später erneut versuchen."}), 429
        
        if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
            return jsonify({"error": "GitHub OAuth nicht konfiguriert"}), 500
        
        body = request.get_json(force=True) or {}
        code = body.get("code") or ""
        state = str(body.get("state") or "").strip()
        code_verifier = str(body.get("code_verifier") or "").strip()

        if not code:
            return jsonify({"error": "Authorization Code fehlt"}), 400
        if not state or not code_verifier:
            return jsonify({"error": "GitHub OAuth benötigt State und PKCE-Verifier"}), 400

        # 1. State validieren (CSRF-Schutz)
        stored_state = _get_oauth_state(state)
        if not stored_state:
            return jsonify({"error": "Ungültiger oder abgelaufener State"}), 400

        # 2. PKCE validieren
        stored_challenge = stored_state.get("code_challenge")
        if not _validate_pkce(code_verifier, stored_challenge):
            return jsonify({"error": "PKCE Validierung fehlgeschlagen"}), 400

        # 3. Code gegen Access Token tauschen
        token_payload = {
            "client_id":     GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code":          code,
        }
        if code_verifier:
            token_payload["code_verifier"] = code_verifier
        if stored_state.get("redirect_uri"):
            token_payload["redirect_uri"] = stored_state["redirect_uri"]

        token_resp = requests.post(
            "https://github.com/login/oauth/access_token",
            json=token_payload,
            headers={"Accept": "application/json"},
            timeout=15,
        )
        if not token_resp.ok:
            return jsonify({"error": "Konnte Access Token nicht erhalten"}), 502
        
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return jsonify({"error": "Kein Access Token von GitHub erhalten"}), 502

        # 4. GitHub User-Info abrufen
        user_resp = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )
        if not user_resp.ok:
            return jsonify({"error": "Konnte GitHub User nicht abrufen"}), 502
        
        github_user = user_resp.json()
        github_id = str(github_user.get("id", ""))
        github_username = github_user.get("login", "")
        email = (github_user.get("email") or "").lower()
        display_name = github_user.get("name") or github_user.get("login") or "User"
        avatar_url = github_user.get("avatar_url")

        # 5. Private Email abrufen falls nötig
        if not email:
            email_resp = requests.get(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=15,
            )
            if email_resp.ok:
                for e in email_resp.json():
                    if e.get("primary") and e.get("verified"):
                        email = e.get("email", "").lower()
                        break
        
        if not email:
            email = f"{github_username}@users.noreply.github.com"
        if not github_id:
            return jsonify({"error": "Unvollständige GitHub-Daten"}), 400

        # 6. Token VERSCHLÜSSELT speichern (NIEMALS im Klartext!)
        encrypted_token = _encrypt_token(access_token)

        # 7. User finden oder erstellen
        row = query(
            "SELECT * FROM admin_users WHERE github_id = %s OR email = %s LIMIT 1",
            (github_id, email), one=True,
        )

        if row:
            user_id = str(row["id"])
            query(
                """UPDATE admin_users
                   SET github_id = %s, github_username = %s,
                       github_access_token = %s, avatar_url = COALESCE(%s, avatar_url),
                       last_active_at = NOW()
                   WHERE id = %s::uuid""",
                (github_id, github_username, encrypted_token, avatar_url, user_id), write=True,
            )
        else:
            user_id = str(uuid.uuid4())
            _create_user_with_initial_credits(
                user_id=user_id,
                email=email,
                display_name=display_name,
                initial_credits=500,
                github_id=github_id,
                github_username=github_username,
                github_access_token=encrypted_token,
                avatar_url=avatar_url,
            )

        # 8. User zurückgeben (OHNE Token!)
        _audit_event("GITHUB_LOGIN_SUCCESS", True, f"user_id={user_id}, github={github_username}", client_ip)
        row = query("SELECT * FROM admin_users WHERE id = %s::uuid LIMIT 1", (user_id,), one=True)
        resp = make_response(jsonify(_user_row_to_dict(row)))
        return _set_session_cookie(resp, user_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/auth/github/init", methods=["POST"])
def auth_github_init():
    """
    Initiiert GitHub OAuth Flow und gibt Auth-URL zurück.
    
    Generiert State + PKCE Challenge für sicheren OAuth Flow.
    
    Response:
        {
            "authUrl": "https://github.com/login/oauth/authorize?...",
            "state": "csrf_state",
            "code_challenge": "pkce_challenge"
        }
    """
    try:
        if not GITHUB_CLIENT_ID:
            return jsonify({"error": "GitHub OAuth nicht konfiguriert"}), 500
        
        body = request.get_json(force=True) or {}
        requested_redirect_uri = str(body.get("redirect_uri") or "").strip()
        requested_opener_origin = str(
            body.get("opener_origin")
            or request.headers.get("Origin")
            or ""
        ).strip()
        if not requested_opener_origin and requested_redirect_uri:
            parsed_requested_redirect = urllib.parse.urlsplit(requested_redirect_uri)
            requested_opener_origin = f"{parsed_requested_redirect.scheme}://{parsed_requested_redirect.netloc}"
        opener_origin = _normalize_oauth_origin(requested_opener_origin)

        # OAuth Redirect URI wird SERVERSEITIG festgelegt.
        # Client-Input wird ignoriert, um Redirect-URI-Mismatch zu vermeiden.
        redirect_uri = GITHUB_OAUTH_REDIRECT_URI
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()
        if not opener_origin or not _is_allowed_github_oauth_opener_origin(opener_origin):
            _audit_event(
                "GITHUB_OAUTH_OPENER_REJECTED",
                False,
                f"opener_origin={requested_opener_origin[:160]}",
                client_ip,
            )
            return jsonify({
                "error": "GitHub OAuth Rückkanal-Origin ist nicht erlaubt",
                "blocker": "github_oauth_opener_origin_not_allowed",
            }), 400
        if requested_redirect_uri and requested_redirect_uri != GITHUB_OAUTH_REDIRECT_URI:
            _audit_event(
                "GITHUB_OAUTH_REDIRECT_IGNORED",
                False,
                f"client_redirect_uri={requested_redirect_uri}",
                client_ip,
            )

        # OAuth darf nicht durch Client-Input auf repo/write-Scope erweitert werden.
        # Schreibzugang läuft separat über validierten GitHub-Zugang, nicht über den
        # Login-Flow der APK/WebView.
        scopes = ["read:user", "user:email"]

        # Generiere State + PKCE über das zentrale Security-Modul.
        state = _generate_state()
        code_verifier, code_challenge = _generate_pkce()

        # State + PKCE speichern. Der Verifier bleibt beim Client und wird nicht
        # serverseitig persistiert; der Server braucht für die Callback-Prüfung nur
        # den Challenge-Wert.
        _store_oauth_state(state, {
            "code_challenge": code_challenge,
            "redirect_uri": redirect_uri,
            "opener_origin": opener_origin,
        })
        
        # GitHub Auth URL bauen
        params = urllib.parse.urlencode({
            "client_id": GITHUB_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        })
        auth_url = f"https://github.com/login/oauth/authorize?{params}"
        
        return jsonify({
            "authUrl": auth_url,
            "state": state,
            "codeChallenge": code_challenge,
            "codeVerifier": code_verifier,  # Client braucht das für Token-Request
            "callbackOrigin": _github_oauth_callback_origin(),
            "openerOrigin": opener_origin,
        })
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
        path  = normalize_agent_path(str(b.get("path") or ""))
        ref   = b.get("ref")
        if not owner or not repo or not path:
            return jsonify({"error": "owner, repo und valider Pfad erforderlich"}), 400
        if ref and not is_safe_branch(ref):
            return jsonify({"error": "Ungültiger Branch-Name"}), 400
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
        path_raw = str(b.get("path") or "").strip()
        if not path_raw or path_raw == "." or path_raw == "./":
            path = ""
        else:
            path = normalize_agent_path(path_raw)
            if path is None:
                return jsonify({"error": "valider Pfad erforderlich"}), 400

        ref   = b.get("ref")
        if not owner or not repo:
            return jsonify({"error": "owner und repo erforderlich"}), 400
        if ref and not is_safe_branch(ref):
            return jsonify({"error": "Ungültiger Branch-Name"}), 400
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
        path   = normalize_agent_path(str(b.get("path") or ""))
        blocks = b.get("blocks", [])
        ref    = b.get("ref")
        if not owner or not repo or not path or not blocks:
            return jsonify({"error": "owner, repo, valider Pfad und blocks erforderlich"}), 400
        if ref and not is_safe_branch(ref):
            return jsonify({"error": "Ungültiger Branch-Name"}), 400

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
        path    = normalize_agent_path(str(b.get("path") or ""))
        message = b.get("message", "")
        blocks  = b.get("blocks", [])
        confirm = b.get("confirm", False)

        if not all([owner, repo, path, message, blocks]):
            return jsonify({"error": "owner, repo, valider Pfad, message und blocks erforderlich"}), 400

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
        path    = normalize_agent_path(str(b.get("path") or ""))
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
        if ref and not is_safe_branch(ref):
            return jsonify({"error": "Ungültiger Branch-Name"}), 400
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
        path  = normalize_agent_path(str(b.get("path") or ""))
        if not owner or not repo or not path:
            return jsonify({"error": "owner, repo und valider Pfad erforderlich"}), 400
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
      <button onclick="showSection('knowledge',this)">📚 Wissen & PDF</button>
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

    <!-- KNOWLEDGE -->
    <div id="s-knowledge" class="section">
      <h2>Wissensdatenbank & PDF-Einspeisung</h2>
      <div class="subtitle">Admin-eigene Referenzquellen in PostgreSQL/pgvector. SHA-256 verhindert Duplikate.</div>
      <div class="card">
        <div class="form-group"><label>GitHub- oder Wikipedia-URL</label><input type="text" id="knowledgeUrl" placeholder="https://github.com/..."/></div>
        <button class="btn btn-primary" onclick="importKnowledgeUrlAdmin()">URL importieren</button>
        <div class="form-group" style="margin-top:14px"><label>PDF, Markdown, Text oder Code</label><input type="file" id="knowledgeFile" accept=".pdf,.txt,.md,.markdown,.mdx,.rst,.json,.yaml,.yml,.toml,.py,.ts,.tsx,.js,.jsx,.java,.kt,.c,.cc,.cpp,.h,.hpp,.rs,.go,.cs,.php,.rb,.sh,.sql"/></div>
        <button class="btn btn-primary" onclick="uploadKnowledgeFileAdmin()">Datei einspeisen</button>
        <button class="btn btn-ghost" style="margin-left:8px" onclick="repairKnowledgeEmbeddingsAdmin()">Fehlende Vektoren reparieren</button>
        <div class="msg" id="knowledgeMsg"></div>
      </div>
      <div class="card">
        <div class="form-group"><label>Semantische Testsuche</label><input type="text" id="knowledgeQuery" placeholder="Wissensfrage"/></div>
        <button class="btn btn-ghost" onclick="searchKnowledgeAdmin()">Suchen</button>
        <div id="knowledgeResults" style="margin-top:12px"></div>
      </div>
      <div id="knowledgeList"><div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div></div>
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
      <div class="subtitle">Worker AI Modelle und Routing konfigurieren.</div>
      
      <!-- Worker AI Status -->
      <div class="card" style="margin-bottom:16px">
        <div class="card-header">
          <span class="card-title">🤖 Cloudflare Worker AI</span>
          <span class="badge" id="wai-status-badge">Lade…</span>
          <span class="chevron">▼</span>
        </div>
        <div class="card-body" id="wai-body">
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px">
            <div>
              <label style="color:var(--muted);font-size:11px;text-transform:uppercase">Status</label>
              <div id="wai-status" style="font-size:16px;font-weight:500">-</div>
            </div>
            <div>
              <label style="color:var(--muted);font-size:11px;text-transform:uppercase">Verfügbare Modelle</label>
              <div id="wai-model-count" style="font-size:16px;font-weight:500">-</div>
            </div>
            <div>
              <label style="color:var(--muted);font-size:11px;text-transform:uppercase">Letzte Prüfung</label>
              <div id="wai-timestamp" style="font-size:14px">-</div>
            </div>
          </div>
          <div class="btn-row">
            <button class="btn btn-primary" onclick="syncWorkerAI()">🔄 Worker AI synchronisieren</button>
            <button class="btn btn-ghost" onclick="loadWorkerAIStatus()">🔍 Status prüfen</button>
          </div>
          <div class="msg" id="wai-msg" style="display:none;margin-top:12px"></div>
        </div>
      </div>
      
      <!-- Available Models from Worker AI -->
      <div class="card" style="margin-bottom:16px">
        <div class="card-header">
          <span class="card-title">📋 Verfügbare Modelle</span>
          <span class="chevron">▼</span>
        </div>
        <div class="card-body" id="wai-models-body">
          <div id="wai-models-list"><div style="color:var(--muted)">Klicke "Status prüfen" um Modelle zu laden…</div></div>
        </div>
      </div>
      
      <!-- Configured Routes -->
      <h3 style="margin:24px 0 12px;font-size:14px;color:var(--muted)">KONFIGURIERTE ROUTES</h3>
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
let API_KEY = '';

function hdr(){ return {'Authorization':'Bearer '+API_KEY,'Content-Type':'application/json'}; }
function formHdr(){ const headers=hdr(); delete headers['Content-Type']; return headers; }

async function boundedFetch(path, options={}, timeoutMs=15000){
  const controller=new AbortController();
  const timeout=timeoutMs>0?setTimeout(()=>controller.abort(),timeoutMs):null;
  try{
    const response=await fetch(BASE+path,{...options,signal:controller.signal});
    const text=await response.text();
    let data={};
    try{ data=text?JSON.parse(text):{}; }catch{ data={error:text||('HTTP '+response.status)}; }
    if(!response.ok){
      if(response.status===401||response.status===403) resetAdminSession();
      throw new Error(data.error||('HTTP '+response.status));
    }
    return data;
  }catch(error){
    if(error&&error.name==='AbortError') throw new Error('Backend-Zeitüberschreitung nach '+Math.ceil(timeoutMs/1000)+' Sekunden.');
    throw error;
  }finally{ if(timeout!==null) clearTimeout(timeout); }
}

async function doLogin(){
  const k = document.getElementById('keyInput').value.trim();
  if(!k) return;
  const e = document.getElementById('loginErr');
  e.style.display='none';
  try{
    const r = await fetch(BASE+'/api/admin/ping',{headers:{'Authorization':'Bearer '+k}});
    const data = await r.json().catch(()=>({}));
    if(!r.ok || data.ok!==true || !data.id){
      throw new Error(data.error||('HTTP '+r.status));
    }
    API_KEY = k;
    initApp();
  }catch(error){
    API_KEY='';
    e.textContent='Admin-Sitzung nicht bestätigt: '+error.message;
    e.style.display='block';
  }
}

document.getElementById('keyInput').addEventListener('keydown',e=>{ if(e.key==='Enter') doLogin(); });

function resetAdminSession(){
  API_KEY='';
  document.getElementById('app').style.display='none';
  document.getElementById('login').style.display='flex';
}

function doLogout(){
  resetAdminSession();
}

function initApp(){
  document.getElementById('login').style.display='none';
  document.getElementById('app').style.display='flex';
  loadPaymentMethods();
  loadPackages();
  loadKnowledge();
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
  
  // Load Worker AI status when LLM section is shown
  if(id === 'llm'){
    loadWorkerAIStatus();
    loadLLMRoutes();
  }
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
  const el=document.getElementById('pkgList');
  el.innerHTML='<div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div>';
  try{
    const d=await boundedFetch('/api/admin/credit-packages',{headers:hdr()});
    pkgData=d.packages||[];
    renderPkg();
  }catch(error){
    el.innerHTML='<div style="color:var(--danger)">Fehler: '+esc(error.message)+' <button class="btn btn-ghost" onclick="loadPackages()">Erneut laden</button></div>';
  }
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
      <span style="color:var(--muted);font-size:13px;margin-right:8px">${p.credits} Credits · €${parseFloat(p.priceEur).toFixed(2)}</span>
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
      <div class="form-group"><label>Preis (EUR)</label><input type="text" id="pp_${p.id}" value="${parseFloat(p.priceEur).toFixed(2)}"/></div>
      <div class="form-group"><label>Beschreibung</label><input type="text" id="pd_${p.id}" value="${esc(p.description||'')}"/></div>
      <div class="btn-row">
        <button class="btn btn-primary" onclick="savePkg('${p.id}')">Speichern</button>
        <button class="btn btn-danger" onclick="deletePkg('${p.id}')" style="margin-left:8px">Löschen</button>
      </div>
      <div class="msg" id="pmsg_${p.id}"></div>
    </div>
  </div>`;
}

function toggleCard2(id){
  document.getElementById('pkg_'+id).classList.toggle('open');
}

async function deletePkg(id){
  if(!confirm('Credit-Paket wirklich löschen? Es wird deaktiviert und verschwindet aus dem Shop.')) return;
  const r = await fetch(BASE+'/api/admin/credit-packages/'+id,{method:'DELETE',headers:hdr()});
  if(r.ok){
    pkgData = pkgData.filter(p=>p.id!==id);
    renderPkg();
    alert('Paket gelöscht ✓');
  } else {
    alert('Fehler beim Löschen');
  }
}

async function togglePkg(id, enabled){
  await fetch(BASE+'/api/admin/credit-packages/'+id,{method:'PATCH',headers:hdr(),body:JSON.stringify({enabled})});
  const p=pkgData.find(x=>x.id===id); if(p) p.enabled=enabled;
  const badge=document.querySelector('#pkg_'+id+' .badge');
  if(badge){ badge.textContent=enabled?'Aktiv':'Inaktiv'; badge.className='badge '+(enabled?'on':'off'); }
}

async function savePkg(id){
  const body={
    name: document.getElementById('pn_'+id).value.trim(),
    credits: parseInt(document.getElementById('pc_'+id).value,10),
    priceEur: parseFloat(document.getElementById('pp_'+id).value),
    description: document.getElementById('pd_'+id).value,
  };
  if(!body.name||!Number.isInteger(body.credits)||body.credits<=0||!Number.isFinite(body.priceEur)||body.priceEur<0){
    showPkgMsg(id,false,'Ungültiger Name, Credit-Wert oder Preis.'); return;
  }
  try{
    const result=await boundedFetch('/api/admin/credit-packages/'+id,{method:'PATCH',headers:hdr(),body:JSON.stringify(body)});
    if(!result.persisted||!result.package) throw new Error('Backend hat Persistenz nicht bestätigt.');
    const verify=await boundedFetch('/api/admin/credit-packages',{headers:hdr()});
    const saved=(verify.packages||[]).find(item=>item.id===id);
    if(!saved||Math.abs(Number(saved.priceEur)-Number(result.package.priceEur))>0.001) throw new Error('Reload-Verifikation fehlgeschlagen.');
    pkgData=verify.packages;
    renderPkg();
    alert('Dauerhaft gespeichert: '+saved.name+' · €'+Number(saved.priceEur).toFixed(2));
  }catch(error){ showPkgMsg(id,false,error.message); }
}

function showPkgMsg(id, ok, text){
  const el=document.getElementById('pmsg_'+id);
  if(!el) return;
  el.textContent=text; el.className='msg '+(ok?'ok':'err'); el.style.display='block';
  setTimeout(()=>{ el.style.display='none'; },3000);
}

/* ────── KNOWLEDGE ────── */
async function loadKnowledge(){
  const el=document.getElementById('knowledgeList');
  el.innerHTML='<div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div>';
  try{
    const data=await boundedFetch('/api/admin/knowledge/sources',{headers:hdr()});
    const sources=data.sources||[];
    el.innerHTML=sources.length?sources.map(source=>`<div class="card"><div class="card-header"><span class="card-title">${esc(source.title)}</span><span class="badge ${source.status==='ready'?'on':'off'}">${esc(source.status)}</span></div><div style="color:var(--muted);font-size:12px;margin-top:8px">${esc(source.sourceType)} · ${source.chunkCount||0} Blöcke</div>${source.blocker?`<div style="color:var(--warn);font-size:11px">${esc(source.blocker)}</div>`:''}<button class="btn btn-danger" style="margin-top:8px" onclick="deleteKnowledgeAdmin('${source.id}')">Löschen</button></div>`).join(''):'<div style="color:var(--muted)">Noch keine Quellen.</div>';
  }catch(error){ el.innerHTML='<div style="color:var(--danger)">Fehler: '+esc(error.message)+' <button class="btn btn-ghost" onclick="loadKnowledge()">Erneut laden</button></div>'; }
}
function knowledgeMessage(text,ok){ const el=document.getElementById('knowledgeMsg'); el.textContent=text; el.className='msg '+(ok?'ok':'err'); el.style.display='block'; }
async function importKnowledgeUrlAdmin(){
  const url=document.getElementById('knowledgeUrl').value.trim(); if(!url)return;
  knowledgeMessage('Quelle wird geladen, geparst, gechunkt und eingebettet. Dieser bestätigte Backend-Lauf kann mehrere Minuten dauern.',true);
  try{ const result=await boundedFetch('/api/admin/knowledge/sources/url',{method:'POST',headers:hdr(),body:JSON.stringify({url})},0); knowledgeMessage(result.duplicate?'Quelle bereits vorhanden.':'Quelle gespeichert: '+result.source.title,true); document.getElementById('knowledgeUrl').value=''; await loadKnowledge(); }
  catch(error){ knowledgeMessage(error.message,false); }
}
async function uploadKnowledgeFileAdmin(){
  const file=document.getElementById('knowledgeFile').files[0]; if(!file){knowledgeMessage('Bitte eine Datei auswählen.',false);return;}
  const form=new FormData(); form.append('file',file);
  knowledgeMessage('Datei wird geladen, geparst, gechunkt und eingebettet. Dieser bestätigte Backend-Lauf kann mehrere Minuten dauern.',true);
  try{ const result=await boundedFetch('/api/admin/knowledge/sources/upload',{method:'POST',headers:formHdr(),body:form},0); knowledgeMessage(result.duplicate?'Datei bereits vorhanden.':'Datei gespeichert: '+result.source.title,true); document.getElementById('knowledgeFile').value=''; await loadKnowledge(); }
  catch(error){ knowledgeMessage(error.message,false); }
}
async function repairKnowledgeEmbeddingsAdmin(){
  knowledgeMessage('Fehlende PDF- und Wissensvektoren werden in begrenzten Batches neu berechnet.',true);
  try{
    const result=await boundedFetch('/api/admin/knowledge/repair',{method:'POST',headers:hdr(),body:JSON.stringify({maxBatches:8})},0);
    const remaining=Number(result.remaining||0);
    knowledgeMessage(String(result.repaired||0)+' Vektoren repariert'+(remaining>0?', '+remaining+' noch offen. Bitte erneut ausführen.':'. Suche ist bereit.'),remaining===0);
    await loadKnowledge();
  }catch(error){ knowledgeMessage(error.message,false); }
}
async function searchKnowledgeAdmin(){
  const query=document.getElementById('knowledgeQuery').value.trim(); if(!query)return;
  const el=document.getElementById('knowledgeResults'); el.innerHTML='Suche… <span class="spin"></span>';
  try{ const data=await boundedFetch('/api/admin/knowledge/search',{method:'POST',headers:hdr(),body:JSON.stringify({query,limit:8})},120000); el.innerHTML=(data.results||[]).map(item=>`<div style="border-top:1px solid var(--border);padding:8px 0"><strong>${esc(item.sourceTitle)}</strong> · ${Math.round(Number(item.similarity)*100)}%<div style="color:var(--muted);font-size:11px;white-space:pre-wrap">${esc(String(item.content||'').slice(0,700))}</div></div>`).join('')||'<div style="color:var(--muted)">Keine Treffer.</div>'; }
  catch(error){ el.innerHTML='<div style="color:var(--danger)">'+esc(error.message)+'</div>'; }
}
async function deleteKnowledgeAdmin(id){ if(!confirm('Quelle wirklich löschen?'))return; try{await boundedFetch('/api/admin/knowledge/sources/'+id,{method:'DELETE',headers:hdr()});await loadKnowledge();}catch(error){knowledgeMessage(error.message,false);} }

/* ────── USERS ────── */
let userPage = 1;

async function loadUsers(pg=1){
  userPage = pg;
  const search = encodeURIComponent(document.getElementById('userSearch').value);
  const el = document.getElementById('userList');
  el.innerHTML='<div style="color:var(--muted);font-size:14px">Lade… <span class="spin"></span></div>';
  try {
    const d=await boundedFetch('/api/admin/users?page='+pg+'&search='+search,{headers:hdr()});
    renderUsers(d);
  }catch(e){ el.innerHTML='<div style="color:var(--danger)">Fehler: '+esc(e.message)+' <button class="btn btn-ghost" onclick="loadUsers('+pg+')">Erneut laden</button></div>'; }
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
    <div class="card-header" onclick="toggleUserCard('${u.id}')">
      <span class="card-title">${esc(u.email||'')}</span>
      <span style="color:var(--muted);font-size:13px">${esc(u.displayName||'')}</span>
      <span class="badge ${statusCls}">${status}</span>
      <span class="chevron">▼</span>
    </div>
    <div class="card-body" id="ubody_${u.id}">
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Credits</label><div style="font-size:18px;font-weight:600;cursor:pointer" onclick="quickAddCredits('${u.id}',${u.credits||0})">${u.credits||0} 💎</div></div>
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Rolle</label><div>${esc(u.role||'user')}</div></div>
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Erstellt</label><div style="font-size:12px">${u.createdAt?(new Date(u.createdAt)).toLocaleDateString():''}</div></div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-ghost" onclick="toggleBan('${u.id}',${!u.isBanned})">${u.isBanned?'Entsperren':'Sperren'}</button>
        <button class="btn btn-ghost" onclick="adjustCredits('${u.id}')">Credits anpassen</button>
        <button class="btn btn-primary" onclick="quickAddCredits('${u.id}',${u.credits||0})">+ Credits</button>
      </div>
    </div>
  </div>`;
}

function toggleUserCard(id){
  document.getElementById('ur_'+id).classList.toggle('open');
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

async function quickAddCredits(uid, currentCredits){
  const add = prompt('Credits hinzufügen (aktueller Stand: '+currentCredits+'):','500');
  if(add===null) return;
  const addInt = parseInt(add);
  if(isNaN(addInt)||addInt<=0){ alert('Ungültiger Betrag.'); return; }
  const reason = prompt('Grund:','Admin-Gutschrift');
  if(!reason) return;
  const r = await fetch(BASE+'/api/admin/users/'+uid+'/credit-adjustment',{
    method:'POST',headers:hdr(),body:JSON.stringify({amount:addInt,reason})
  });
  const d = await r.json();
  if(d.error) alert('Fehler: '+d.error);
  else { alert('+' + addInt + ' Credits hinzugefügt ✓'); loadUsers(userPage); }
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
    const d=await boundedFetch(url.replace(BASE,''),{headers:hdr()});
    renderBilling(d);
  }catch(e){ el.innerHTML='<div style="color:var(--danger)">Fehler: '+esc(e.message)+' <button class="btn btn-ghost" onclick="loadBilling('+pg+')">Erneut laden</button></div>'; }
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

/* ────── WORKER AI ────── */
async function loadWorkerAIStatus(){
  try {
    const r = await fetch(BASE+'/api/admin/llm/worker-ai/status',{headers:hdr()});
    const d = await r.json();
    
    // Update status badge
    const badge = document.getElementById('wai-status-badge');
    badge.className = 'badge ' + (d.status === 'healthy' ? 'on' : 'off');
    badge.textContent = d.status === 'healthy' ? 'Aktiv' : d.status === 'error' ? 'Fehler' : 'Unbekannt';
    
    // Update info
    document.getElementById('wai-status').textContent = d.status === 'healthy' ? '✓ Verbunden' : d.status === 'error' ? '✗ Fehler' : '? Unbekannt';
    document.getElementById('wai-model-count').textContent = d.modelCount || 0;
    document.getElementById('wai-timestamp').textContent = d.timestamp ? new Date(d.timestamp).toLocaleTimeString() : '-';
    
    // Show models list
    if(d.availableModels && d.availableModels.length > 0){
      const modelsHtml = d.availableModels.map(m => {
        const id = m.id || '';
        const friendly = id.replace('@cf/', '').replace(/\//g, ' / ');
        return `<div style="padding:8px 12px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
          <div>
            <div style="font-weight:500">${friendly}</div>
            <div style="font-size:12px;color:var(--muted)">${id}</div>
          </div>
          <span style="font-size:11px;padding:2px 8px;background:var(--success);color:white;border-radius:4px">✓ Verfügbar</span>
        </div>`;
      }).join('');
      document.getElementById('wai-models-list').innerHTML = modelsHtml;
    } else {
      document.getElementById('wai-models-list').innerHTML = '<div style="color:var(--muted)">Keine Modelle gefunden</div>';
    }
    
    showWaiMsg('Worker AI Status aktualisiert', true);
  } catch(e){
    showWaiMsg('Fehler: ' + e.message, false);
  }
}

function showWaiMsg(text, ok){
  const el = document.getElementById('wai-msg');
  el.textContent = text;
  el.className = 'msg ' + (ok ? 'ok' : 'err');
  el.style.display = 'block';
  if(ok) setTimeout(() => { el.style.display = 'none'; }, 3000);
}

async function syncWorkerAI(){
  const btn = event.target;
  btn.disabled = true;
  btn.innerHTML = '⏳ Synchronisiere…';
  
  try {
    const r = await fetch(BASE+'/api/admin/llm/worker-ai/sync',{method:'POST',headers:hdr()});
    const d = await r.json();
    
    if(d.ok){
      const created = d.synced?.created?.length || 0;
      const updated = d.synced?.updated?.length || 0;
      const disabled = d.synced?.disabled?.length || 0;
      showWaiMsg(`✓ Sync完成: ${created} erstellt, ${updated} aktualisiert, ${disabled} deaktiviert`, true);
      
      // Reload routes list
      loadLLMRoutes();
      loadWorkerAIStatus();
    } else {
      showWaiMsg('Fehler: ' + (d.error || 'Unbekannt'), false);
    }
  } catch(e){
    showWaiMsg('Fehler: ' + e.message, false);
  }
  
  btn.disabled = false;
  btn.innerHTML = '🔄 Worker AI synchronisieren';
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
    <div class="card-header" onclick="toggleLLMCard('${r.id}')">
      <span class="card-title">${esc(r.provider||'')} / ${esc(r.modelName||r.modelId||'')}</span>
      <span class="badge ${r.disabled?'off':'on'}">${r.disabled?'Deaktiviert':'Aktiv'}</span>
      <span class="chevron">▼</span>
    </div>
    <div class="card-body" id="lrbody_${r.id}">
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Provider</label><div>${esc(r.provider||'')}</div></div>
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Credits/Unit (€)</label>
          <div class="form-group" style="margin:4px 0 0 0">
            <input type="number" step="0.001" min="0" id="lcpu_${r.id}" value="${r.creditsPerUnit||0.001}" style="width:100%;background:#0d1117;border:1px solid var(--border);border-radius:4px;color:var(--text);padding:4px 8px;font-size:14px"/>
          </div>
        </div>
        <div><label style="color:var(--muted);font-size:11px;text-transform:uppercase">Priorität</label>
          <div class="form-group" style="margin:4px 0 0 0">
            <input type="number" step="1" min="0" id="lprio_${r.id}" value="${r.priority||0}" style="width:100%;background:#0d1117;border:1px solid var(--border);border-radius:4px;color:var(--text);padding:4px 8px;font-size:14px"/>
          </div>
        </div>
      </div>
      <div class="toggle-row">
        <span class="toggle-label">Route aktivieren</span>
        <label class="toggle">
          <input type="checkbox" id="ltog_${r.id}" ${r.disabled?'':'checked'} onchange="toggleLLM('${r.id}',!this.checked)"/>
          <span class="slider"></span>
        </label>
      </div>
      <div class="btn-row">
        <button class="btn btn-primary" onclick="saveLLMCost('${r.id}')">Kosten speichern</button>
        <button class="btn btn-ghost" onclick="healthcheckLLM('${r.id}')" id="hcbtn_${r.id}">🔍 Healthcheck</button>
        <span id="hcstatus_${r.id}" style="margin-left:12px;font-size:13px"></span>
      </div>
      <div class="msg" id="lmsg_${r.id}"></div>
    </div>
  </div>`).join('');
}

function toggleLLMCard(id){
  document.getElementById('lr_'+id).classList.toggle('open');
}

async function toggleLLM(rid, disabled){
  await fetch(BASE+'/api/admin/llm/routes/'+rid,{method:'PATCH',headers:hdr(),body:JSON.stringify({disabled})});
  loadLLMRoutes();
}

async function saveLLMCost(rid){
  const cpu = parseFloat(document.getElementById('lcpu_'+rid).value)||0.001;
  const prio = parseInt(document.getElementById('lprio_'+rid).value)||0;
  const r = await fetch(BASE+'/api/admin/llm/routes/'+rid,{
    method:'PATCH',headers:hdr(),body:JSON.stringify({creditsPerUnit:cpu,priority:prio})
  });
  showLLMMsg(rid, r.ok, r.ok?'Kosten gespeichert ✓':'Fehler beim Speichern');
}

function showLLMMsg(rid, ok, text){
  const el = document.getElementById('lmsg_'+rid);
  if(!el) return;
  el.textContent=text; el.className='msg '+(ok?'ok':'err'); el.style.display='block';
  setTimeout(()=>{ el.style.display='none'; },3000);
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
    const [launcherRes, toolchainRes] = await Promise.all([
      fetch(BASE+'/api/admin/launcher/tools',{headers:hdr()}),
      fetch(BASE+'/api/admin/toolchain/tools',{headers:hdr()}).catch(()=>null)
    ]);
    const launcherData = await launcherRes.json();
    let toolchainData = null;
    if (toolchainRes && toolchainRes.ok) {
      toolchainData = await toolchainRes.json();
    }
    renderTools(launcherData, toolchainData);
  } catch(e){ el.innerHTML='<div style="color:var(--danger)">Fehler: '+e.message+'</div>'; }
}
function renderTools(launcherData, toolchainData){
  const el = document.getElementById('toolsList');
  const parts = [];
  
  // Render Launcher Tools
  if (launcherData && launcherData.tools && launcherData.tools.length) {
    parts.push('<h3 style="font-size:13px;color:var(--accent);margin:0 0 12px;font-weight:700;">Launcher Tools</h3>');
    launcherData.tools.forEach(t => {
      const badges = [];
      if (t.badge) badges.push('<span class="badge on">'+esc(t.badge)+'</span>');
      parts.push('<div class="card" id="tr_'+t.id+'">'+
        '<div class="card-header">'+
          '<span class="card-title">'+esc(t.label||'')+'</span>'+
          badges.join('')+
          '<span class="badge '+(t.disabled?'off':'on')+'">'+(t.disabled?'Deaktiviert':'Aktiv')+'</span>'+
        '</div>'+
        '<div class="card-body">'+
          '<div class="toggle-row">'+
            '<span class="toggle-label">Tool aktivieren</span>'+
            '<label class="toggle">'+
              '<input type="checkbox" id="ttog_'+t.id+'" '+(t.disabled?'':'checked')+' onchange="toggleTool(\''+t.id+'\',!this.checked)"/>'+
              '<span class="slider"></span>'+
            '</label>'+
          '</div>'+
          '<div style="margin-top:12px">'+
            '<button class="btn btn-ghost" onclick="healthcheckTool(\''+t.id+'\')" id="thcbtn_'+t.id+'">🔍 Healthcheck</button>'+
            '<span id="thcstatus_'+t.id+'" style="margin-left:12px;font-size:13px"></span>'+
          '</div>'+
        '</div>'+
      '</div>');
    });
  }
  
  // Render Toolchain Tools
  if (toolchainData && toolchainData.tools && toolchainData.tools.length) {
    parts.push('<h3 style="font-size:13px;color:var(--accent);margin:16px 0 12px;font-weight:700;">Toolchain Tools</h3>');
    toolchainData.tools.forEach(t => {
      const badges = [];
      if (t.writeAction) badges.push('<span class="badge" style="background:var(--warn)20;color:var(--warn);border-color:var(--warn)40">WRITE</span>');
      if (t.requiresConfirm) badges.push('<span class="badge" style="background:#3b82f620;color:#3b82f6;border-color:#3b82f640">CONFIRM</span>');
      parts.push('<div class="card" id="tct_'+t.id+'">'+
        '<div class="card-header">'+
          '<span class="card-title">'+esc(t.name||'')+'</span>'+
          '<span class="badge '+(t.enabled?'on':'off')+'">'+(t.enabled?'Aktiv':'Deaktiviert')+'</span>'+
          badges.join('')+
        '</div>'+
        '<div class="card-body">'+
          '<div style="font-size:12px;color:var(--textSub);margin-bottom:8px">'+esc(t.description||'Keine Beschreibung')+'</div>'+
          '<div class="toggle-row">'+
            '<span class="toggle-label">Tool aktivieren</span>'+
            '<label class="toggle">'+
              '<input type="checkbox" id="tctog_'+t.id+'" '+(t.enabled?'':'checked')+' onchange="toggleToolchainTool(\''+t.id+'\',!this.checked)"/>'+
              '<span class="slider"></span>'+
            '</label>'+
          '</div>'+
        '</div>'+
      '</div>');
    });
  }
  
  if (!parts.length) {
    el.innerHTML='<div style="color:var(--muted);font-size:14px">Keine Tools konfiguriert.</div>';
    return;
  }
  el.innerHTML=parts.join('');
}
async function toggleToolchainTool(tid, enabled){
  try {
    await fetch(BASE+'/api/admin/toolchain/tools/'+tid,{method:'PATCH',headers:hdr(),body:JSON.stringify({enabled})});
    loadTools();
  } catch(e){ alert('Fehler: '+e.message); }
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



# Register modular knowledge and account-security contracts only after the
# existing session-cookie and require_session helpers are available.
register_knowledge_routes(
    app,
    require_session=require_session,
    get_connection=get_agent_runtime_connection,
)
register_admin_knowledge_routes(
    app,
    require_admin=require_admin,
    get_connection=get_agent_runtime_connection,
    get_admin_user_id=get_current_admin_user_id,
)
register_security_routes(
    app,
    require_session=require_session,
    get_connection=get_agent_runtime_connection,
    set_session_cookie=_set_session_cookie,
)
register_are_inference_routes(
    app,
    require_session=require_session,
    get_connection=get_agent_runtime_connection,
)

# ── GitHub App Marketplace Integration ────────────────────────────────────────
if HAS_GITHUB_APP and register_github_app_routes:
    try:
        register_github_app_routes(
            app,
            require_admin=require_admin,
            get_connection=get_connection,
        )
        print("✓ GitHub App routes registered")
    except Exception as e:
        print(f"⚠ GitHub App routes registration failed: {e}")

# ── Embedded Sovereign Universal Toolchain ────────────────────────────────────
# Safe diagnosis runs inside this Flask/PostgreSQL runtime. Execution stays in
# Sovereign Agent jobs and their Draft-PR evidence gates. No second service.
# ─────────────────────────────────────────────────────────────────────────────

from agent_runtime.universal_toolchain import (
    dispatch_embedded_tool,
    toolchain_briefing,
    toolchain_manifest,
)


def _utc_request(method: str, path: str, body=None):
    """Removed compatibility shim: the universal toolchain is embedded."""
    raise RuntimeError("External universal toolchain proxy was removed; use embedded tools")
    import urllib.request as _ur
    import urllib.error   as _ue
    if not _UTOOLCHAIN_BASE:
        raise RuntimeError("TOOLCHAIN_BASE_URL is not configured")
    url = f"{_UTOOLCHAIN_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if _TOOLCHAIN_KEY:
        headers["X-Toolchain-Key"] = _TOOLCHAIN_KEY
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
    """Public health contract for the embedded policy-guarded toolchain."""
    manifest = toolchain_manifest()
    return jsonify({
        "ok": True,
        "name": manifest["name"],
        "version": manifest["version"],
        "runtime": manifest["runtime"],
        "toolCount": len(manifest["tools"]),
        "proxyVia": None,
        "policy": manifest["policy"],
    })


@app.route("/api/toolchain/universal/manifest")
def utc_manifest():
    """Return the embedded manifest plus enabled read-only custom tools."""
    manifest = toolchain_manifest()
    all_tools = list(manifest["tools"])
    try:
        db_tools = query(
            """SELECT name, description, input_schema, requires_confirm
               FROM toolchain_tools
               WHERE enabled = true AND write_action = false
               ORDER BY sort_order ASC"""
        )
        known = {str(item.get("name") or "") for item in all_tools}
        for tool in db_tools or []:
            if tool["name"] not in known:
                all_tools.append({
                    "name": tool["name"],
                    "description": tool["description"] or "",
                    "input_schema": tool["input_schema"] or {},
                    "write_action": False,
                    "requires_confirm": bool(tool["requires_confirm"]),
                    "runtime": "database-manifest-only",
                })
    except Exception:
        pass
    return jsonify({
        **manifest,
        "tools": all_tools,
        "sources": {
            "embedded": "agent_runtime.universal_toolchain",
            "database": "read-only toolchain_tools",
        },
    })


@app.route("/api/toolchain/universal/briefing")
def utc_briefing():
    """Return the embedded toolchain briefing for LLM and no-code clients."""
    return jsonify(toolchain_briefing())


@app.route("/api/toolchain/universal/invoke", methods=["POST"])
@require_session
def utc_invoke():
    """Invoke only embedded read-only tools; execution uses the agent handoff route."""
    body = request.get_json(force=True) or {}
    tool = str(body.get("tool") or "").strip()
    args = body.get("args") if isinstance(body.get("args"), dict) else {}
    if not tool:
        return jsonify({"error": "tool name erforderlich"}), 400
    try:
        result = dispatch_embedded_tool(tool, args)
        _tc_audit(
            request.session_user_id,
            f"universal_invoke_{tool}",
            {"tool": tool, "argsKeys": sorted(args.keys()), "writeAction": False},
        )
        return jsonify({"ok": True, "result": result, "runtime": "embedded"})
    except KeyError as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
            "blocker": "embedded_tool_not_allowed",
            "hint": "Use /api/user/agent/toolchain/handoff for execution and Draft-PR workflows.",
        }), 403
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


# ═════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════
# NOTE: This must be at the END of the file!
# Routes defined after this block will NOT be registered when running directly.
# For production, use gunicorn: gunicorn -w 4 -b 0.0.0.0:8787 app:app

# =============================================================================
# CLOUDFLARE AI GATEWAY AUTO-INTEGRATION
# =============================================================================

AI_GATEWAY_ID = os.getenv("AI_GATEWAY_ID", "gatter")
AI_GATEWAY_ACCOUNT = os.getenv("AI_GATEWAY_ACCOUNT", "4a82319180f1f1cee60d85a971c3041d")
AI_GATEWAY_BASE = f"https://gateway.ai.cloudflare.com/v1/{AI_GATEWAY_ACCOUNT}/{AI_GATEWAY_ID}"
AI_GATEWAY_TIMEOUT = 30

def _gateway_headers(include_auth: bool = True) -> dict:
    headers = {"Content-Type": "application/json"}
    if include_auth:
        token = os.getenv("AI_GATEWAY_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers

def fetch_ai_gateway(path: str, method: str = "GET", json_data: dict = None, provider: str = None) -> tuple:
    if provider:
        url = f"{AI_GATEWAY_BASE}/providers/{provider}{path}"
    else:
        url = f"{AI_GATEWAY_BASE}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, headers=_gateway_headers(), timeout=AI_GATEWAY_TIMEOUT)
        elif method == "POST":
            resp = requests.post(url, headers=_gateway_headers(), json=json_data, timeout=AI_GATEWAY_TIMEOUT)
        else:
            return None, f"Unsupported method: {method}"
        return resp, ""
    except requests.exceptions.Timeout:
        return None, f"AI Gateway request timed out after {AI_GATEWAY_TIMEOUT}s"
    except requests.exceptions.ConnectionError as e:
        return None, f"Cannot connect to AI Gateway: {e}"
    except Exception as e:
        return None, f"AI Gateway request failed: {e}"

def test_provider_key(provider: str) -> tuple:
    resp, err = fetch_ai_gateway(f"/{provider}/v1/models", provider=provider)
    if err:
        return False, err, []
    if resp.status_code == 401:
        return False, f"No {provider} key configured", []
    if resp.status_code == 403:
        return False, f"{provider} key invalid", []
    if resp.status_code == 404:
        return False, f"{provider} provider not found", []
    if not resp.ok:
        return False, f"{provider} error: HTTP {resp.status_code}", []
    try:
        data = resp.json()
        models = data.get("data", []) if isinstance(data, dict) else []
        return True, "", models
    except:
        return True, "", []

    if resp.status_code and resp.status_code < 500:
        return True, f"{provider} available", model_info["models"]
    return False, f"{provider} error: HTTP {resp.status_code}", []

@app.route("/api/admin/llm/gateway/providers", methods=["GET"])
@require_admin
def admin_llm_gateway_providers():
    results = []
    for provider_id, info in PROVIDER_MODELS.items():
        available, message, models = test_provider_available(provider_id)
        results.append({
            "provider": provider_id,
            "name": info["name"],
            "configured": available,
            "status": message,
            "models": models if available else info["models"],
            "defaultModel": info["default"] if available else None,
        })
    results.append({
        "provider": "cloudflare",
        "name": "Cloudflare Worker AI",
        "configured": True,
        "status": "Always available (free)",
        "models": [],
        "defaultModel": "@cf/meta/llama-3.1-8b-instruct"
    })
    return jsonify({"ok": True, "providers": results, "gatewayUrl": AI_GATEWAY_BASE})

@app.route("/api/admin/llm/gateway/sync", methods=["POST"])
@require_admin
def admin_llm_gateway_sync():
    try:
        results = {"providers": {}, "workerAiSync": None, "errors": []}
        for provider_id, info in PROVIDER_MODELS.items():
            available, message, _ = test_provider_available(provider_id)
            if not available:
                results["providers"][provider_id] = {"configured": False, "status": message, "created": 0, "updated": 0}
                continue
            created, updated = 0, 0
            for model in info["models"]:
                full_model_id = info["format"].format(model=model)
                existing = query("SELECT id::text FROM llm_routes WHERE model_id = %s", (full_model_id,), one=True)
                priority = 50
                if any(x in model.lower() for x in ["mini", "lite", "haiku", "flash"]):
                    priority = 10
                elif any(x in model.lower() for x in ["large", "ultra", "opus", "pro"]):
                    priority = 100
                try:
                    if existing:
                        query("UPDATE llm_routes SET model_name = %s, base_url = %s, priority = %s, disabled = false, updated_at = NOW() WHERE model_id = %s",
                              (model, AI_GATEWAY_BASE, priority, full_model_id), write=True)
                        updated += 1
                    else:
                        query("INSERT INTO llm_routes (id, model_id, model_name, provider, base_url, credits_per_unit, priority, disabled) VALUES (gen_random_uuid(), %s, %s, %s, %s, 0.01, %s, false)",
                              (full_model_id, model, provider_id, AI_GATEWAY_BASE, priority), write=True)
                        created += 1
                except Exception as e:
                    results["errors"].append(f"{full_model_id}: {str(e)}")
            results["providers"][provider_id] = {"configured": True, "status": message, "modelCount": len(info["models"]), "created": created, "updated": updated}
        try:
            resp, err = fetch_worker_ai("v1/models")
            if not err and resp and resp.ok:
                worker_models = resp.json().get("data", [])
                w_c, w_u = 0, 0
                for wm in worker_models:
                    mid = wm.get("id", "")
                    if not mid: continue
                    existing = query("SELECT id::text FROM llm_routes WHERE model_id = %s", (mid,), one=True)
                    p = 50
                    if "70b" in mid or "32b" in mid: p = 100
                    elif "7b" in mid: p = 25
                    try:
                        if existing:
                            query("UPDATE llm_routes SET model_name = %s, base_url = %s, priority = %s, disabled = false, updated_at = NOW() WHERE model_id = %s",
                                  (mid, WORKER_AI_BASE, p, mid), write=True)
                            w_u += 1
                        else:
                            query("INSERT INTO llm_routes (id, model_id, model_name, provider, base_url, credits_per_unit, priority, disabled) VALUES (gen_random_uuid(), %s, %s, 'cloudflare', %s, 0.001, %s, false)",
                                  (mid, mid, WORKER_AI_BASE, p), write=True)
                            w_c += 1
                    except: pass
                results["workerAiSync"] = {"ok": True, "totalModels": len(worker_models), "created": w_c, "updated": w_u}
        except Exception as e:
            results["workerAiSync"] = {"ok": False, "error": str(e)}
        audit("admin_llm_gateway_sync", None, results)
        return jsonify({"ok": True, "results": results, "message": "AI Gateway sync completed."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _worker_route_fields(model_id: str) -> tuple[str, int]:
    """Derive deterministic display and priority fields from one real Worker model id."""
    normalized = str(model_id or "").strip()
    friendly_name = normalized
    if normalized.startswith("@cf/"):
        parts = normalized.replace("@cf/", "", 1).split("/")
        if len(parts) >= 2:
            friendly_name = f"{parts[0]}-{parts[1]}"
    lowered = normalized.lower()
    priority = 100 if ("32b" in lowered or "70b" in lowered) else 25 if "7b" in lowered else 50
    return friendly_name, priority


def _reconcile_worker_routes_if_empty() -> tuple[int, str]:
    """Restore an empty route catalog only from the live Worker model source."""
    current = query("SELECT COUNT(*)::integer AS count FROM llm_routes WHERE disabled = false", one=True)
    current_count = int((current or {}).get("count") or 0)
    if current_count > 0:
        return current_count, ""

    response, error = fetch_worker_ai("v1/models")
    if error:
        return 0, error
    if response is None or not response.ok:
        status_code = getattr(response, "status_code", "unknown")
        return 0, f"Worker AI models HTTP {status_code}"

    payload = response.json() if response.content else {}
    worker_models = payload.get("data", []) if isinstance(payload, dict) else []
    model_ids = sorted({
        str(model.get("id") or "").strip()
        for model in worker_models
        if isinstance(model, dict) and str(model.get("id") or "").strip()
    })
    if not model_ids:
        return 0, "Worker AI lieferte keine Modelle"

    for model_id in model_ids:
        friendly_name, priority = _worker_route_fields(model_id)
        query(
            """INSERT INTO llm_routes
                   (id, model_id, model_name, provider, base_url,
                    credits_per_unit, priority, disabled)
               VALUES (gen_random_uuid()::text, %s, %s, 'cloudflare', %s, 0.001, %s, false)
               ON CONFLICT (model_id) DO UPDATE SET
                   model_name = EXCLUDED.model_name,
                   provider = EXCLUDED.provider,
                   base_url = EXCLUDED.base_url,
                   credits_per_unit = EXCLUDED.credits_per_unit,
                   priority = EXCLUDED.priority,
                   disabled = false,
                   updated_at = NOW()""",
            (model_id, friendly_name, WORKER_AI_BASE, priority),
            write=True,
        )

    restored = query("SELECT COUNT(*)::integer AS count FROM llm_routes WHERE disabled = false", one=True)
    restored_count = int((restored or {}).get("count") or 0)
    if restored_count == 0:
        return 0, "Worker-Routen konnten nicht persistent rekonstruiert werden"
    audit("system_worker_ai_route_reconcile", None, {
        "reason": "empty_route_catalog",
        "restored": restored_count,
        "workerModels": len(model_ids),
    })
    return restored_count, ""


@app.route("/api/llm/auto-route", methods=["POST"])
@require_session
def public_llm_auto_route():
    user_id = request.session_user_id
    try:
        _read_verified_credit_balance(user_id)
    except LookupError:
        return jsonify({"error": "User nicht gefunden"}), 404
    except CreditStateConflict as exc:
        return jsonify({
            "error": str(exc),
            "blocker": "credit_state_verification_failed",
            "creditStateVerified": False,
        }), 409
    except Exception as exc:
        return jsonify({"error": str(exc), "runtimeState": "failed"}), 500

    try:
        routes = query("SELECT id::text, model_id, model_name, provider, base_url, credits_per_unit, priority FROM llm_routes WHERE disabled = false ORDER BY priority ASC, credits_per_unit ASC LIMIT 20")
        if not routes:
            _restored_count, reconcile_error = _reconcile_worker_routes_if_empty()
            if reconcile_error:
                return jsonify({
                    "error": "Keine LLM Routes verfuegbar",
                    "blocker": "llm_routes_empty",
                    "cause": reconcile_error,
                    "suggestion": "Worker-Modellquelle und Datenbank-Persistenz prüfen",
                }), 503
            routes = query("SELECT id::text, model_id, model_name, provider, base_url, credits_per_unit, priority FROM llm_routes WHERE disabled = false ORDER BY priority ASC, credits_per_unit ASC LIMIT 20")
        if not routes:
            return jsonify({
                "error": "Keine LLM Routes verfuegbar",
                "blocker": "llm_routes_empty_after_reconcile",
            }), 503
        selected = routes[0]
        provider = selected.get("provider", "")
        if provider == "cloudflare":
            return jsonify({"ok": True, "selected": {"modelId": selected["model_id"], "modelName": selected["model_name"], "provider": provider, "baseUrl": selected["base_url"], "creditsPerUnit": float(selected["credits_per_unit"]), "routeType": "worker-ai"}, "fallback": [r for r in routes[1:5]] if len(routes) > 1 else [], "message": f"Worker AI: {selected['model_name']}"})
        if provider in PROVIDER_MODELS:
            available, _, _ = test_provider_available(provider)
            if available:
                return jsonify({"ok": True, "selected": {"modelId": selected["model_id"], "modelName": selected["model_name"], "provider": provider, "baseUrl": selected["base_url"], "creditsPerUnit": float(selected["credits_per_unit"]), "routeType": "gateway"}, "fallback": [r for r in routes[1:3]] if len(routes) > 1 else [], "message": f"AI Gateway: {selected['model_name']}"})
        worker_routes = [r for r in routes if r.get("provider") == "cloudflare"]
        if worker_routes:
            return jsonify({"ok": True, "selected": {"modelId": worker_routes[0]["model_id"], "modelName": worker_routes[0]["model_name"], "provider": "cloudflare", "baseUrl": worker_routes[0]["base_url"], "creditsPerUnit": float(worker_routes[0]["credits_per_unit"]), "routeType": "worker-ai-fallback"}, "fallback": [], "message": "Fallback to Worker AI"})
        return jsonify({"error": "Keine Route verfuegbar"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/llm/chat", methods=["POST"])
@require_session
def public_llm_chat():
    try:
        body = request.get_json(force=True) or {}
        model = body.get("model", "")
        messages = body.get("messages", [])
        max_tokens = body.get("max_tokens", 1000)
        if not messages:
            return jsonify({"error": "messages required"}), 400
        if model.startswith("@cf/"):
            resp, err = fetch_worker_ai("v1/chat/completions", method="POST", json_data={"model": model, "messages": messages, "max_tokens": max_tokens})
            if err: return jsonify({"error": err}), 500
            if not resp.ok: return jsonify({"error": resp.text}), resp.status_code
            return jsonify(resp.json())
        if "/" in model:
            parts = model.split("/", 1)
            provider, model_name = parts[0], parts[1]
            resp, err = fetch_ai_gateway("/compat/v1/chat/completions", method="POST", json_data={"model": model_name, "messages": messages, "max_tokens": max_tokens}, provider=provider)
            if err: return jsonify({"error": err}), 500
            if not resp.ok: return jsonify({"error": resp.text}), resp.status_code
            return jsonify(resp.json())
        return jsonify({"error": f"Unbekanntes Model: {model}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Validate required tables exist before starting
    try:
        query("SELECT 1", one=True)
    except Exception as e:
        print(f"[WARN] Database connection failed: {e}")
        print("[WARN] Starting anyway - routes may fail if DB is required.")
    
    app.run(host="0.0.0.0", port=8787, debug=False)
