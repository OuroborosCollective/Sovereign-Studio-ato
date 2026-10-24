"""Execute the actual owner-page script with external DOM/fetch adapters, not a browser test."""
import ast
from pathlib import Path
import subprocess
import unittest


class OwnerPageContracts(unittest.TestCase):
    def test_key_stays_in_memory_and_all_calls_use_bearer_without_redirects(self):
        source = Path(__file__).resolve().parents[3] / 'scripts/sovereign-backend/aurion_native_auth_routes.py'
        tree = ast.parse(source.read_text())
        page = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'PAGE' for t in n.targets))
        script = page.split('<script>')[1].split('</script>')[0]
        harness = r'''
const assert=require('node:assert/strict');
const nodes=new Map(), calls=[]; let leaving;
global.document={getElementById(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',disabled:true});return nodes.get(id);}};
global.window={addEventListener(event,fn){assert.equal(event,'pagehide');leaving=fn;}};
global.fetch=async(path,options)=>{calls.push({path,options});return {ok:true,status:200,json:async()=>path.endsWith('/plan')?{planHash:'b'.repeat(64)}:path.endsWith('/approve')?{operationId:'c'.repeat(32),queueStatus:'QUEUED'}:{phase:'APPROVAL_PENDING'}};};
'''
        assertions = r'''
(async()=>{
const key='SYNTHETIC_UI_OWNER_SECRET';
element('adminKey').value=key;element('login').onclick();assert.equal(element('adminKey').value,'');
element('revision').value='a'.repeat(40);await element('plan').onclick();
assert.equal(calls.length,1); // no automatic approval
await element('approve').onclick();await element('read').onclick();
assert.equal(calls.length,3);
for(const call of calls){assert.equal(call.options.headers.Authorization,'Bearer '+key);
assert.equal(call.options.mode,'same-origin');assert.equal(call.options.redirect,'error');
assert(!call.path.includes(key));assert(!(call.options.body||'').includes(key));}
for(const node of nodes.values())assert(!node.textContent.includes(key));
leaving();assert.equal(admin,'');assert.equal(current,null);assert(element('approve').disabled);
})().catch(()=>process.exitCode=1);
'''
        completed = subprocess.run(['node', '-'], input=harness + script + assertions,
                                   text=True, capture_output=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn('SYNTHETIC_UI_OWNER_SECRET', completed.stdout + completed.stderr)

    def test_failure_codes_are_bounded_without_response_or_exception_secrets(self):
        source = Path(__file__).resolve().parents[3] / 'scripts/sovereign-backend/aurion_native_auth_routes.py'
        tree = ast.parse(source.read_text())
        page = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'PAGE' for t in n.targets))
        script = page.split('<script>')[1].split('</script>')[0]
        harness = r'''
const assert=require('node:assert/strict'),nodes=new Map();
global.document={getElementById(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',disabled:true});return nodes.get(id);}};
global.window={addEventListener(){}};
'''
        assertions = r'''
(async()=>{
const secret='SYNTHETIC_RESPONSE_TOKEN',cases=[
[401,{error:secret},'HTTP 401 · AUTHENTICATION_NOT_CONFIRMED'],
[403,{error:'OWNER_OR_ORIGIN_REQUIRED',extra:secret},'HTTP 403 · OWNER_OR_ORIGIN_REQUIRED'],
[403,{error:secret},'HTTP 403 · REQUEST_NOT_CONFIRMED'],
[409,{error:'NATIVE_AUTH_PLAN_UNAVAILABLE',detail:secret},'HTTP 409 · NATIVE_AUTH_PLAN_UNAVAILABLE'],
[409,{error:'NATIVE_AUTH_APPROVAL_BLOCKED'},'HTTP 409 · NATIVE_AUTH_APPROVAL_BLOCKED'],
[500,{error:secret},'HTTP 500 · REQUEST_NOT_CONFIRMED'],
[409,null,'HTTP 409 · REQUEST_NOT_CONFIRMED'],
[502,undefined,'HTTP 502 · RESPONSE_NOT_JSON'],
[0,undefined,'NETWORK_RESPONSE_UNAVAILABLE']];
for(const [status,body,expected] of cases){
forget();element('adminKey').value='SYNTHETIC_OWNER_KEY';element('login').onclick();
element('revision').value='a'.repeat(40);let requests=0;
global.fetch=async()=>{requests++;if(status===0)throw Error(secret);
return {status,ok:false,json:async()=>{if(body===undefined)throw Error(secret);return body;}};};
await element('plan').onclick();
assert.equal(requests,1);assert.equal(element('preview').textContent,expected);
assert.equal(current,null);assert(element('approve').disabled);
if(status===401||status===403)assert.equal(admin,'');
for(const node of nodes.values())assert(!node.textContent.includes(secret));
}
// Readback displays the same bounded diagnostic, never the arbitrary body.
admin='SYNTHETIC_OWNER_KEY';operation='a'.repeat(32);
global.fetch=async()=>({status:503,ok:false,json:async()=>({error:'NATIVE_AUTH_READBACK_UNAVAILABLE',detail:secret})});
await element('read').onclick();
assert.equal(element('status').textContent,'HTTP 503 · NATIVE_AUTH_READBACK_UNAVAILABLE');
})().catch(()=>process.exitCode=1);
'''
        completed = subprocess.run(['node', '-'], input=harness + script + assertions,
                                   text=True, capture_output=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn('SYNTHETIC_RESPONSE_TOKEN', completed.stdout + completed.stderr)
