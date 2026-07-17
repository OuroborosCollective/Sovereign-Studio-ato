"""Owner-controlled one-time server input requests.

The request record contains metadata only. The protected value is accepted only
from the authenticated owner endpoint, written directly to one allowlisted
server destination and never returned, audited or stored in PostgreSQL.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Callable

from flask import jsonify, make_response, request

ConnectionFactory = Callable[[], Any]

DEFAULT_TTL_SECONDS = 900
MAX_TTL_SECONDS = 3600
MAX_COMMENT_CHARS = 1000
DEFAULT_ROOT = Path("/opt/sovereign-owner-managed")
DEFAULT_TARGETS: dict[str, dict[str, Any]] = {
    "openai_api_key": {
        "label": "OpenAI Provider für LiteLLM",
        "fieldLabel": "OpenAI API-Key",
        "path": "/opt/sovereign-owner-managed/openai_api_key.txt",
        "maxBytes": 8192,
        "kind": "credential",
    },
    "litellm_provider_key": {
        "label": "Einmaliger Fremdprovider-Zugang für LiteLLM",
        "fieldLabel": "Provider API-Key",
        "path": "/opt/sovereign-owner-managed/litellm_provider_key.txt",
        "maxBytes": 8192,
        "kind": "credential",
    },
}
SENSITIVE_COMMENT_PATTERNS = (
    re.compile(r"\b(?:ghp_|github_pat_|sk-proj-|Bearer\s+)[A-Za-z0-9_./+=-]{8,}", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _close(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _root() -> Path:
    return Path(os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", str(DEFAULT_ROOT))).resolve()


def _target_map() -> dict[str, dict[str, Any]]:
    targets = {key: dict(value) for key, value in DEFAULT_TARGETS.items()}
    targets["openai_api_key"]["path"] = str(_root() / "openai_api_key.txt")
    targets["litellm_provider_key"]["path"] = str(_root() / "litellm_provider_key.txt")
    configured = os.getenv("SOVEREIGN_OWNER_INPUT_TARGETS_JSON", "").strip()
    if configured:
        parsed = json.loads(configured)
        if not isinstance(parsed, dict):
            raise RuntimeError("SOVEREIGN_OWNER_INPUT_TARGETS_JSON must be an object")
        for target_id, raw in parsed.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", str(target_id)) or not isinstance(raw, dict):
                raise RuntimeError("Owner input target configuration is invalid")
            targets[str(target_id)] = dict(raw)

    root = _root()
    validated: dict[str, dict[str, Any]] = {}
    for target_id, raw in targets.items():
        path = Path(str(raw.get("path") or "")).resolve()
        if root != path.parent and root not in path.parents:
            continue
        max_bytes = max(1, min(int(raw.get("maxBytes") or 8192), 65536))
        validated[target_id] = {
            "id": target_id,
            "label": str(raw.get("label") or target_id)[:120],
            "fieldLabel": str(raw.get("fieldLabel") or "Geschützter Serverwert")[:120],
            "path": path,
            "maxBytes": max_bytes,
            "kind": str(raw.get("kind") or "credential")[:40],
        }
    return validated


def _owner_matches(admin: dict[str, Any] | None) -> bool:
    current = admin or {}
    expected_id = os.getenv("SOVEREIGN_OWNER_ADMIN_ID", "").strip()
    expected_email = os.getenv("SOVEREIGN_OWNER_ADMIN_EMAIL", "").strip().lower()
    if expected_id:
        return hmac.compare_digest(str(current.get("id") or ""), expected_id)
    if expected_email:
        return hmac.compare_digest(str(current.get("email") or "").lower(), expected_email)
    return False


def _service_authorized() -> bool:
    expected = os.getenv("SOVEREIGN_OWNER_REQUEST_KEY", "").strip()
    supplied = request.headers.get("X-Sovereign-Owner-Request-Key", "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _luhn_valid(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, character in enumerate(digits):
        value = int(character)
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _contains_payment_card_number(value: str) -> bool:
    for candidate in re.findall(r"(?:\d[ -]?){13,19}", value):
        digits = re.sub(r"\D", "", candidate)
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            return True
    return False


def _contains_payment_card_bytes(value: bytes | bytearray) -> bool:
    for candidate in re.findall(rb"(?:\d[ -]?){13,19}", bytes(value)):
        digits = re.sub(rb"\D", b"", candidate).decode("ascii")
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            return True
    return False


def _comment_is_safe(comment: str) -> bool:
    if _contains_payment_card_number(comment):
        return False
    return not any(pattern.search(comment) for pattern in SENSITIVE_COMMENT_PATTERNS)


def _no_store(response: Any) -> Any:
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _atomic_write(target: dict[str, Any], protected_value: bytes | bytearray | str) -> None:
    encoded = protected_value if isinstance(protected_value, bytearray) else bytearray(
        protected_value.encode("utf-8") if isinstance(protected_value, str) else protected_value
    )
    if not encoded or len(encoded) > int(target["maxBytes"]):
        raise ValueError("Der geschützte Wert fehlt oder überschreitet das Ziel-Limit")
    path = Path(target["path"])
    root = _root()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    resolved_parent = path.parent.resolve()
    if resolved_parent != root and root not in resolved_parent.parents:
        raise ValueError("Das Ziel liegt außerhalb des Owner-Verzeichnisses")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            view = memoryview(encoded)
            written = 0
            while written < len(view):
                written += os.write(descriptor, view[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
        for index in range(len(encoded)):
            encoded[index] = 0


def _request_api(row: dict[str, Any], targets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    target = targets.get(str(row.get("target_id") or ""), {})
    return {
        "id": str(row.get("id") or ""),
        "targetId": str(row.get("target_id") or ""),
        "targetLabel": str(target.get("label") or row.get("target_id") or ""),
        "fieldLabel": str(row.get("field_label") or target.get("fieldLabel") or "Geschützter Serverwert"),
        "title": str(row.get("title") or ""),
        "reason": str(row.get("reason") or ""),
        "status": str(row.get("status") or ""),
        "ownerComment": str(row.get("owner_comment") or ""),
        "requestedAt": str(row.get("requested_at") or ""),
        "expiresAt": str(row.get("expires_at") or ""),
        "resolvedAt": str(row.get("resolved_at") or ""),
        "resultCode": str(row.get("result_code") or ""),
    }


def register_owner_input_routes(
    app: Any,
    *,
    require_admin: Callable,
    get_connection: ConnectionFactory,
    get_current_admin: Callable[[], dict[str, Any] | None],
) -> None:
    @app.route("/api/internal/owner-input/requests", methods=["POST"])
    def owner_input_request_create():
        if not _service_authorized():
            return _no_store(jsonify({"error": "Nicht autorisiert"})), 401
        body = request.get_json(force=True) or {}
        targets = _target_map()
        target_id = str(body.get("targetId") or "").strip()
        if target_id not in targets:
            return _no_store(jsonify({"error": "Owner-Ziel ist nicht allowlistet"})), 400
        title = str(body.get("title") or "Geschützte Servereingabe erforderlich").strip()[:160]
        reason = str(body.get("reason") or "").strip()[:1000]
        field_label = str(body.get("fieldLabel") or targets[target_id]["fieldLabel"]).strip()[:120]
        ttl = max(60, min(int(body.get("expiresInSeconds") or DEFAULT_TTL_SECONDS), MAX_TTL_SECONDS))
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE owner_input_requests
                       SET status='expired', resolved_at=NOW(), result_code='expired'
                       WHERE target_id=%s AND status='pending' AND expires_at <= NOW()""",
                    (target_id,),
                )
                cur.execute(
                    """INSERT INTO owner_input_requests
                       (target_id, title, reason, field_label, expires_at)
                       VALUES (%s, %s, %s, %s, NOW() + (%s * INTERVAL '1 second'))
                       ON CONFLICT (target_id) WHERE status IN ('pending','processing') DO NOTHING
                       RETURNING id::text, target_id, title, reason, field_label, status,
                                 requested_at, expires_at, resolved_at, owner_comment, result_code""",
                    (target_id, title, reason, field_label, ttl),
                )
                row = cur.fetchone()
                if not row:
                    cur.execute(
                        """SELECT id::text, target_id, title, reason, field_label, status,
                                  requested_at, expires_at, resolved_at, owner_comment, result_code
                           FROM owner_input_requests
                           WHERE target_id=%s AND status IN ('pending','processing')
                           ORDER BY requested_at DESC LIMIT 1""",
                        (target_id,),
                    )
                    row = cur.fetchone()
            conn.commit()
            if not row:
                return _no_store(jsonify({"error": "Offene Owner-Anfrage konnte nicht bestätigt werden"})), 409
            return _no_store(jsonify({"ok": True, "request": _request_api(dict(row), targets)})), 201
        finally:
            _close(conn)

    @app.route("/api/internal/owner-input/requests/<request_id>", methods=["GET"])
    def owner_input_request_status(request_id: str):
        if not _service_authorized():
            return _no_store(jsonify({"error": "Nicht autorisiert"})), 401
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE owner_input_requests
                       SET status='expired', resolved_at=NOW(), result_code='expired'
                       WHERE id=%s::uuid AND status='pending' AND expires_at <= NOW()""",
                    (request_id,),
                )
                cur.execute(
                    """SELECT id::text, target_id, title, reason, field_label, status,
                              requested_at, expires_at, resolved_at, owner_comment, result_code
                       FROM owner_input_requests WHERE id=%s::uuid LIMIT 1""",
                    (request_id,),
                )
                row = cur.fetchone()
            conn.commit()
            if not row:
                return _no_store(jsonify({"error": "Anfrage nicht gefunden"})), 404
            return _no_store(jsonify({"ok": True, "request": _request_api(dict(row), _target_map())}))
        finally:
            _close(conn)

    @app.route("/api/admin/owner-input/requests", methods=["GET"])
    @require_admin
    def owner_input_requests_list():
        if not _owner_matches(get_current_admin()):
            return _no_store(jsonify({"error": "Nur die konfigurierte Owner-Instanz darf diese Anfragen sehen"})), 403
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE owner_input_requests SET status='expired', resolved_at=NOW(), result_code='expired'
                       WHERE status='pending' AND expires_at <= NOW()"""
                )
                cur.execute(
                    """SELECT id::text, target_id, title, reason, field_label, status,
                              requested_at, expires_at, resolved_at, owner_comment, result_code
                       FROM owner_input_requests
                       WHERE status IN ('pending','processing')
                       ORDER BY requested_at ASC LIMIT 20"""
                )
                rows = cur.fetchall()
            conn.commit()
            targets = _target_map()
            return _no_store(jsonify({"requests": [_request_api(dict(row), targets) for row in rows]}))
        finally:
            _close(conn)

    @app.route("/api/admin/owner-input/requests/<request_id>/resolve", methods=["POST"])
    @require_admin
    def owner_input_request_resolve(request_id: str):
        admin = get_current_admin()
        if not _owner_matches(admin):
            return _no_store(jsonify({"error": "Nur die konfigurierte Owner-Instanz darf entscheiden"})), 403
        decision = str(request.args.get("decision") or "").strip().lower()
        comment = str(request.args.get("comment") or "").strip()[:MAX_COMMENT_CHARS]
        protected_buffer = bytearray()
        if decision not in {"yes", "no"}:
            return _no_store(jsonify({"error": "decision muss yes oder no sein"})), 400
        if not _comment_is_safe(comment):
            return _no_store(jsonify({"error": "Der Kommentar darf keine Zugangsdaten oder Zahlungsdaten enthalten"})), 400

        targets = _target_map()
        conn = get_connection()
        claimed: dict[str, Any] | None = None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE owner_input_requests
                       SET status='processing', owner_admin_id=%s::uuid, owner_comment=%s
                       WHERE id=%s::uuid AND status='pending' AND expires_at > NOW()
                       RETURNING id::text, target_id""",
                    (str((admin or {}).get("id") or ""), comment, request_id),
                )
                row = cur.fetchone()
            conn.commit()
            if not row:
                return _no_store(jsonify({"error": "Anfrage ist abgelaufen, bereits entschieden oder nicht vorhanden"})), 409
            claimed = dict(row)

            if decision == "no":
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE owner_input_requests
                           SET status='denied', resolved_at=NOW(), result_code='owner_denied'
                           WHERE id=%s::uuid AND status='processing'""",
                        (request_id,),
                    )
                conn.commit()
                return _no_store(jsonify({"ok": True, "status": "denied"}))

            target = targets.get(str(claimed["target_id"]))
            if not target:
                raise ValueError("Das bestätigte Ziel ist nicht mehr allowlistet")
            content_length = int(request.content_length or 0)
            if content_length < 1 or content_length > int(target["maxBytes"]):
                raise ValueError("Der geschützte Wert fehlt oder überschreitet das Ziel-Limit")
            protected_buffer = bytearray(request.get_data(cache=False, as_text=False) or b"")
            if _contains_payment_card_bytes(protected_buffer):
                raise ValueError("Rohe Kartennummern sind nicht zulässig; verwende einen tokenisierten Zahlungsanbieter-Flow")
            _atomic_write(target, protected_buffer)
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE owner_input_requests
                       SET status='consumed', resolved_at=NOW(), consumed_at=NOW(), result_code='target_updated'
                       WHERE id=%s::uuid AND status='processing'""",
                    (request_id,),
                )
            conn.commit()
            return _no_store(jsonify({"ok": True, "status": "consumed", "targetId": target["id"]}))
        except Exception as exc:
            conn.rollback()
            if claimed:
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE owner_input_requests
                           SET status='failed', resolved_at=NOW(), result_code='target_update_failed'
                           WHERE id=%s::uuid AND status='processing'""",
                        (request_id,),
                    )
                conn.commit()
            return _no_store(jsonify({"error": str(exc)[:300]})), 400
        finally:
            for index in range(len(protected_buffer)):
                protected_buffer[index] = 0
            _close(conn)

    @app.route("/owner-approvals", methods=["GET"])
    def owner_input_page():
        response = make_response(_OWNER_PAGE)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return _no_store(response)


