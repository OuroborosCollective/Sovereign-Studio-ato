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
from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
import requests

app = Flask(__name__)

DEFAULT_CORS_ORIGINS = (
    "https://sovereign-backend.arelorian.de",
    "https://sovereign-studio.arelorian.de",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8787",
    "capacitor://localhost",
)

def _parse_cors_origins(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return list(DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]

CORS_ORIGINS = _parse_cors_origins(os.getenv("CORS_ORIGINS"))
CORS(app, origins=CORS_ORIGINS, supports_credentials=True)

# ── Config ────────────────────────────────────────────────────────────────────

ADMIN_API_KEY  = os.getenv("ADMIN_API_KEY", "")
LLM_PROXY_KEY  = os.getenv("LLM_PROXY_KEY", "")
OPENHANDS_API_URL = os.getenv("OPENHANDS_API_URL", "http://127.0.0.1:3000")

POSTGRES_HOST  = os.getenv("POSTGRES_HOST", "host.docker.internal")
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

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Fail-closed: if ADMIN_API_KEY is unset/empty, always deny.
        if not ADMIN_API_KEY:
            return jsonify({"error": "Admin-Schlüssel nicht konfiguriert"}), 503
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if not token or token != ADMIN_API_KEY:
            return jsonify({"error": "Nicht autorisiert"}), 401
        return f(*args, **kwargs)
    return decorated


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
    auth = request.headers.get("Authorization", "")
    key  = auth[7:] if auth.startswith("Bearer ") else ""
    admin = query(
        "SELECT id, email FROM admin_users WHERE role IN ('admin','superadmin') LIMIT 1",
        one=True,
    )
    admin_id    = str(admin["id"])    if admin else "system"
    admin_email = admin["email"]       if admin else "system"
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
    allowed = {"role", "credits", "subscriptionStatus", "isBanned"}
    col_map = {
        "role":               "role",
        "credits":            "credits",
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
    body   = request.get_json(force=True) or {}
    amount = body.get("amount", 0)
    reason = body.get("reason", "")
    if not amount:
        return jsonify({"error": "amount darf nicht 0 sein"}), 400
    if not reason:
        return jsonify({"error": "reason fehlt"}), 400

    query(
        "UPDATE admin_users SET credits = GREATEST(0, credits + %s) WHERE id = %s::uuid",
        (amount, uid), write=True,
    )
    user = query(
        "SELECT email FROM admin_users WHERE id = %s::uuid",
        (uid,), one=True,
    )
    if user:
        sign = "+" if amount > 0 else ""
        desc = "Admin Credit-Anpassung: " + sign + str(amount) + " (" + reason + ")"
        query(
            """INSERT INTO transactions
                  (user_id, user_email, type, amount, currency, status, description)
               VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)""",
            (uid, user["email"], "adjustment", 0, "EUR", "completed", desc),
            write=True,
        )
    audit("admin_credit_adjustment", uid, {"amount": amount, "reason": reason})
    return jsonify({"ok": True})


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8787, debug=False)


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
    user_id = _get_session_user_id() or ""
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
    user_id    = _get_session_user_id() or ""
    if not user_id:
        return jsonify({"error": "Bitte einloggen"}), 401
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
    user_id  = _get_session_user_id() or ""
    if not user_id:
        return jsonify({"error": "Bitte einloggen"}), 401
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
        if uid != user_id:
            return jsonify({"error": "Order gehört nicht zur aktuellen Session"}), 403

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
    user_id    = _get_session_user_id() or ""
    if not user_id:
        return jsonify({"error": "Bitte einloggen"}), 401
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
    user_id    = _get_session_user_id() or ""
    if not user_id:
        return jsonify({"error": "Bitte einloggen"}), 401

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
    user_id        = _get_session_user_id() or ""
    if not user_id:
        return jsonify({"error": "Bitte einloggen"}), 401

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
    """Return credit balance for the authenticated session user."""
    user_id = _get_session_user_id() or ""
    if not user_id:
        return jsonify({"credits": 0, "authenticated": False}), 200
    try:
        row = query(
            "SELECT credits FROM admin_users WHERE id = %s::uuid LIMIT 1",
            (user_id,), one=True,
        )
        credits = int(row["credits"]) if row else 0
        return jsonify({"credits": credits, "authenticated": True})
    except Exception as exc:
        return jsonify({"credits": 0, "error": str(exc)}), 500


@app.route("/api/billing/deduct", methods=["POST"])
def user_billing_deduct():
    """Server-side credit deduction with validation and usage logging."""
    body        = request.get_json(force=True) or {}
    user_id     = _get_session_user_id() or ""
    cost_id     = str(body.get("costId",    ""))
    amount      = int(body.get("amount",    0))
    token_count = int(body.get("tokenCount", 0))

    if amount <= 0:
        return jsonify({"ok": True, "deducted": 0})
    if not user_id:
        return jsonify({"error": "Bitte einloggen"}), 401

    try:
        row = query(
            "SELECT credits FROM admin_users WHERE id = %s::uuid LIMIT 1",
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
            "UPDATE admin_users SET credits = GREATEST(0, credits - %s) WHERE id = %s::uuid",
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


def _session_secret_ready() -> bool:
    """Production auth must fail closed when SESSION_SECRET is missing or weak."""
    return len(SESSION_SECRET.strip()) >= 32


def _session_secret_error():
    return jsonify({"error": "SESSION_SECRET nicht konfiguriert"}), 503


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

