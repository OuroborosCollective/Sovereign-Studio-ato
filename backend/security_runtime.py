"""Passkeys, recovery/account keys and one-time step-up approvals.

Passkeys use WebAuthn public-key verification. Account keys are random secrets
shown once and stored only as server-peppered HMAC hashes. Step-up approvals are
bound to one action and one canonical context, expire quickly and are consumed
exactly once.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from typing import Any, Callable
import uuid

from flask import jsonify, make_response, request
import psycopg2.extras

from security_oauth import _check_rate_limit

ConnectionFactory = Callable[[], Any]

PASSKEY_RP_ID = os.getenv("PASSKEY_RP_ID", "arelorian.de").strip()
PASSKEY_RP_NAME = os.getenv("PASSKEY_RP_NAME", "Sovereign Studio").strip()
_configured_passkey_origins = os.getenv(
    "PASSKEY_ALLOWED_ORIGINS",
    "https://chat.arelorian.de,https://arelorian.de",
).split(",")
_capacitor_passkey_origin = os.getenv("CAPACITOR_PASSKEY_ORIGIN", "").strip()
if _capacitor_passkey_origin:
    _configured_passkey_origins.append(_capacitor_passkey_origin)
PASSKEY_ALLOWED_ORIGINS = tuple(
    origin.strip().rstrip("/")
    for origin in _configured_passkey_origins
    if origin.strip()
)
CHALLENGE_TTL_SECONDS = 300
STEP_UP_TTL_SECONDS = 300


class SecurityRuntimeUnavailable(RuntimeError):
    pass


def _webauthn():
    try:
        from webauthn import (
            base64url_to_bytes,
            generate_authentication_options,
            generate_registration_options,
            options_to_json,
            verify_authentication_response,
            verify_registration_response,
        )
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria,
            PublicKeyCredentialDescriptor,
            ResidentKeyRequirement,
            UserVerificationRequirement,
        )
    except ImportError as exc:
        raise SecurityRuntimeUnavailable(
            "Passkey backend dependency 'webauthn' is not installed"
        ) from exc
    return {
        "base64url_to_bytes": base64url_to_bytes,
        "generate_authentication_options": generate_authentication_options,
        "generate_registration_options": generate_registration_options,
        "options_to_json": options_to_json,
        "verify_authentication_response": verify_authentication_response,
        "verify_registration_response": verify_registration_response,
        "AuthenticatorSelectionCriteria": AuthenticatorSelectionCriteria,
        "PublicKeyCredentialDescriptor": PublicKeyCredentialDescriptor,
        "ResidentKeyRequirement": ResidentKeyRequirement,
        "UserVerificationRequirement": UserVerificationRequirement,
    }


def _close(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _pepper() -> bytes:
    value = (
        os.getenv("ACCOUNT_KEY_PEPPER", "").strip()
        or os.getenv("JWT_SECRET", "").strip()
    )
    if not value:
        raise SecurityRuntimeUnavailable("ACCOUNT_KEY_PEPPER or JWT_SECRET is required")
    return value.encode("utf-8")


def _secret_hash(value: str) -> str:
    return hmac.new(_pepper(), value.encode("utf-8"), hashlib.sha256).hexdigest()


def canonical_context_hash(action: str, context: Any) -> str:
    payload = json.dumps(
        {"action": str(action or "").strip(), "context": context or {}},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _request_origin() -> str:
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    if origin and origin in PASSKEY_ALLOWED_ORIGINS:
        return origin
    if not origin and PASSKEY_ALLOWED_ORIGINS:
        return PASSKEY_ALLOWED_ORIGINS[0]
    raise ValueError("Request origin is not allowed for passkeys")


def _rp_id_for_origin(origin: str) -> str:
    capacitor_origin = os.getenv("CAPACITOR_PASSKEY_ORIGIN", "").strip().rstrip("/")
    if capacitor_origin and origin == capacitor_origin:
        capacitor_rp_id = os.getenv("CAPACITOR_PASSKEY_RP_ID", "").strip()
        if not capacitor_rp_id:
            raise SecurityRuntimeUnavailable(
                "CAPACITOR_PASSKEY_RP_ID is required for the configured Capacitor origin"
            )
        return capacitor_rp_id
    return PASSKEY_RP_ID


def _user(conn: Any, user_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id::text, email, display_name, role, credits,
                      subscription_status, is_banned, created_at, avatar_url,
                      google_id, github_id, github_username
               FROM admin_users WHERE id=%s::uuid LIMIT 1""",
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _user_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "email": row.get("email"),
        "displayName": row.get("display_name") or "",
        "role": row.get("role") or "user",
        "credits": int(row.get("credits") or 0),
        "subscriptionStatus": row.get("subscription_status") or "free",
        "isBanned": bool(row.get("is_banned")),
        "createdAt": str(row.get("created_at") or ""),
        "avatarUrl": row.get("avatar_url"),
        "googleId": row.get("google_id"),
        "githubId": row.get("github_id"),
        "githubUsername": row.get("github_username"),
    }


