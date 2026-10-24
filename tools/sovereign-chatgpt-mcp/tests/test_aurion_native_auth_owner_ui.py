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
