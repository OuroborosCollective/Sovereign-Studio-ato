"""Authenticated owner SSH console; protected values bypass MCP and its queue."""
from __future__ import annotations
import json
import hashlib
import os
import time
import uuid
from pathlib import Path
from flask import jsonify, make_response, request
from command_queue import HostCommandQueueClient
from owner_input_runtime import _atomic_write, _no_store, _owner_matches, _root
from owner_ssh_console import OwnerSSHConsole, OPERATIONS
from agent_runtime.agent_run_receipts import _broker_call

def _protected_write(name, value):
    content = bytearray(json.dumps(value, separators=(",", ":")).encode())
    try:
        _atomic_write({"path": _root() / name, "maxBytes": 65536,
                       "kind": "root_owned_credential", "ownerUid": 0, "ownerGid": 0}, content)
    finally:
        content[:] = b"\x00" * len(content)

def register_owner_ssh_routes(app, *, require_admin, get_current_admin):
    def owner():
        return _owner_matches(get_current_admin())

    def csrf_ok():
        # A custom same-origin header forces CORS preflight on other origins.
        # Do not allow either absent Origin or an externally supplied owner ID
        # to bypass the authenticated, configured server owner.
        return request.headers.get("X-Sovereign-Owner-Action") == "ssh-console" and (
            not request.headers.get("Origin") or request.headers["Origin"] == os.getenv("SOVEREIGN_BACKEND_PUBLIC_URL", "https://sovereign-backend.arelorian.de").rstrip("/")
        )

    @app.route("/api/admin/owner-ssh/status", methods=["GET"])
    @require_admin
    def owner_ssh_status():
        if not owner():
            return _no_store(jsonify({"error": "Owner access required"})), 403
        try:
            result = _broker_call("ssh_console_status", {}, timeout=8)
            if result.get("sessionId"):
                state = OwnerSSHConsole(root=_root())._state()
                if state["sessionId"] == result["sessionId"]:
                    result["lastActivity"] = state.get("lastActivity")
            return _no_store(jsonify(result)), 200 if result.get("ok") else 503
        except Exception:
            return _no_store(jsonify({"error": "SSH broker unavailable; no connection is confirmed"})), 503

    @app.route("/api/admin/owner-ssh/action", methods=["POST"])
    @require_admin
    def owner_ssh_action():
        if not owner() or not csrf_ok():
            return _no_store(jsonify({"error": "Authenticated same-origin owner action required"})), 403
        if not request.is_json or not request.content_length or request.content_length > 24000:
            return _no_store(jsonify({"error": "Invalid owner SSH payload"})), 400
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _no_store(jsonify({"error": "Invalid owner SSH payload"})), 400
        action = body.get("action")
        if action not in {"connect", "close", "inspect", "grant", "revoke"}:
            return _no_store(jsonify({"error": "Unsupported owner SSH action"})), 400
        try:
            if action == "connect":
                profile = body.get("profile")
                OwnerSSHConsole.validate_profile(profile)
                _protected_write("ssh_console_profile.json", profile)
            operation_id = uuid.uuid4().hex
            record = {"operationId": operation_id, "action": action, "expiresAt": time.time() + 35}
            if action == "connect":
                record["profileSha256"] = hashlib.sha256(json.dumps(profile, separators=(",", ":")).encode()).hexdigest()
            if action != "connect":
                session_id = str(body.get("sessionId") or "")
                if not len(session_id) == 32 or any(c not in "0123456789abcdef" for c in session_id):
                    raise ValueError("Invalid session identity")
                record["sessionId"] = session_id
            if action == "inspect":
                if body.get("operation") not in OPERATIONS:
                    raise ValueError("Invalid inspection operation")
                record["operation"] = body["operation"]
            if action == "grant":
                ops, ttl = body.get("operations"), body.get("ttl", 300)
                if not isinstance(ops, list) or not ops or any(op not in OPERATIONS for op in ops):
                    raise ValueError("Invalid delegation scope")
                if type(ttl) is not int or not 30 <= ttl <= 900:
                    raise ValueError("Invalid delegation duration")
                record.update(operations=ops, ttl=ttl)
            _protected_write("ssh_console_action.json", record)
            result = HostCommandQueueClient().submit("ssh_console_owner_action",
                       {"operation_id": operation_id}, timeout=25)
            # Credentials are never included in the queue, response or errors.
            return _no_store(jsonify(result)), 200 if result.get("ok") or result.get("status") in {"IN_PROGRESS", "QUEUED"} else 409
        except Exception:
            return _no_store(jsonify({"error": "SSH action was not confirmed; check status before retrying",
                                     "protectedValuesReturned": False})), 400

    @app.route("/api/admin/owner-ssh/command/<request_id>", methods=["GET"])
    @require_admin
    def owner_ssh_command_status(request_id):
        if not owner():
            return _no_store(jsonify({"error": "Owner access required"})), 403
        try:
            result = HostCommandQueueClient().status(request_id)
            return _no_store(jsonify(result))
        except Exception:
            return _no_store(jsonify({"error": "SSH command status unavailable"})), 400

    @app.route("/owner-ssh", methods=["GET"])
    def owner_ssh_page():
        response = make_response(PAGE)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return _no_store(response)