def _store_challenge(
    conn: Any,
    *,
    user_id: str | None,
    purpose: str,
    challenge: bytes,
    context: dict[str, Any],
) -> str:
    challenge_id = str(uuid.uuid4())
    context_hash = canonical_context_hash(str(context.get("action") or purpose), context)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO auth_challenges
               (id, user_id, purpose, challenge, context_hash, context, expires_at)
               VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s::jsonb,
                       NOW() + (%s * INTERVAL '1 second'))""",
            (
                challenge_id,
                user_id,
                purpose,
                challenge,
                context_hash,
                json.dumps(context, ensure_ascii=False),
                CHALLENGE_TTL_SECONDS,
            ),
        )
    conn.commit()
    return challenge_id


def _consume_challenge(
    conn: Any,
    *,
    challenge_id: str,
    purpose: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id::text, user_id::text, challenge, context_hash, context
               FROM auth_challenges
               WHERE id=%s::uuid AND purpose=%s
                 AND consumed_at IS NULL AND expires_at > NOW()
               FOR UPDATE""",
            (challenge_id, purpose),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Security challenge is invalid, expired or already used")
        if user_id and str(row.get("user_id") or "") not in {"", user_id}:
            raise ValueError("Security challenge belongs to another user")
        cur.execute(
            "UPDATE auth_challenges SET consumed_at=NOW() WHERE id=%s::uuid",
            (challenge_id,),
        )
    conn.commit()
    return dict(row)


