"""Owner-authenticated, same-origin approval of one freshly resolved repair plan."""
import os
from flask import jsonify, make_response, request
from aurion_native_auth import NativeAuthRepair, NativeAuthState, OPERATION, RepairBlocked, plan_diagnostic
from command_queue import HostCommandQueueClient
from owner_input_runtime import _no_store, _owner_matches
from agent_runtime.agent_run_receipts import _broker_call, ReceiptIdentityBlocked


class PlanReader:
    def snapshot(self, revision):
        try:
            result = _broker_call("aurion_native_auth_plan", {"expected_revision": revision}, timeout=90)
        except ReceiptIdentityBlocked as error:
            raise RepairBlocked(plan_diagnostic(error.failure_family)) from None
        if not isinstance(result, dict):
            raise RepairBlocked("NATIVE_AUTH_PLAN_UNAVAILABLE")
        if "snapshot" not in result or "planHash" not in result:
            raise RepairBlocked(plan_diagnostic(result.get("blocker"))) from None
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
        except RepairBlocked as error:
            code = error.args[0] if len(error.args) == 1 else None
            return result({"error": plan_diagnostic(code)}, 409)
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
            queued = HostCommandQueueClient().enqueue("aurion_native_auth_apply",
                {"operation_id": approval["operationId"]})
            return result({**approval, "requestId": queued.get("request_id"), "queueStatus": queued["status"],
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
    def native_auth_page():
        # Static login shell, matching /owner-ssh. Every data/action endpoint
        # retains the real Bearer require_admin and configured-owner checks.
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
<label>Owner-Admin-Key <input id="adminKey" type="password" autocomplete="off"></label>
<button id="login">Anmelden</button><button id="logout">Schlüssel verwerfen</button>
<p>Der Schlüssel bleibt nur im Seitenspeicher und wird ausschließlich an diese Origin gesendet. Eine erfolgreiche Serverantwort bestätigt erst die Anmeldung.</p>
<label>Erwartete Aurion-Revision <input id="revision" maxlength="40" size="42"></label>
<button id="plan" disabled>Plan lesen</button><pre id="preview"></pre>
<button id="approve" disabled>Diesen Plan einmalig ausführen</button>
<button id="read" disabled>Operationszustand lesen</button><pre id="status"></pre>
<script>
let current=null, operation=null, admin="";
const element=id=>document.getElementById(id);
function forget(){admin='';current=null;operation=null;element('adminKey').value='';
for(const id of ['plan','approve','read'])element(id).disabled=true;
element('preview').textContent='';element('status').textContent='';}
element('login').onclick=()=>{admin=element('adminKey').value;element('adminKey').value='';
current=null;element('approve').disabled=true;element('plan').disabled=!admin;};
element('logout').onclick=forget;window.addEventListener('pagehide',forget);
function publicFailure(status,value){
const allowed={403:['OWNER_OR_ORIGIN_REQUIRED','OWNER_REQUIRED'],
409:[
"NATIVE_AUTH_PLAN_UNAVAILABLE", "NATIVE_AUTH_APPROVAL_BLOCKED", "SCHEMA_MISMATCH", "TARGET_OR_REVISION_INVALID", "TARGET_OR_REVISION_DRIFT", "IDENTITY_UNRESOLVED", "SNAPSHOT_CONTRACT", "CONFIGURATION_CONTRACT", "BASELINE_UNHEALTHY", "EXISTING_KEY_INVALID", "ENV_ENCODING", "ENV_FORMAT", "ENV_DUPLICATE", "ENV_EXPANSION", "FILE_NAME", "FILE_PROTECTION", "FILE_SIZE", "FILE_DRIFT", "FILE_UNAVAILABLE", "HOST_PATH_INVALID", "HOST_DIRECTORY_UNPROTECTED", "DEPLOYMENT_LINK_INVALID", "DEPLOYMENT_LINK_DRIFT", "HEALTH_BODY_SIZE", "HOST_COMMAND_FAILED", "CONTAINER_CARDINALITY", "CONTAINER_IDENTITY", "CONTAINER_ENV_DUPLICATE", "VOLUME_CONFIGURATION_DRIFT", "NETWORK_CONFIGURATION_DRIFT", "HOST_CONFIGURATION_DRIFT", "VOLUMES_UNAVAILABLE", "DEPLOYMENT_RECEIPT_MISMATCH", "ACTIVE_COMPOSE_UNRESOLVED", "DEPLOYMENT_MANIFEST_MISMATCH", "ROUTING_ENV_INVALID", "ROUTING_ENV_FILE_MISMATCH", "ROUTING_DOMAIN_MISMATCH", "ROUTING_PROXY_NETWORK_MISMATCH", "ROUTING_DATABASE_NETWORK_MISMATCH", "ROUTING_REQUIRED_KEY_MISSING", "ROUTING_UNEXPECTED_KEY", "ROUTING_CERTRESOLVER_INVALID", "ROUTING_RECEIPT_DOMAIN_MISMATCH", "ROUTING_RECEIPT_PROXY_NETWORK_MISMATCH", "ROUTING_RECEIPT_DATABASE_NETWORK_MISMATCH", "RUNTIME_DIGEST_MISMATCH", "IMAGE_REVISION_MISMATCH", "IMAGE_PROCESS_OVERRIDE", "IMAGE_HEALTHCHECK_UNVERIFIED", "EFFECTIVE_AUTH_CONFIG_DRIFT", "COMPOSE_SERVICE_MISMATCH", "EFFECTIVE_CONFIG_DRIFT", "NATIVE_AUTH_PRIVATE_OPERATOR_REQUIRED", "BROKER_SOCKET_UNAVAILABLE", "BROKER_SOCKET_PERMISSION_DENIED", "BROKER_RPC_TIMEOUT", "BROKER_RPC_UNAVAILABLE", "BROKER_RESPONSE_TOO_LARGE", "BROKER_RPC_INVALID_RESPONSE", "BROKER_RPC_CONTRACT_MISMATCH"],
400:['OPERATION_INVALID'],503:['NATIVE_AUTH_READBACK_UNAVAILABLE']};
const code=status===401?'AUTHENTICATION_NOT_CONFIRMED':
((allowed[status]||[]).includes(value?.error)?value.error:'REQUEST_NOT_CONFIRMED');
return 'HTTP '+status+' · '+code;
}
async function api(path,body){if(!admin)throw Error('AUTHENTICATION_NOT_CONFIRMED');
let response;
try{response=await fetch('/api/admin/aurion-native-auth/'+path,{
method:body?'POST':'GET',headers:{Authorization:'Bearer '+admin,
...(body?{'Content-Type':'application/json','X-Sovereign-Owner-Action':'aurion-native-auth'}:{})},
body:body?JSON.stringify(body):undefined,credentials:'same-origin',mode:'same-origin',redirect:'error',cache:'no-store'});
}catch(_){throw Error('NETWORK_RESPONSE_UNAVAILABLE');}
let value;try{value=await response.json();}catch(_){
if(response.status===401||response.status===403)forget();
throw Error('HTTP '+response.status+' · RESPONSE_NOT_JSON');}
if(!response.ok){const message=publicFailure(response.status,value);
if(response.status===401||response.status===403)forget();throw Error(message);}return value;}
const post=api;
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
element('read').onclick=async()=>{if(!operation)return;try{const value=await api('readback/'+operation);
element('status').textContent=JSON.stringify(value,null,2);}catch(e){element('status').textContent=e.message;}};
</script></html>'''
