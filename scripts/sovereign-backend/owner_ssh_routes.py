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
        if action not in {"connect", "probe", "close", "inspect", "grant", "revoke"}:
            return _no_store(jsonify({"error": "Unsupported owner SSH action"})), 400
        try:
            if action == "connect":
                profile = body.get("profile")
                OwnerSSHConsole.validate_profile(profile)
                _protected_write("ssh_console_profile.json", profile)
            operation_id = uuid.uuid4().hex
            record = {"operationId": operation_id, "action": action, "createdAt": time.time(), "expiresAt": time.time() + 35}
            if action == "connect":
                record["profileSha256"] = hashlib.sha256(json.dumps(profile, separators=(",", ":")).encode()).hexdigest()
            if action == "probe":
                host, port = OwnerSSHConsole.validate_target(body.get("host"), body.get("port", 22))
                record.update(host=host, port=port)
            if action not in {"connect", "probe"}:
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
                OwnerSSHConsole.validate_grant(ops, ttl)
                record.update(operations=ops, ttl=ttl)
                if "shell" in ops:
                    command = body.get("command")
                    timeout_seconds = body.get("timeoutSeconds", 30)
                    record.update(commandSha256=OwnerSSHConsole.validate_shell_command(command, timeout_seconds),
                                  timeoutSeconds=timeout_seconds)
            if action in {"revoke", "close"}:
                # Cancellation must reach an in-flight worker immediately, before queue dispatch.
                # This durable marker remains effective if the queued owner action expires.
                _protected_write("ssh_console_revocation.json", {"sessionId": record["sessionId"], "at": record["createdAt"]})
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
<button id="probeHost" type="button">1. Server prüfen (ohne Passwort)</button>
<div id="hostVerification" hidden>
<p>Gefundener Server-Fingerabdruck: <strong id="hostFingerprint"></strong></p>
<p class="muted">In der Hostinger-Webkonsole unabhängig vergleichen mit: <code>ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub</code>. Der Eintrag mit <code>command=</code> gehört zur CI-Autorisierung und ist kein Server-Hostschlüssel.</p>
<label class="check"><input id="hostConfirmed" type="checkbox">Fingerabdruck stimmt mit Hostinger überein</label>
</div>
<p class="muted">Danach mit Benutzername und Passwort verbinden. Kein SSH-Schlüsseltext erforderlich. Der Server-Schlüssel wird nur nach Bestätigung der Identität akzeptiert.</p>
<label>Anmeldung<select id="authMode"><option value="password" selected>SSH-Passwort</option><option value="key">SSH-Schlüssel (optional)</option></select></label>
<label id="keySection" hidden>Dedizierter SSH-Privatschlüssel ohne Passphrase<textarea id="privateKey" autocomplete="off" spellcheck="false"></textarea></label>
<label id="passwordSection">SSH-Passwort<input id="password" type="password" autocomplete="off"></label>
<p class="muted">Schlüssel oder Passwort ausschließlich hier eingeben. Verschlüsselte Schlüssel und zusätzliche MFA-Abfragen sind in dieser Version noch nicht unterstützt.</p>
<label>Sitzungsdauer<select id="duration"><option value="900">15 Minuten</option><option value="1800">30 Minuten</option><option value="3600">60 Minuten</option></select></label>
<button id="connect">SSH verbinden</button></section>
<section id="uncertain" hidden><h2>Verbindungsende unbestätigt</h2><p>Die Assistenzfreigabe ist widerrufen. Das Ende der SSH-Verbindung konnte noch nicht bestätigt werden.</p><button id="retryClose">Schließen erneut prüfen</button></section>
<section id="console" hidden><h2>Aktive Verbindung</h2><p id="identity"></p><p id="grantState"></p>
<div id="operations"></div>
<h3>Meine Hilfe freigeben</h3><p>Nur die ausgewählten Menüaktionen werden freigegeben. Die Freigabe gilt für diese Verbindung und endet automatisch.</p>
<div id="scope"></div><label>Freigabedauer<select id="grantDuration"><option value="300">5 Minuten</option><option value="900">15 Minuten</option></select></label>
<label class="check"><input id="workspaceScope" type="checkbox">Isolierten VPS-Workspace freigeben</label>
<label class="check"><input id="shellScope" type="checkbox">Einen konkreten VPS-Befehl einmalig freigeben</label>
<label id="shellCommandLabel" hidden>Exakter freizugebender Befehl<textarea id="shellCommand" autocomplete="off" spellcheck="false"></textarea></label>
<label id="shellTimeoutLabel" hidden>Maximale Ausführungszeit<select id="shellTimeout"><option value="30">30 Sekunden</option><option value="60">1 Minute</option><option value="120">2 Minuten</option><option value="180">3 Minuten</option><option value="300">5 Minuten</option></select></label>
<p id="shellScopeHelp" hidden>Die Freigabe gilt nur für diesen exakten Befehl, diese SSH-Verbindung und die gewählte Zeit. Sie wird vor Ausführung verbraucht und kann widerrufen werden. stdout und stderr werden vollständig verworfen; nur Exit-Code und Bytezahlen werden quittiert.</p>
<p>Erlaubt wiederholte Dateiänderungen und Python-/Node-Tests für 15–60 Minuten. Testcode läuft ohne Root-Rechte und ohne Netzwerk oder produktive Dateien. Merge, Deployment und Datenbankänderungen gehören nicht zu dieser Sitzungsberechtigung.</p>
<label>Workspace-Freigabedauer<select id="workspaceDuration"><option value="900">15 Minuten</option><option value="1800">30 Minuten</option><option value="3600">60 Minuten</option></select></label>
<button id="grant">Hilfe freigeben</button><button id="revoke">Freigabe widerrufen</button><button id="close">Verbindung beenden</button>
<h3>Konsole</h3><pre id="output" aria-live="polite">Noch keine Aktion ausgeführt.</pre></section>
<p id="message" role="status" aria-live="polite"></p>
<script>
'use strict';
const $=id=>document.getElementById(id);
let admin='',session='',busy=false,pending='',pendingAction='',trustedKey='',trustedTarget='';
const target=()=>$('host').value.trim()+'|'+Number($('port').value);
function clearProbe(){
 trustedKey='';trustedTarget='';$('hostVerification').hidden=true;
 $('hostConfirmed').checked=false;$('hostFingerprint').textContent='';
}
function receiveProbe(result){
 if(!result||result.status!=='SSH_HOST_KEY_DISCOVERED'||result.ok!==true||
    result.host+'|'+Number(result.port)!==target()||
    typeof result.knownHostKey!=='string'||!result.knownHostKey.startsWith('ssh-ed25519 ')||
    typeof result.hostFingerprint!=='string'||!result.hostFingerprint.startsWith('SHA256:')){
   clearProbe();throw new Error('Serverprüfung fehlgeschlagen. IP und SSH-Port erneut prüfen.');
 }
 trustedKey=result.knownHostKey;trustedTarget=target();
 $('hostFingerprint').textContent=result.hostFingerprint;
 $('hostConfirmed').checked=false;$('hostVerification').hidden=false;
 message('Server gefunden. Fingerabdruck vor dem Verbinden in der Hostinger-Konsole vergleichen.');
}
const names={system:'System',disk:'Festplatten',memory:'Arbeitsspeicher',containers:'Container',services:'Dienste',workspace:'Isolierter Workspace',shell:'Freie VPS-Befehle'};
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
 if(state.lastActivity){const a=state.lastActivity;if(a.operation==='shell'){$('output').textContent='[Shell-Ausführungsbeleg]\nFreigabe: '+a.approvalId+'\nQuellrevision: '+a.sourceRevision+'\nBefehls-SHA256: '+a.commandSha256+'\nStatus: '+a.status+'\nstdout-Bytes: '+(a.stdoutBytes??'unbekannt')+' · stderr-Bytes: '+(a.stderrBytes??'unbekannt')+'\nExit: '+a.exitCode+'\nAusgabe: verworfen';}else{$('output').textContent='['+a.actor+'] $ '+a.command+'\n'+a.output+'\nExit: '+a.exitCode;}}
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
  if(result.status==='IN_PROGRESS'||result.status==='QUEUED'){pending=result.request_id;pendingAction=body.action;message('Auftrag läuft. Nicht erneut senden.');return;}
  if(result.output!==undefined)$('output').textContent='$ '+result.command+'\n'+result.output+'\nExit: '+result.exitCode;
  if(!result.ok)throw new Error(result.blocker||'Aktion nicht bestätigt.');
  if(body.action==='probe')receiveProbe(result);
  else message(result.status);busy=false;await refresh();
 }catch(error){message(error.message);}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=Boolean(pending));}
}
$('loginButton').onclick=async()=>{admin=$('admin').value.trim();$('admin').value='';if(!admin){message('Owner-Admin-Zugang erforderlich.');return;}try{await refresh();message('Owner angemeldet.');}catch(error){admin='';message(error.message);}};
$('authMode').onchange=()=>{const password=$('authMode').value==='password';$('keySection').hidden=password;$('passwordSection').hidden=!password;$('privateKey').value='';$('password').value='';};
for(const id of ['host','port'])$(id).addEventListener('input',clearProbe);
$('probeHost').onclick=()=>{clearProbe();return action({action:'probe',host:$('host').value.trim(),port:Number($('port').value)});};
$('connect').onclick=async()=>{
 if(!trustedKey||trustedTarget!==target()||!$('hostConfirmed').checked){
  message('Zuerst den Server prüfen und dessen Fingerabdruck mit Hostinger vergleichen.');return;
 }
 const profile={host:$('host').value.trim(),port:Number($('port').value),username:$('username').value.trim(),knownHostKey:trustedKey,expiresInSeconds:Number($('duration').value)};
 if($('authMode').value==='password')profile.password=$('password').value;else profile.privateKey=$('privateKey').value;
 $('privateKey').value='';$('password').value='';
 await action({action:'connect',profile});profile.privateKey='';profile.password='';
};
$('retryClose').onclick=()=>action({action:'close'});
$('close').onclick=()=>action({action:'close'});$('revoke').onclick=()=>action({action:'revoke'});
$('shellScope').onchange=()=>{$('shellCommandLabel').hidden=!$('shellScope').checked;$('shellTimeoutLabel').hidden=!$('shellScope').checked;$('shellScopeHelp').hidden=!$('shellScope').checked;};
$('grant').onclick=()=>{if($('shellScope').checked){const command=$('shellCommand').value;if(!command.trim()){message('Für die Shell-Freigabe zuerst genau einen Befehl eintragen.');return;}const displayControl=/[\p{Cf}\p{Cs}\p{Cn}\p{Zl}\p{Zp}]/u;const control=/\p{Cc}/u;if(Array.from(command).some(ch=>displayControl.test(ch)||(control.test(ch)&&ch!=='\n'&&ch!=='\t'))){message('Unsichtbare Steuerzeichen im Befehl sind nicht erlaubt.');return;}const timeoutSeconds=Number($('shellTimeout').value);if(!confirm('Einmalige Freigabe für genau diesen Befehl bis zu '+timeoutSeconds+' Sekunden?\n\n'+command+'\n\nDer Befehl kann produktive Dateien und Dienste verändern.'))return;$('shellCommand').value='';return action({action:'grant',operations:['shell'],ttl:Number($('grantDuration').value),command,timeoutSeconds});}const ops=Array.from($('scope').querySelectorAll('input:checked')).map(b=>b.value);if($('workspaceScope').checked)ops.push('workspace');return action({action:'grant',operations:ops,ttl:Number($($('workspaceScope').checked?'workspaceDuration':'grantDuration').value)});};
setInterval(async()=>{try{
 if(pending&&!busy){const result=await api('/api/admin/owner-ssh/command/'+encodeURIComponent(pending));if(result.status!=='IN_PROGRESS'&&result.status!=='QUEUED'){
 const completedAction=pendingAction;pending='';pendingAction='';
 if(completedAction==='probe'&&result.ok)receiveProbe(result);else message(result.status);
 if(result.output!==undefined)$('output').textContent='$ '+result.command+'\n'+result.output+'\nExit: '+result.exitCode;
 document.querySelectorAll('button').forEach(b=>b.disabled=false);
}}
 await refresh();
}catch(error){message(error.message);}},5000);
window.addEventListener('pagehide',()=>{admin='';$('privateKey').value='';$('password').value='';});
</script></body></html>"""
