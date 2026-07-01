#!/usr/bin/env python3
"""
Sovereign Backend — Flask app.
Serves OpenHands proxy routes + Admin API routes.

Issue #460: Admin API (psycopg2, real DB)
"""
from __future__ import annotations

import os
import threading
import time
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
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != ADMIN_API_KEY:
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
    task = body.get("task", "")
    if not task:
        return jsonify({"error": "task required"}), 400

    job_id = str(uuid.uuid4())
    oh_conv_id = None

    try:
        resp = requests.post(
            f"{OPENHANDS_API_URL}/api/conversations",
            headers=oh_headers(),
            json={"initial_message": task, "runtime_image": "docker.all-hands.ai/all-hands-ai/runtime:0.39-nikolaik"},
            timeout=30,
        )
        if resp.ok:
            oh_conv_id = resp.json().get("conversation_id")
    except Exception as exc:
        pass

    job = {
        "id": job_id,
        "status": "running",
        "task": task,
        "ohConvId": oh_conv_id,
        "events": [{
            "at": int(time.time()), "level": "info",
            "stage": "init", "message": "Job gestartet",
        }],
        "result": None,
        "createdAt": int(time.time()),
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