_OWNER_PAGE = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sovereign Owner-Freigaben</title>
<style>
:root{color-scheme:dark;--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;--muted:#8b949e;--yes:#238636;--no:#da3633;--accent:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;padding:max(1rem,env(safe-area-inset-top)) max(1rem,env(safe-area-inset-right)) max(1rem,env(safe-area-inset-bottom)) max(1rem,env(safe-area-inset-left))}.wrap{width:min(100%,42rem);margin:auto}.card{background:var(--card);border:1px solid var(--border);border-radius:1rem;padding:clamp(1rem,4vw,1.5rem);margin-block:1rem}label{display:block;color:var(--muted);font-size:.85rem;margin:.75rem 0 .35rem}input,textarea,button{font:inherit}input,textarea{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:.65rem;padding:.8rem;min-height:2.75rem}textarea{min-height:5rem}button{min-width:2.75rem;min-height:2.75rem;border:0;border-radius:.65rem;padding:.7rem 1rem;font-weight:700;cursor:pointer}.yes{background:var(--yes);color:white}.no{background:var(--no);color:white}.ghost{background:#21262d;color:var(--text);border:1px solid var(--border)}.row{display:flex;gap:.75rem;flex-wrap:wrap;margin-top:1rem}.muted{color:var(--muted);font-size:.85rem}.error{color:#ff7b72}.ok{color:#7ee787}h1{font-size:clamp(1.25rem,5vw,1.8rem)}pre{white-space:pre-wrap;overflow-wrap:anywhere}@media(hover:hover){button:hover{filter:brightness(1.12)}}
</style></head><body><main class="wrap"><h1>Owner-Freigaben</h1><p class="muted">Der geschützte Wert gehört ausschließlich in das dafür vorgesehene Feld – niemals in Kommentar oder Chat.</p>
<section id="login" class="card"><label for="adminKey">Admin-Zugang</label><input id="adminKey" type="password" autocomplete="off"><button class="yes" id="loginButton">Anmelden</button><p id="loginMessage" class="error"></p></section>
<section id="requestCard" class="card" hidden><h2 id="requestTitle"></h2><p id="requestReason"></p><p class="muted" id="requestMeta"></p><label for="comment">Optionaler Kommentar ohne sensible Daten</label><textarea id="comment" maxlength="1000"></textarea><label for="protectedValue" id="valueLabel"></label><input id="protectedValue" type="password" autocomplete="new-password" spellcheck="false"><div class="row"><button class="yes" id="yesButton">Ja – sicher eintragen</button><button class="no" id="noButton">Nein</button><button class="ghost" id="reloadButton">Neu laden</button></div><p id="result"></p></section>
<section id="empty" class="card" hidden><p>Keine offene Anfrage.</p><button class="ghost" id="emptyReload">Neu laden</button></section></main>
<script>
let adminKey='';let current=null;const byId=id=>document.getElementById(id);const requestedId=new URLSearchParams(window.location.search).get('request_id')||'';
function headers(){return {'Authorization':'Bearer '+adminKey};}
async function load(){const response=await fetch('/api/admin/owner-input/requests',{headers:headers(),cache:'no-store',credentials:'same-origin',mode:'same-origin',redirect:'error'});const data=await response.json();if(!response.ok)throw new Error(data.error||'Anfrage fehlgeschlagen');const requests=data.requests||[];current=requestedId?(requests.find(item=>item.id===requestedId)||null):(requests[0]||null);render();}
function render(){byId('login').hidden=Boolean(adminKey);byId('requestCard').hidden=!current;byId('empty').hidden=Boolean(current)||!adminKey;if(!current)return;byId('requestTitle').textContent=current.title;byId('requestReason').textContent=current.reason;byId('requestMeta').textContent=current.targetLabel+' · gültig bis '+current.expiresAt;byId('valueLabel').textContent=current.fieldLabel;byId('protectedValue').value='';byId('comment').value='';byId('result').textContent='';}
async function resolve(decision){if(!current)return;const encoded=decision==='yes'?new TextEncoder().encode(byId('protectedValue').value):new Uint8Array();const url='/api/admin/owner-input/requests/'+encodeURIComponent(current.id)+'/resolve?decision='+encodeURIComponent(decision)+'&comment='+encodeURIComponent(byId('comment').value);try{const response=await fetch(url,{method:'POST',headers:{'Authorization':'Bearer '+adminKey,'Content-Type':'application/octet-stream'},cache:'no-store',credentials:'same-origin',mode:'same-origin',redirect:'error',body:encoded});encoded.fill(0);byId('protectedValue').value='';const data=await response.json();if(!response.ok)throw new Error(data.error||'Entscheidung fehlgeschlagen');byId('result').className='ok';byId('result').textContent=decision==='yes'?'Sicher eingetragen und Transportfeld geleert.':'Abgelehnt.';current=null;setTimeout(load,700);}catch(error){encoded.fill(0);byId('protectedValue').value='';byId('result').className='error';byId('result').textContent=error instanceof TypeError?'HTTPS-Übertragung nicht bestätigt. Bitte nicht erneut eingeben und die Verbindung prüfen.':error.message;}}
byId('loginButton').onclick=async()=>{adminKey=byId('adminKey').value.trim();byId('adminKey').value='';try{await load();}catch(error){adminKey='';byId('loginMessage').textContent=error.message;render();}};byId('yesButton').onclick=()=>resolve('yes');byId('noButton').onclick=()=>resolve('no');byId('reloadButton').onclick=load;byId('emptyReload').onclick=load;
</script></body></html>"""
