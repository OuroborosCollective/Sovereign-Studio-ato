"""Execute actual core, broker dispatch, routes and UI; external IO is substituted.

These are regression fixtures, not live runtime/authentication evidence. Real
Flask and Bearer-boundary tests remain in backend/tests.
"""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/sovereign-chatgpt-mcp'))
import aurion_native_auth as core
from command_contract import is_mutating_action


class PlanDiagnostics(unittest.TestCase):
    def test_host_broker_planreader_route_ui_pipeline(self):
        source = ROOT / 'scripts/sovereign-backend/aurion_native_auth_routes.py'
        tree = ast.parse(source.read_text())
        selected = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        page = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'PAGE' for t in n.targets))
        broker_tree = ast.parse((ROOT / 'tools/sovereign-chatgpt-mcp/broker.py').read_text())
        dispatch = next(n for cls in broker_tree.body if isinstance(cls, ast.ClassDef)
                        and cls.name == 'BrokerRuntime' for n in cls.body
                        if isinstance(n, ast.FunctionDef) and n.name == 'dispatch')
        broker_globals = {'Any': object, 'os': os, 'subprocess': subprocess,
                          'is_mutating_action': is_mutating_action}
        exec(compile(ast.Module(body=[dispatch], type_ignores=[]), 'broker.py', 'exec'), broker_globals)
        class Broker:
            private_owner_mode = True
            def __getattr__(self, name):
                return lambda *a, **k: None  # unrelated bound handlers, never called
        class App:
            def __init__(self): self.endpoints = {}
            def route(self, path, **kwargs):
                def register(fn): self.endpoints[path] = fn; return fn
                return register
        class ReceiptIdentityBlocked(RuntimeError):
            def __init__(self, code, detail):
                super().__init__(detail); self.failure_family = code
        secret = 'SYNTHETIC_PIPELINE_SECRET'
        cases = [(core.RepairBlocked('SCHEMA_MISMATCH'), 'SCHEMA_MISMATCH'),
                 (core.RepairBlocked('ENV_DUPLICATE'), 'ENV_DUPLICATE'),
                 (ValueError(secret), 'NATIVE_AUTH_PLAN_UNAVAILABLE'),
                 (core.RepairBlocked(secret), 'NATIVE_AUTH_PLAN_UNAVAILABLE'),
                 (core.RepairBlocked('SCHEMA_MISMATCH '+secret), 'NATIVE_AUTH_PLAN_UNAVAILABLE')]
        cases.extend((core.RepairBlocked(code), code) for code in sorted(core.PLAN_DIAGNOSTIC_CODES)
                     if code.startswith('ROUTING_'))
        for failure, expected in cases:
            with self.subTest(expected=expected, exception=type(failure).__name__):
                class Host:
                    def snapshot(self, revision): raise failure
                broker = Broker()
                broker.aurion_native_auth = core.NativeAuthRepair(Host(), None)
                calls = []
                def rpc(action, arguments, **kwargs):
                    calls.append(action)
                    return broker_globals['dispatch'](broker, action, arguments)
                ns = {'os': os, 'NativeAuthRepair': core.NativeAuthRepair, 'NativeAuthState': lambda: None,
                      'RepairBlocked': core.RepairBlocked, 'plan_diagnostic': core.plan_diagnostic,
                      'ReceiptIdentityBlocked': ReceiptIdentityBlocked, '_broker_call': rpc,
                      '_owner_matches': lambda owner: True, '_no_store': lambda x: x, 'jsonify': lambda x: x,
                      'request': SimpleNamespace(is_json=True, content_length=64,
                          headers={'Origin':'https://sovereign-backend.arelorian.de',
                                   'X-Sovereign-Owner-Action':'aurion-native-auth'},
                          get_json=lambda **k: {'expectedRevision':'a'*40})}
                exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), ns)
                app = App()
                ns['register_aurion_native_auth_routes'](app, require_admin=lambda f:f, get_current_admin=lambda: {})
                logs = io.StringIO()
                with patch.dict(os.environ, {'SOVEREIGN_MCP_ENABLE_AURION_OPERATOR':'1',
                     'SOVEREIGN_BACKEND_PUBLIC_URL':'https://sovereign-backend.arelorian.de'}), contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
                    body, status = app.endpoints['/api/admin/aurion-native-auth/plan']()
                self.assertEqual((body, status), ({'error':expected},409))
                self.assertEqual(calls, ['aurion_native_auth_plan'])
                self.assertNotIn(secret, json.dumps(body)+logs.getvalue())
                harness = '''const assert=require('node:assert/strict'),nodes=new Map();
global.document={getElementById(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',disabled:true});return nodes.get(id);}};
global.window={addEventListener(){}};
'''
                script = page.split('<script>')[1].split('</script>')[0]
                assertions = '''(async()=>{element('adminKey').value='SYNTHETIC_KEY';element('login').onclick();
element('revision').value='a'.repeat(40);let calls=0;
global.fetch=async()=>{calls++;return {status:409,ok:false,json:async()=>(__PAYLOAD_JSON__)};};
await element('plan').onclick();assert.equal(calls,1);assert(element('approve').disabled);
assert.equal(element('preview').textContent,__EXPECTED_JSON__);
})().catch(()=>process.exitCode=1);'''.replace('__PAYLOAD_JSON__',json.dumps(body)).replace('__EXPECTED_JSON__',json.dumps('HTTP 409 · '+expected))
                ran = subprocess.run(['node','-'], input=harness+script+assertions, text=True, capture_output=True, timeout=10)
                self.assertEqual(ran.returncode,0,ran.stderr)
                self.assertNotIn(secret,ran.stdout+ran.stderr)

    def test_allowlist_rejects_nonstrings_and_partial_matches(self):
        for value in [None, {}, [], 'SCHEMA_MISMATCH secret', 'schema_mismatch']:
            self.assertEqual(core.plan_diagnostic(value), 'NATIVE_AUTH_PLAN_UNAVAILABLE')