PAGE = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sovott SSH-Konsole</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3}*{box-sizing:border-box}
body{margin:auto;padding:20px;max-width:820px}section{border:1px solid #30363d;border-radius:14px;padding:18px;margin:16px 0;background:#161b22}
input,textarea,select,button{font:inherit;color:inherit;background:#0d1117;border:1px solid #57606a;border-radius:8px;padding:12px;min-height:46px}
input,textarea,select{width:100%;margin:6px 0 12px}textarea{min-height:110px}button{cursor:pointer;margin:5px}
button:disabled{opacity:.45;cursor:wait}label{display:block}.muted{color:#8b949e}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:480px;overflow:auto}
.check{display:inline-flex;align-items:center;gap:8px;margin:8px}.check input{width:auto;margin:0}
</style></head><body><h1>Sovott SSH-Konsole</h1>
<p class="muted">Deine Zugangsdaten bleiben auf dieser geschützten Sovereign-Seite. Die Verbindung erfolgt direkt über SSH.</p>
<section id="login"><label>Owner-Admin-Zugang<input id="admin" type="password" autocomplete="off"></label><button id="loginButton">Anmelden</button></section>
<section id="setup" hidden><h2>VPS verbinden</h2>
<label>Öffentliche VPS-IP<input id="host" autocomplete="off" placeholder="IPv4 oder IPv6"></label>
<label>SSH-Port<input id="port" type="number" min="1" max="65535" value="22"></label>
<label>SSH-Benutzer<input id="username" autocomplete="off"></label>
<label>Geprüfter Host-Public-Key (ssh-ed25519)<input id="hostKey" autocomplete="off"></label>
<p class="muted">Den Public-Key unabhängig über deine Provider-Konsole prüfen. Unbekannte oder geänderte Host-Schlüssel werden abgewiesen.</p>
<label>Anmeldung<select id="authMode"><option value="key">SSH-Schlüssel</option><option value="password">SSH-Passwort</option></select></label>
<label id="keySection">Dedizierter SSH-Privatschlüssel ohne Passphrase<textarea id="privateKey" autocomplete="off" spellcheck="false"></textarea></label>
<label id="passwordSection" hidden>SSH-Passwort<input id="password" type="password" autocomplete="off"></label>
<p class="muted">Schlüssel oder Passwort ausschließlich hier eingeben. Verschlüsselte Schlüssel und zusätzliche MFA-Abfragen sind in dieser Version noch nicht unterstützt.</p>
<label>Sitzungsdauer<select id="duration"><option value="900">15 Minuten</option><option value="1800">30 Minuten</option><option value="3600">60 Minuten</option></select></label>
<button id="connect">SSH verbinden</button></section>
<section id="uncertain" hidden><h2>Verbindungsende unbestätigt</h2><p>Die Assistenzfreigabe ist widerrufen. Das Ende der SSH-Verbindung konnte noch nicht bestätigt werden.</p><button id="retryClose">Schließen erneut prüfen</button></section>
<section id="console" hidden><h2>Aktive Verbindung</h2><p id="identity"></p><p id="grantState"></p>
<div id="operations"></div>
<h3>Meine Hilfe freigeben</h3><p>Nur die ausgewählten Menüaktionen werden freigegeben. Die Freigabe gilt für diese Verbindung und endet automatisch.</p>
<div id="scope"></div><label>Freigabedauer<select id="grantDuration"><option value="300">5 Minuten</option><option value="900">15 Minuten</option></select></label>
<button id="grant">Hilfe freigeben</button><button id="revoke">Freigabe widerrufen</button><button id="close">Verbindung beenden</button>
<h3>Konsole</h3><pre id="output" aria-live="polite">Noch keine Aktion ausgeführt.</pre></section>
<p id="message" role="status" aria-live="polite"></p>
<script>
'use strict';
const $=id=>document.getElementById(id);
let admin='',session='',busy=false,pending='';
const names={system:'System',disk:'Festplatten',memory:'Arbeitsspeicher',containers:'Container',services:'Dienste'};
async function api(path,body){
 const response=await fetch(path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+admin,...(body?{'Content-Type':'application/json','X-Sovereign-Owner-Action':'ssh-console'}:{})},body:body?JSON.stringify(body):undefined,credentials:'same-origin',mode:'same-origin',cache:'no-store',redirect:'error'});
 const data=await response.json();
 if(!response.ok){if(response.status===401||response.status===403){admin='';$('login').hidden=false;$('setup').hidden=true;$('console').hidden=true;}throw new Error(data.error||data.blocker||'Aktion nicht bestätigt.');}
 return data;
}
function message(value){$('message').textContent=value;}
function render(state){
 const previous=session;session=state.sessionId||'';
 const active=state.status==='connected';
 const uncertain=state.status==='close_unverified';
 $('login').hidden=Boolean(admin);$('setup').hidden=!admin||active||uncertain;$('console').hidden=!active;$('uncertain').hidden=!uncertain;
 $('identity').textContent=active?state.username+'@'+state.host+' · '+state.hostFingerprint+' · bis '+new Date(state.expiresAt*1000).toLocaleTimeString():'';
 if(state.lastActivity){const a=state.lastActivity;$('output').textContent='['+a.actor+'] $ '+a.command+'\n'+a.output+'\nExit: '+a.exitCode;}
 $('grantState').textContent=state.assistantGrantActive?'Hilfe freigegeben: '+state.allowedOperations.map(op=>names[op]||op).join(', '):'Keine aktive Freigabe für die Assistenz.';
 const resetScope=previous!==session||!$('scope').childElementCount;
 $('operations').replaceChildren();if(resetScope)$('scope').replaceChildren();
 for(const op of state.operations||[]){
  const button=document.createElement('button');button.textContent=names[op]||op;button.onclick=()=>action({action:'inspect',operation:op});$('operations').append(button);
  if(resetScope){const label=document.createElement('label');label.className='check';const box=document.createElement('input');box.type='checkbox';box.value=op;box.checked=true;label.append(box,document.createTextNode(names[op]||op));$('scope').append(label);}
 }
}
async function refresh(){if(admin&&!busy&&!pending){try{render(await api('/api/admin/owner-ssh/status'));}catch(error){$('console').hidden=true;$('uncertain').hidden=true;message('Sitzungsstatus unbestätigt: '+error.message);throw error;}}}
async function action(body){
 if(busy||pending)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);message('Aktion läuft…');
 try{
  const result=await api('/api/admin/owner-ssh/action',{...body,sessionId:session});
  if(result.status==='IN_PROGRESS'||result.status==='QUEUED'){pending=result.request_id;message('Auftrag läuft. Nicht erneut senden.');return;}
  if(result.output!==undefined)$('output').textContent='$ '+result.command+'\n'+result.output+'\nExit: '+result.exitCode;
  if(!result.ok)throw new Error(result.blocker||'Aktion nicht bestätigt.');
  message(result.status);busy=false;await refresh();
 }catch(error){message(error.message);}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=Boolean(pending));}
}
$('loginButton').onclick=async()=>{admin=$('admin').value.trim();$('admin').value='';try{await refresh();message('Owner angemeldet.');}catch(error){admin='';message(error.message);}};
$('authMode').onchange=()=>{const password=$('authMode').value==='password';$('keySection').hidden=password;$('passwordSection').hidden=!password;$('privateKey').value='';$('password').value='';};
$('connect').onclick=async()=>{const profile={host:$('host').value.trim(),port:Number($('port').value),username:$('username').value.trim(),knownHostKey:$('hostKey').value.trim(),expiresInSeconds:Number($('duration').value)};if($('authMode').value==='password')profile.password=$('password').value;else profile.privateKey=$('privateKey').value;$('privateKey').value='';$('password').value='';await action({action:'connect',profile});profile.privateKey='';profile.password='';};
$('retryClose').onclick=()=>action({action:'close'});
$('close').onclick=()=>action({action:'close'});$('revoke').onclick=()=>action({action:'revoke'});
$('grant').onclick=()=>action({action:'grant',operations:Array.from($('scope').querySelectorAll('input:checked')).map(b=>b.value),ttl:Number($('grantDuration').value)});
setInterval(async()=>{try{
 if(pending&&!busy){const result=await api('/api/admin/owner-ssh/command/'+encodeURIComponent(pending));if(result.status!=='IN_PROGRESS'&&result.status!=='QUEUED'){pending='';message(result.status);if(result.output!==undefined)$('output').textContent='$ '+result.command+'\n'+result.output+'\nExit: '+result.exitCode;document.querySelectorAll('button').forEach(b=>b.disabled=false);}}
 await refresh();
}catch(error){message(error.message);}},5000);
window.addEventListener('pagehide',()=>{admin='';$('privateKey').value='';$('password').value='';});
</script></body></html>"""
