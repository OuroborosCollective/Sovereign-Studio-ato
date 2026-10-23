"""Owner-authenticated, same-origin approval of one freshly resolved repair plan."""
import os
from flask import jsonify, make_response, request
from aurion_native_auth import NativeAuthRepair, NativeAuthState, OPERATION, RepairBlocked
from command_queue import HostCommandQueueClient
from owner_input_runtime import _no_store, _owner_matches
from agent_runtime.agent_run_receipts import _broker_call


class PlanReader:
    def snapshot(self, revision):
        result = _broker_call("aurion_native_auth_plan", {"expected_revision": revision}, timeout=90)
        if "snapshot" not in result or "planHash" not in result:
            raise RepairBlocked("PLAN_UNAVAILABLE")
        return result["snapshot"]


def register_aurion_native_auth_routes(app, *, require_admin, get_current_admin):
    def owner():
        return _owner_matches(get_current_admin())

    def same_origin():
        return (request.headers.get("Origin") == os.getenv("SOVEREIGN_BACKEND_PUBLIC_URL", "https://sovereign-backend.arelorian.de").rstrip("/")
                and request.headers.get("X-Sovereign-Owner-Action") == "aurion-native-auth")

    def result(payload, status=200):
        return _no_store(jsonify(payload)), status

    def payload(keys):
        if not request.is_json or not request.content_length or request.content_length > 1024:
            raise RepairBlocked("PAYLOAD_INVALID")
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != set(keys) or any(not isinstance(v, str) for v in body.values()):
            raise RepairBlocked("PAYLOAD_INVALID")
        return body

    @app.route("/api/admin/aurion-native-auth/plan", methods=["POST"])
    @require_admin
    def native_auth_plan():
        if not owner() or not same_origin():
            return result({"error": "OWNER_OR_ORIGIN_REQUIRED"}, 403)
        try:
            body = payload({"expectedRevision"})
            runtime = NativeAuthRepair(PlanReader(), NativeAuthState())
            return result(runtime.plan(body["expectedRevision"]))
        except Exception:
            return result({"error": "NATIVE_AUTH_PLAN_UNAVAILABLE"}, 409)

    @app.route("/api/admin/aurion-native-auth/approve", methods=["POST"])
    @require_admin
    def native_auth_approve():
        if not owner() or not same_origin():
            return result({"error": "OWNER_OR_ORIGIN_REQUIRED"}, 403)
        try:
            body = payload({"expectedRevision", "planHash"})
            runtime = NativeAuthRepair(PlanReader(), NativeAuthState())
            approval = runtime.issue(body["planHash"], body["expectedRevision"])
        except Exception:
            return result({"error": "NATIVE_AUTH_APPROVAL_BLOCKED"}, 409)
        try:
            queued = HostCommandQueueClient().submit("aurion_native_auth_apply",
                {"operation_id": approval["operationId"]}, timeout=1)
            return result({**approval, "requestId": queued.get("request_id"),
                           "nextAction": "read_operation_and_queue_status"}, 202)
        except Exception:
            # Do not retry a possibly submitted action. Its operation identity
            # remains available even when the queue response was lost.
            return result({**approval, "status": "QUEUE_OUTCOME_UNCERTAIN",
                           "nextAction": "read_operation_and_queue_status"}, 202)

    @app.route("/api/admin/aurion-native-auth/readback/<operation_id>", methods=["GET"])
    @require_admin
    def native_auth_readback(operation_id):
        if not owner():
            return result({"error": "OWNER_REQUIRED"}, 403)
        if not OPERATION.fullmatch(operation_id):
            return result({"error": "OPERATION_INVALID"}, 400)
        try:
            return result(_broker_call("aurion_native_auth_readback", {"operation_id": operation_id}, timeout=30))
        except Exception:
            return result({"error": "NATIVE_AUTH_READBACK_UNAVAILABLE"}, 503)

    @app.route("/owner-aurion-native-auth", methods=["GET"])
    @require_admin
    def native_auth_page():
        if not owner():
            return result({"error": "OWNER_REQUIRED"}, 403)
        response = make_response(PAGE)
        response.headers["Content-Security-Policy"] = "default-src 'none'; script-src 'unsafe-inline'; connect-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return _no_store(response)


PAGE = '''<!doctype html><html lang="de"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Aurion Native-Auth</title>
<h1>Aurion Native-Auth-Reparatur</h1>
<p>Nur Projekt echoes-of-aurion, Dienst aurion. Prüfe den konkreten Plan vor der einmaligen Freigabe.</p>
<p>Risiken: lokale Schlüsselneuanlage, falls erforderlich; kurze Dienstunterbrechung;
rootgeschützte Sicherung und kontrollierte Rücknahme. Der Starttest erzeugt eine kurzlebige
Auth-Transaktion. Vollständiger Geräte-Login bleibt UNVERIFIED.</p>
<label>Erwartete Aurion-Revision <input id="revision" maxlength="40" size="42"></label>
<button id="plan">Plan lesen</button><pre id="preview"></pre>
<button id="approve" disabled>Diesen Plan einmalig ausführen</button>
<button id="read" disabled>Operationszustand lesen</button><pre id="status"></pre>
<script>
let current=null, operation=null;
const element=id=>document.getElementById(id);
async function post(path,body){const response=await fetch('/api/admin/aurion-native-auth/'+path,{
method:'POST',headers:{'Content-Type':'application/json','X-Sovereign-Owner-Action':'aurion-native-auth'},
body:JSON.stringify(body),credentials:'same-origin',cache:'no-store'}); const value=await response.json();
if(!response.ok)throw Error(value.error||'Anfrage fehlgeschlagen'); return value;}
element('revision').oninput=()=>{current=null;element('approve').disabled=true;};
element('plan').onclick=async()=>{current=null;element('approve').disabled=true;try{
const revision=element('revision').value; const value=await post('plan',{expectedRevision:revision});
element('preview').textContent=JSON.stringify(value,null,2);current={revision,hash:value.planHash};
element('approve').disabled=value.alreadySatisfied||!value.planHash;
}catch(e){element('preview').textContent=e.message;}};
element('approve').onclick=async()=>{if(!current)return;const chosen=current;current=null;
element('approve').disabled=true;try{const value=await post('approve',{expectedRevision:chosen.revision,planHash:chosen.hash});
operation=value.operationId;element('status').textContent=JSON.stringify(value,null,2);element('read').disabled=!operation;
}catch(e){element('status').textContent=e.message;}};
element('read').onclick=async()=>{if(!operation)return;try{const r=await fetch('/api/admin/aurion-native-auth/readback/'+operation,{cache:'no-store',credentials:'same-origin'});
element('status').textContent=JSON.stringify(await r.json(),null,2);}catch(e){element('status').textContent='Readback nicht verfügbar';}};
</script></html>'''
