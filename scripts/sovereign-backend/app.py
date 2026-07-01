#!/usr/bin/env python3
"""
Sovereign Backend — Flask app.
Serves OpenHands proxy routes + Admin API routes.

Issue #460: Admin API (psycopg2, real DB)
"""
from __future__ import annotations

import base64
import hashlib
import os
import threading
import time
import urllib.parse
import uuid
from functools import wraps

import psycopg2
import psycopg2.extras
import psycopg2.pool
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app, origins="*")

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