def _passkeys(conn: Any, user_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id::text, credential_id, credential_public_key, sign_count,
                      transports, device_type, backed_up, label,
                      to_char(created_at,'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "createdAt",
                      to_char(last_used_at,'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "lastUsedAt"
               FROM user_passkeys WHERE user_id=%s::uuid
               ORDER BY created_at DESC""",
            (user_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def _public_passkey(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "label": row.get("label") or "Passkey",
        "transports": list(row.get("transports") or []),
        "deviceType": row.get("device_type"),
        "backedUp": bool(row.get("backed_up")),
        "createdAt": row.get("createdAt"),
        "lastUsedAt": row.get("lastUsedAt"),
    }


def _policy(conn: Any, user_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO user_security_policies (user_id)
               VALUES (%s::uuid) ON CONFLICT (user_id) DO NOTHING""",
            (user_id,),
        )
        cur.execute(
            """SELECT require_purchase_step_up AS "requirePurchaseStepUp",
                      purchase_threshold_eur::float AS "purchaseThresholdEur",
                      require_expensive_route_step_up AS "requireExpensiveRouteStepUp",
                      route_threshold_credits AS "routeThresholdCredits",
                      prefer_passkey AS "preferPasskey"
               FROM user_security_policies WHERE user_id=%s::uuid""",
            (user_id,),
        )
        row = cur.fetchone()
    conn.commit()
    return dict(row)


def step_up_requirement(
    conn: Any,
    *,
    user_id: str,
    action: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    policy = _policy(conn, user_id)
    required = False
    if action == "credit_purchase" and policy["requirePurchaseStepUp"]:
        amount = float(context.get("priceEur") or 0)
        required = amount >= float(policy["purchaseThresholdEur"])
    elif action == "expensive_llm_route" and policy["requireExpensiveRouteStepUp"]:
        credits = int(context.get("credits") or 0)
        required = credits >= int(policy["routeThresholdCredits"])
    return {
        "required": required,
        "action": action,
        "context": context,
        "contextHash": canonical_context_hash(action, context),
        "policy": policy,
    }


def consume_step_up_approval(
    get_connection: ConnectionFactory,
    *,
    user_id: str,
    action: str,
    context: dict[str, Any],
    token: str | None,
) -> dict[str, Any]:
    conn = get_connection()
    try:
        requirement = step_up_requirement(
            conn,
            user_id=user_id,
            action=action,
            context=context,
        )
        if not requirement["required"]:
            return {**requirement, "approved": True, "consumed": False}
        if not token:
            return {**requirement, "approved": False, "reason": "step_up_token_missing"}
        token_hash = _secret_hash(token)
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id::text FROM step_up_approvals
                   WHERE user_id=%s::uuid AND action=%s AND context_hash=%s
                     AND token_hash=%s AND consumed_at IS NULL AND expires_at > NOW()
                   FOR UPDATE""",
                (user_id, action, requirement["contextHash"], token_hash),
            )
            approval = cur.fetchone()
            if not approval:
                conn.rollback()
                return {**requirement, "approved": False, "reason": "step_up_token_invalid"}
            cur.execute(
                "UPDATE step_up_approvals SET consumed_at=NOW() WHERE id=%s::uuid",
                (approval["id"],),
            )
        conn.commit()
        return {**requirement, "approved": True, "consumed": True}
    finally:
        _close(conn)


def _create_approval(
    conn: Any,
    *,
    user_id: str,
    action: str,
    context_hash: str,
) -> str:
    raw_token = "sva_" + secrets.token_urlsafe(32)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO step_up_approvals
               (user_id, action, context_hash, token_hash, expires_at)
               VALUES (%s::uuid, %s, %s, %s,
                       NOW() + (%s * INTERVAL '1 second'))""",
            (user_id, action, context_hash, _secret_hash(raw_token), STEP_UP_TTL_SECONDS),
        )
    conn.commit()
    return raw_token


def register_security_routes(
    app: Any,
    *,
    require_session: Callable,
    get_connection: ConnectionFactory,
    set_session_cookie: Callable,
) -> None:
    @app.route("/api/security/overview", methods=["GET"])
    @require_session
    def security_overview():
        conn = get_connection()
        try:
            _webauthn()
            passkeys = [_public_passkey(row) for row in _passkeys(conn, request.session_user_id)]
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id::text, key_hint AS "keyHint", label, scopes,
                              to_char(created_at,'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "createdAt",
                              to_char(last_used_at,'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS "lastUsedAt"
                       FROM user_account_keys
                       WHERE user_id=%s::uuid AND revoked_at IS NULL
                       ORDER BY created_at DESC""",
                    (request.session_user_id,),
                )
                account_keys = [dict(row) for row in cur.fetchall()]
            return jsonify({
                "passkeys": passkeys,
                "accountKeys": account_keys,
                "policy": _policy(conn, request.session_user_id),
                "passkeyAvailable": True,
            })
        except SecurityRuntimeUnavailable as exc:
            return jsonify({"error": str(exc), "passkeyAvailable": False}), 503
        finally:
            _close(conn)

    @app.route("/api/security/policy", methods=["PATCH"])
    @require_session
    def security_policy_update():
        body = request.get_json(force=True) or {}
        allowed = {
            "requirePurchaseStepUp": "require_purchase_step_up",
            "purchaseThresholdEur": "purchase_threshold_eur",
            "requireExpensiveRouteStepUp": "require_expensive_route_step_up",
            "routeThresholdCredits": "route_threshold_credits",
            "preferPasskey": "prefer_passkey",
        }
        sets: list[str] = []
        values: list[Any] = []
        for key, column in allowed.items():
            if key not in body:
                continue
            value = body[key]
            if key == "purchaseThresholdEur":
                value = max(0, min(float(value), 100_000))
            elif key == "routeThresholdCredits":
                value = max(1, min(int(value), 10_000_000))
            else:
                value = bool(value)
            sets.append(f"{column}=%s")
            values.append(value)
        if not sets:
            return jsonify({"error": "No security policy fields supplied"}), 400
        conn = get_connection()
        try:
            _policy(conn, request.session_user_id)
            with conn.cursor() as cur:
                cur.execute(
                    f"""UPDATE user_security_policies
                        SET {', '.join(sets)}, updated_at=NOW()
                        WHERE user_id=%s::uuid""",
                    values + [request.session_user_id],
                )
            conn.commit()
            return jsonify({"ok": True, "policy": _policy(conn, request.session_user_id)})
        finally:
            _close(conn)

    @app.route("/api/security/passkeys/register/options", methods=["POST"])
    @require_session
    def passkey_register_options():
        api = _webauthn()
        origin = _request_origin()
        rp_id = _rp_id_for_origin(origin)
        conn = get_connection()
        try:
            user = _user(conn, request.session_user_id)
            if not user:
                return jsonify({"error": "User not found"}), 404
            existing = _passkeys(conn, request.session_user_id)
            descriptors = [
                api["PublicKeyCredentialDescriptor"](id=bytes(row["credential_id"]))
                for row in existing
            ]
            options = api["generate_registration_options"](
                rp_id=rp_id,
                rp_name=PASSKEY_RP_NAME,
                user_id=uuid.UUID(request.session_user_id).bytes,
                user_name=str(user.get("email") or request.session_user_id),
                user_display_name=str(user.get("display_name") or user.get("email") or "Sovereign user"),
                exclude_credentials=descriptors,
                authenticator_selection=api["AuthenticatorSelectionCriteria"](
                    resident_key=api["ResidentKeyRequirement"].PREFERRED,
                    user_verification=api["UserVerificationRequirement"].REQUIRED,
                ),
            )
            challenge_id = _store_challenge(
                conn,
                user_id=request.session_user_id,
                purpose="passkey_register",
                challenge=options.challenge,
                context={"origin": origin, "rpId": rp_id},
            )
            payload = json.loads(api["options_to_json"](options))
            payload["challengeId"] = challenge_id
            return jsonify(payload)
        except (ValueError, SecurityRuntimeUnavailable) as exc:
            return jsonify({"error": str(exc)}), 400
        finally:
            _close(conn)

    @app.route("/api/security/passkeys/register/verify", methods=["POST"])
    @require_session
    def passkey_register_verify():
        body = request.get_json(force=True) or {}
        api = _webauthn()
        conn = get_connection()
        try:
            challenge = _consume_challenge(
                conn,
                challenge_id=str(body.get("challengeId") or ""),
                purpose="passkey_register",
                user_id=request.session_user_id,
            )
            credential = body.get("credential") or {}
            verification = api["verify_registration_response"](
                credential=credential,
                expected_challenge=bytes(challenge["challenge"]),
                expected_rp_id=str(challenge["context"].get("rpId") or PASSKEY_RP_ID),
                expected_origin=str(challenge["context"].get("origin")),
                require_user_verification=True,
            )
            transports = credential.get("response", {}).get("transports", [])
            label = str(body.get("label") or "Passkey").strip()[:80] or "Passkey"
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO user_passkeys
                       (user_id, credential_id, credential_public_key, sign_count,
                        transports, device_type, backed_up, label)
                       VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (credential_id) DO NOTHING
                       RETURNING id::text""",
                    (
                        request.session_user_id,
                        verification.credential_id,
                        verification.credential_public_key,
                        verification.sign_count,
                        list(transports),
                        str(verification.credential_device_type),
                        bool(verification.credential_backed_up),
                        label,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            if not row:
                return jsonify({"error": "Passkey already registered"}), 409
            return jsonify({"ok": True, "id": row["id"], "label": label})
        except Exception as exc:
            conn.rollback()
            return jsonify({"error": str(exc)[:500]}), 400
        finally:
            _close(conn)

    @app.route("/api/security/passkeys/<passkey_id>", methods=["DELETE"])
    @require_session
    def passkey_delete(passkey_id: str):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM user_passkeys WHERE id=%s::uuid AND user_id=%s::uuid RETURNING id",
                    (passkey_id, request.session_user_id),
                )
                deleted = cur.fetchone()
            conn.commit()
            return (jsonify({"ok": True}) if deleted else (jsonify({"error": "Passkey not found"}), 404))
        finally:
            _close(conn)

    @app.route("/api/auth/passkey/options", methods=["POST"])
    def passkey_login_options():
        body = request.get_json(silent=True) or {}
        email = str(body.get("email") or "").strip().lower()
        api = _webauthn()
        origin = _request_origin()
        rp_id = _rp_id_for_origin(origin)
        conn = get_connection()
        try:
            user_id = None
            descriptors = []
            if email:
                with conn.cursor() as cur:
                    cur.execute("SELECT id::text FROM admin_users WHERE email=%s LIMIT 1", (email,))
                    user = cur.fetchone()
                if user:
                    user_id = str(user["id"])
                    descriptors = [
                        api["PublicKeyCredentialDescriptor"](id=bytes(row["credential_id"]))
                        for row in _passkeys(conn, user_id)
                    ]
            options = api["generate_authentication_options"](
                rp_id=rp_id,
                allow_credentials=descriptors,
                user_verification=api["UserVerificationRequirement"].REQUIRED,
            )
            challenge_id = _store_challenge(
                conn,
                user_id=user_id,
                purpose="passkey_login",
                challenge=options.challenge,
                context={"origin": origin, "rpId": rp_id},
            )
            payload = json.loads(api["options_to_json"](options))
            payload["challengeId"] = challenge_id
            return jsonify(payload)
        except (ValueError, SecurityRuntimeUnavailable) as exc:
            return jsonify({"error": str(exc)}), 400
        finally:
            _close(conn)

    @app.route("/api/auth/passkey/verify", methods=["POST"])
    def passkey_login_verify():
        body = request.get_json(force=True) or {}
        credential = body.get("credential") or {}
        api = _webauthn()
        conn = get_connection()
        try:
            credential_id = api["base64url_to_bytes"](str(credential.get("id") or ""))
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT p.id::text AS passkey_id, p.user_id::text, p.credential_public_key,
                              p.sign_count, u.*
                       FROM user_passkeys p
                       JOIN admin_users u ON u.id=p.user_id
                       WHERE p.credential_id=%s LIMIT 1""",
                    (credential_id,),
                )
                row = cur.fetchone()
            if not row:
                return jsonify({"error": "Unknown passkey"}), 401
            challenge = _consume_challenge(
                conn,
                challenge_id=str(body.get("challengeId") or ""),
                purpose="passkey_login",
                user_id=str(row["user_id"]),
            )
            verification = api["verify_authentication_response"](
                credential=credential,
                expected_challenge=bytes(challenge["challenge"]),
                expected_rp_id=str(challenge["context"].get("rpId") or PASSKEY_RP_ID),
                expected_origin=str(challenge["context"].get("origin")),
                credential_public_key=bytes(row["credential_public_key"]),
                credential_current_sign_count=int(row["sign_count"]),
                require_user_verification=True,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE user_passkeys
                       SET sign_count=%s, last_used_at=NOW(),
                           device_type=%s, backed_up=%s
                       WHERE id=%s::uuid""",
                    (
                        verification.new_sign_count,
                        str(verification.credential_device_type),
                        bool(verification.credential_backed_up),
                        row["passkey_id"],
                    ),
                )
            conn.commit()
            response = make_response(jsonify(_user_api(dict(row))))
            return set_session_cookie(response, str(row["user_id"]))
        except Exception as exc:
            conn.rollback()
            return jsonify({"error": str(exc)[:500]}), 401
        finally:
            _close(conn)

    @app.route("/api/security/account-keys", methods=["POST"])
    @require_session
    def account_key_create():
        body = request.get_json(force=True) or {}
        label = str(body.get("label") or "Sovereign Account Key").strip()[:80]
        raw_key = "svk_" + secrets.token_urlsafe(36)
        hint = raw_key[:12] + "…" + raw_key[-6:]
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO user_account_keys
                       (user_id, key_hash, key_hint, label)
                       VALUES (%s::uuid, %s, %s, %s) RETURNING id::text""",
                    (request.session_user_id, _secret_hash(raw_key), hint, label),
                )
                key_id = cur.fetchone()["id"]
            conn.commit()
            return jsonify({
                "ok": True,
                "id": key_id,
                "key": raw_key,
                "keyHint": hint,
                "warning": "This key is shown once. Store it securely.",
            }), 201
        finally:
            _close(conn)

    @app.route("/api/security/account-keys/<key_id>", methods=["DELETE"])
    @require_session
    def account_key_revoke(key_id: str):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE user_account_keys SET revoked_at=NOW()
                       WHERE id=%s::uuid AND user_id=%s::uuid AND revoked_at IS NULL
                       RETURNING id""",
                    (key_id, request.session_user_id),
                )
                revoked = cur.fetchone()
            conn.commit()
            return (jsonify({"ok": True}) if revoked else (jsonify({"error": "Account key not found"}), 404))
        finally:
            _close(conn)

    @app.route("/api/auth/account-key", methods=["POST"])
    def account_key_login():
        allowed, _remaining = _check_rate_limit(
            f"account-key-login:{request.remote_addr or 'unknown'}",
            max_requests=5,
        )
        if not allowed:
            return jsonify({"error": "Too many account-key attempts"}), 429
        body = request.get_json(force=True) or {}
        raw_key = str(body.get("key") or "").strip()
        if not raw_key.startswith("svk_"):
            return jsonify({"error": "Invalid account key"}), 401
        conn = get_connection()
        try:
            key_hash = _secret_hash(raw_key)
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT k.id::text AS key_id, k.user_id::text, u.*
                       FROM user_account_keys k JOIN admin_users u ON u.id=k.user_id
                       WHERE k.key_hash=%s AND k.revoked_at IS NULL
                         AND 'login'=ANY(k.scopes) LIMIT 1""",
                    (key_hash,),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE user_account_keys SET last_used_at=NOW() WHERE id=%s::uuid",
                        (row["key_id"],),
                    )
            if not row or row.get("is_banned"):
                conn.rollback()
                return jsonify({"error": "Invalid account key"}), 401
            conn.commit()
            response = make_response(jsonify(_user_api(dict(row))))
            return set_session_cookie(response, str(row["user_id"]))
        finally:
            _close(conn)

    @app.route("/api/security/step-up/options", methods=["POST"])
    @require_session
    def step_up_options():
        body = request.get_json(force=True) or {}
        action = str(body.get("action") or "").strip()[:80]
        context = body.get("context") if isinstance(body.get("context"), dict) else {}
        if not action:
            return jsonify({"error": "action is required"}), 400
        api = _webauthn()
        origin = _request_origin()
        rp_id = _rp_id_for_origin(origin)
        conn = get_connection()
        try:
            rows = _passkeys(conn, request.session_user_id)
            if not rows:
                return jsonify({"error": "No passkey registered", "blocker": "passkey_missing"}), 409
            options = api["generate_authentication_options"](
                rp_id=rp_id,
                allow_credentials=[
                    api["PublicKeyCredentialDescriptor"](id=bytes(row["credential_id"]))
                    for row in rows
                ],
                user_verification=api["UserVerificationRequirement"].REQUIRED,
            )
            challenge_id = _store_challenge(
                conn,
                user_id=request.session_user_id,
                purpose="step_up",
                challenge=options.challenge,
                context={"origin": origin, "rpId": rp_id, "action": action, "payload": context},
            )
            payload = json.loads(api["options_to_json"](options))
            payload["challengeId"] = challenge_id
            return jsonify(payload)
        finally:
            _close(conn)

    @app.route("/api/security/step-up/verify", methods=["POST"])
    @require_session
    def step_up_verify():
        body = request.get_json(force=True) or {}
        credential = body.get("credential") or {}
        api = _webauthn()
        conn = get_connection()
        try:
            credential_id = api["base64url_to_bytes"](str(credential.get("id") or ""))
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id::text, credential_public_key, sign_count
                       FROM user_passkeys
                       WHERE credential_id=%s AND user_id=%s::uuid LIMIT 1""",
                    (credential_id, request.session_user_id),
                )
                passkey = cur.fetchone()
            if not passkey:
                return jsonify({"error": "Passkey does not belong to this user"}), 401
            challenge = _consume_challenge(
                conn,
                challenge_id=str(body.get("challengeId") or ""),
                purpose="step_up",
                user_id=request.session_user_id,
            )
            verification = api["verify_authentication_response"](
                credential=credential,
                expected_challenge=bytes(challenge["challenge"]),
                expected_rp_id=str(challenge["context"].get("rpId") or PASSKEY_RP_ID),
                expected_origin=str(challenge["context"].get("origin")),
                credential_public_key=bytes(passkey["credential_public_key"]),
                credential_current_sign_count=int(passkey["sign_count"]),
                require_user_verification=True,
            )
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE user_passkeys SET sign_count=%s,last_used_at=NOW() WHERE id=%s::uuid",
                    (verification.new_sign_count, passkey["id"]),
                )
            conn.commit()
            action = str(challenge["context"].get("action") or "")
            payload = challenge["context"].get("payload") or {}
            context_hash = canonical_context_hash(action, payload)
            token = _create_approval(
                conn,
                user_id=request.session_user_id,
                action=action,
                context_hash=context_hash,
            )
            return jsonify({
                "ok": True,
                "token": token,
                "action": action,
                "contextHash": context_hash,
                "expiresIn": STEP_UP_TTL_SECONDS,
            })
        except Exception as exc:
            conn.rollback()
            return jsonify({"error": str(exc)[:500]}), 401
        finally:
            _close(conn)

    @app.route("/api/security/step-up/account-key", methods=["POST"])
    @require_session
    def step_up_account_key():
        allowed, _remaining = _check_rate_limit(
            f"account-key-step-up:{request.remote_addr or 'unknown'}",
            max_requests=5,
        )
        if not allowed:
            return jsonify({"error": "Too many account-key attempts"}), 429
        body = request.get_json(force=True) or {}
        raw_key = str(body.get("key") or "").strip()
        action = str(body.get("action") or "").strip()[:80]
        context = body.get("context") if isinstance(body.get("context"), dict) else {}
        if not raw_key or not action:
            return jsonify({"error": "key and action are required"}), 400
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id::text FROM user_account_keys
                       WHERE user_id=%s::uuid AND key_hash=%s AND revoked_at IS NULL
                         AND 'step_up'=ANY(scopes) LIMIT 1""",
                    (request.session_user_id, _secret_hash(raw_key)),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE user_account_keys SET last_used_at=NOW() WHERE id=%s::uuid",
                        (row["id"],),
                    )
            if not row:
                conn.rollback()
                return jsonify({"error": "Invalid account key"}), 401
            conn.commit()
            context_hash = canonical_context_hash(action, context)
            token = _create_approval(
                conn,
                user_id=request.session_user_id,
                action=action,
                context_hash=context_hash,
            )
            return jsonify({
                "ok": True,
                "token": token,
                "action": action,
                "contextHash": context_hash,
                "expiresIn": STEP_UP_TTL_SECONDS,
            })
        finally:
            _close(conn)
