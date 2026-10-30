"""Workflow regressions. SDK/HTTPS adapters are fixtures, never live APK evidence."""
import contextlib
import hashlib
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

    def test_exact_reviewed_aurion_revision_is_pinned_in_build_and_sign(self):
        expected = '36c4a98b15a431e0378b03cf825a193c3fb4cb8e'
        build = self.workflow['jobs']['build']
        self.assertEqual(build['env']['AURION_EXPECTED_REVISION'], expected)
        self.assertEqual(self.sign['env']['AURION_EXPECTED_REVISION'], expected)
        checkout = next(step for step in build['steps'] if step['name'].startswith('Checkout reviewed Aurion'))
        self.assertEqual(checkout['with']['ref'], expected)

    def test_owner_push_trigger_is_limited_to_main_workflow_change(self):
        events = self.workflow['on']
        self.assertEqual(set(events), {'workflow_dispatch', 'push'})
        self.assertIsNone(events['workflow_dispatch'])
        self.assertEqual(events['push'], {
            'branches': ['main'],
            'paths': ['.github/workflows/aurion-godot-login.yml'],
        })

    def test_every_effectful_job_retains_the_exact_owner_identity_guard(self):
        expected = ("github.repository == 'OuroborosCollective/Sovereign-Studio-ato' "
                    "&& github.ref == 'refs/heads/main' && github.actor_id == '266194342' "
                    "&& github.triggering_actor == github.repository_owner")
        for name in ['build', 'sign']:
            with self.subTest(job=name):
                self.assertEqual(' '.join(self.workflow['jobs'][name]['if'].split()), expected)

    def test_signable_3d_build_prepares_and_verifies_real_imported_assets(self):
        build = self.workflow['jobs']['build']
        body = next(s['run'] for s in build['steps'] if s.get('name', '').startswith('Build unsigned Login APK'))
        for expression in (
            "from './scripts/godot/export-assets.mjs'",
            'await stageAssetProject(project,revision)',
            'includeAssetManifest(',
            'await verifyStagedAssetImports(project,prepared,buildEnv)',
            'readApkAssets(apk,prepared,entries)',
            'packagedAssets',
        ):
            self.assertIn(expression, body, 'Signed G21 source does not package and verify active 3D GLB assets: '+expression)

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

    def run_validator(self, *, certificate=None, content_type='application/json', revision=None, badging_suffix='', domain_ok=True, unsigned=False, wrong_package=False, asset_fault=None):
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
            source_hash = hashlib.sha256(b'source fixture').hexdigest()
            asset_id = 'glb_' + source_hash[:48]
            imported_entry = 'assets/.godot/imported/' + asset_id + '.glb-test.scn'
            scene = b'RSRC' + b'fixture-imported-scene'
            asset_manifest = {'schemaVersion':'aurion.godot-prepared-assets.v1', 'sourceRevision':self.revision,
                        'sources':[{'assetId':asset_id,'sourceSha256':source_hash,'outputSha256':source_hash}]}
            manifest_bytes = json.dumps(asset_manifest, separators=(',',':')).encode()
            receipt = {'schemaVersion':'aurion.godot-packaged-assets.v1','sourceRevision':self.revision,
                       'manifestSha256':hashlib.sha256(manifest_bytes).hexdigest(),
                       'resources':[{'assetId':asset_id,'sourceSha256':source_hash,'outputSha256':source_hash,
                                     'importedEntry':imported_entry,'importedBytes':len(scene),
                                     'importedSha256':hashlib.sha256(scene).hexdigest()}],
                       'layer':'android-imported-resource-package-readback','device':'unverified'}
            if asset_fault == 'receipt_revision': receipt['sourceRevision']='0'*40
            if asset_fault == 'empty_resources': receipt['resources']=[]
            evidence_dir=Path(directory)/'aurion-sign-input';evidence_dir.mkdir()
            (evidence_dir/'build-evidence.json').write_text(json.dumps({'sourceRevision':self.revision,'signingState':'unsigned','packagedAssets':receipt}))
            with zipfile.ZipFile(apk,'w') as z:
                z.writestr('assets/override.cfg','[aurion]\nclient_build="'+(revision or self.revision)+'"\nnative_auth_start_enabled=true\n')
                z.writestr('lib/arm64-v8a/libgodot_android.so',b'non-executable test fixture')
                z.writestr('assets/assets/generated/manifest.json', manifest_bytes if asset_fault != 'manifest' else b'{}')
                z.writestr('assets/assets/generated/'+asset_id+'.glb.import','path="res://.godot/imported/'+asset_id+'.glb-test.scn"\n')
                if asset_fault != 'missing_scene': z.writestr(imported_entry, scene if asset_fault != 'scene' else b'RSRC'+b'tampered-scene')
            env={**self.sign['env'],'ANDROID_HOME':directory,'RUNNER_TEMP':directory}
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

    def test_signed_asset_receipt_is_preserved_and_checked(self):
        result=self.run_validator()
        self.assertEqual(result['packagedAssets']['sourceRevision'], self.revision)
        self.assertEqual(len(result['packagedAssets']['resources']), 1)

    def test_signed_asset_evidence_tampering_fails_closed(self):
        for fault in ['receipt_revision','empty_resources','manifest','scene','missing_scene']:
            with self.subTest(fault=fault),self.assertRaises((AssertionError,KeyError)):
                self.run_validator(asset_fault=fault)

    def test_final_artifact_readback_compares_unsigned_and_signed_receipts(self):
        step=next(s for s in self.sign['steps'] if s['name'].startswith('Independently read back'))
        snippets=re.findall(r"<<'PY'\n(.*?)\nPY", step['run'], re.S)
        self.assertEqual(len(snippets),2)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); readback=root/'readback'; readback.mkdir()
            inputs=root/'aurion-sign-input'; inputs.mkdir()
            receipt={'sourceRevision':self.revision,'resources':[{'assetId':'example'}]}
            evidence={'packagedAssets':receipt,'apkSha256':'1'*64}
            (inputs/'build-evidence.json').write_text(json.dumps({'packagedAssets':receipt}))
            (readback/'verified.json').write_text(json.dumps(evidence))
            with zipfile.ZipFile(readback/'artifact.zip','w') as z:z.writestr('build-evidence.json',json.dumps(evidence))
            with patch.dict(os.environ,{'RUNNER_TEMP':directory,'AURION_ARTIFACT_READBACK':str(readback)}):
                exec(compile(snippets[-1],'final-asset-readback','exec'),{'__name__':'__main__'})
                evidence['packagedAssets']['resources'][0]['assetId']='tampered'
                with zipfile.ZipFile(readback/'artifact.zip','w') as z:z.writestr('build-evidence.json',json.dumps(evidence))
                with self.assertRaises(AssertionError):
                    exec(compile(snippets[-1],'final-asset-readback','exec'),{'__name__':'__main__'})

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
