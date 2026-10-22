"""Workflow regressions. SDK/HTTPS adapters are fixtures, never live APK evidence."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/aurion-godot-login.yml'
if not WORKFLOW.exists():
    WORKFLOW = Path(__file__).with_name('aurion-signing-isolated.yml')

class LoginWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load(WORKFLOW.read_text())
        self.sign = self.workflow['jobs']['sign']
        step = next(s for s in self.sign['steps'] if s['name'].startswith('Prepare repository-owned'))
        self.validator = step['run'].split("<<'PYCODE'\n", 1)[1].split('\nPYCODE', 1)[0]
        self.revision = self.sign['env']['AURION_EXPECTED_REVISION']
        self.fingerprint = self.sign['env']['AURION_LOGIN_SIGNER_SHA256']

    def test_exact_reviewed_aurion_source_is_pinned_in_build_sign_and_checkout(self):
        # Intentional release checkpoint. Updates require a reviewed exact revision.
        reviewed = '8c83af2ef0ad92876f6cb4a40901835b930427ea'
        self.assertEqual(len(reviewed), 40)
        self.assertTrue(all(character in '0123456789abcdef' for character in reviewed))
        build = self.workflow['jobs']['build']
        sign = self.workflow['jobs']['sign']
        checkout = next(step for step in build['steps'] if step['name'].startswith('Checkout reviewed Aurion source'))
        self.assertEqual(build['env']['AURION_EXPECTED_REVISION'], reviewed)
        self.assertEqual(sign['env']['AURION_EXPECTED_REVISION'], reviewed)
        self.assertEqual(checkout['with']['ref'], reviewed)

    def test_build_never_receives_release_secrets(self):
        self.assertNotIn('secrets.', json.dumps(self.workflow['jobs']['build']))
        self.assertEqual(self.sign['needs'], 'build')

    def test_signer_does_not_checkout_or_execute_application(self):
        for step in self.sign['steps']:
            self.assertNotIn('checkout', step.get('uses', ''))
            self.assertNotIn('export-login-android.mjs', step.get('run', ''))
            self.assertNotIn('gradlew', step.get('run', ''))
        self.assertIn("github.actor_id == '266194342'", self.sign['if'])
        self.assertIn('github.triggering_actor == github.repository_owner', self.sign['if'])

    def test_embedded_programs_parse(self):
        for job in self.workflow['jobs'].values():
            for step in job['steps']:
                body = step.get('run', '')
                subprocess.run(['bash', '-n'], input=body, text=True, check=True)
                for marker, code in re.findall(r"<<'(PY|PYCODE)'\n(.*?)\n\1", body, re.S):
                    compile(code, marker, 'exec')

    def run_validator(self, *, certificate=None, content_type='application/json', revision=None, badging_suffix='', domain_ok=True, unsigned=False, wrong_package=False):
        expected = self.fingerprint.replace(':', '').lower()
        signature = 'Verified using v2 scheme: true\nSigner #1 certificate SHA-256 digest: '+(certificate or expected)
        badging = "package: name='org.ouroboroscollective.aurion.godot.login' versionCode='1' versionName='0.1.0-login'\napplication-label:'Aurion Login'\nuses-permission: name='android.permission.INTERNET'\nnative-code: 'arm64-v8a'\nsdkVersion:'24'\ntargetSdkVersion:'36'\n"+badging_suffix
        if wrong_package:badging=badging.replace('org.ouroboroscollective.aurion.godot.login','invalid.package')
        manifest = '''      E: activity (
        android:name="Main"
        screenOrientation=0x0
      E: activity-alias (
        android:exported=0xffffffff
        android:targetActivity="Main"
        E: intent-filter
          android.intent.action.MAIN
          android.intent.category.LAUNCHER
        E: intent-filter
          android:autoVerify=0xffffffff
          android.intent.action.VIEW
          android.intent.category.DEFAULT
          android.intent.category.BROWSABLE
          android:scheme="https"
          android:host="arelogic.space"
          android:path="/app/auth/callback"
'''
        from email.message import Message
        headers=Message();headers['Content-Type']=content_type
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):
                return json.dumps([{'relation':['delegate_permission/common.handle_all_urls'],'target':{'namespace':'android_app','package_name':'org.ouroboroscollective.aurion.godot.login','sha256_cert_fingerprints':[expected if domain_ok else 'revoked']}}]).encode()
        response=Response();response.headers=headers
        class Opener:
            def open(self,*args,**kwargs):return response
        def sdk(args,**kwargs):
            if str(args[0]).endswith('apksigner'):return signature
            return badging if 'badging' in args else manifest
        with tempfile.TemporaryDirectory() as directory:
            apk=Path(directory)/'test.apk'
            with zipfile.ZipFile(apk,'w') as z:
                z.writestr('assets/override.cfg','[aurion]\nclient_build="'+(revision or self.revision)+'"\nnative_auth_start_enabled=true\n')
                z.writestr('lib/arm64-v8a/libgodot_android.so',b'non-executable test fixture')
            env={**self.sign['env'],'ANDROID_HOME':directory}
            with patch.dict(os.environ,env),patch.object(sys,'argv',['verify',str(apk)]+(['--unsigned'] if unsigned else [])),patch('urllib.request.build_opener',return_value=Opener()),patch('subprocess.check_output',side_effect=sdk),patch('subprocess.run',return_value=subprocess.CompletedProcess([],1)),contextlib.redirect_stdout(io.StringIO()) as output:
                exec(compile(self.validator,'actual-workflow-validator','exec'),{'__name__':'__main__'})
                return json.loads(output.getvalue())

    def test_unsigned_input_is_verified_before_signing(self):
        result=self.run_validator(unsigned=True)
        self.assertEqual(result['signingState'],'unsigned')
        self.assertIsNone(result['signerSha256'])

    def test_unsigned_wrong_package_is_rejected(self):
        with self.assertRaises(AssertionError):self.run_validator(unsigned=True,wrong_package=True)

    def test_actual_validator_accepts_consistent_adapter_evidence(self):
        self.assertEqual(self.run_validator()['sourceRevision'],self.revision)

    def test_actual_validator_rejects_wrong_certificate(self):
        with self.assertRaises(AssertionError):self.run_validator(certificate='0'*64)

    def test_actual_validator_rejects_stale_packaged_revision(self):
        with self.assertRaises(AssertionError):self.run_validator(revision='0'*40)

    def test_actual_validator_rejects_html_and_revoked_association(self):
        for options in [{'content_type':'text/html'},{'domain_ok':False}]:
            with self.subTest(options=options),self.assertRaises(AssertionError):self.run_validator(**options)

    def test_actual_validator_rejects_extra_permission(self):
        with self.assertRaises(AssertionError):self.run_validator(badging_suffix="uses-permission: name='android.permission.CAMERA'\n")

if __name__=='__main__':unittest.main()
