/**
 * Tests for release-oauth-identity-gate.mjs (issue #1567)
 * Run: node --test scripts/release-oauth-identity-gate.test.mjs
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync, mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { checkStringsXml, runGate } from './release-oauth-identity-gate.mjs';

const GATE = new URL('./release-oauth-identity-gate.mjs', import.meta.url).pathname;

function makeXml({ appName = 'Sovereign Studio', title = 'Sovereign Studio', clientId } = {}) {
  return `<?xml version='1.0' encoding='utf-8'?>
<resources>
    <string name="app_name">${appName}</string>
    <string name="title_activity_main">${title}</string>
    <string name="google_client_id">${clientId}</string>
</resources>`;
}

test('fails on REPLACE_WITH_ placeholder in google_client_id', () => {
  const xml = makeXml({ clientId: 'REPLACE_WITH_YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com' });
  const violations = checkStringsXml(xml, 'fixture');
  assert.equal(violations.length, 1);
  assert.match(violations[0], /google_client_id/);
  assert.match(violations[0], /placeholder/);
});

test('passes with a real client ID and Sovereign Studio branding', () => {
  const xml = makeXml({ clientId: '123456789-abcdef.apps.googleusercontent.com' });
  assert.deepEqual(checkStringsXml(xml, 'fixture'), []);
});

test('fails on NOCode in app_name', () => {
  const xml = makeXml({ appName: 'NOCode Studio', clientId: 'real.apps.googleusercontent.com' });
  const violations = checkStringsXml(xml, 'fixture');
  assert.equal(violations.length, 1);
  assert.match(violations[0], /app_name/);
  assert.match(violations[0], /Sovereign Studio/);
});

test('fails on NOCode in title_activity_main', () => {
  const xml = makeXml({ title: 'NOCode Studio', clientId: 'real.apps.googleusercontent.com' });
  const violations = checkStringsXml(xml, 'fixture');
  assert.equal(violations.length, 1);
  assert.match(violations[0], /title_activity_main/);
});

test('reports multiple violations at once', () => {
  const xml = makeXml({
    appName: 'NOCode Studio',
    clientId: 'REPLACE_WITH_YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com',
  });
  assert.equal(checkStringsXml(xml, 'fixture').length, 2);
});

test('runGate fails closed when the resource file is missing', () => {
  const violations = runGate(['/nonexistent/path/strings.xml']);
  assert.equal(violations.length, 1);
  assert.match(violations[0], /not found/);
});

test('runGate checks an optional merged release resources file', () => {
  const dir = mkdtempSync(join(tmpdir(), 'oauth-gate-'));
  try {
    const merged = join(dir, 'merged-strings.xml');
    writeFileSync(
      merged,
      makeXml({ clientId: 'REPLACE_WITH_YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com' })
    );
    const violations = runGate([merged]);
    assert.equal(violations.length, 1);
    assert.match(violations[0], /merged-strings\.xml/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('CLI exits 1 with BLOCKED on placeholder fixture', () => {
  const dir = mkdtempSync(join(tmpdir(), 'oauth-gate-'));
  try {
    const bad = join(dir, 'bad.xml');
    writeFileSync(bad, makeXml({ clientId: 'REPLACE_WITH_X.apps.googleusercontent.com' }));
    let code = 0;
    let stderr = '';
    try {
      execFileSync('node', [GATE, bad], { cwd: dir, encoding: 'utf8' });
    } catch (e) {
      code = e.status;
      stderr = e.stderr;
    }
    assert.equal(code, 1);
    assert.match(stderr, /OAUTH_IDENTITY_GATE=BLOCKED/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('CLI exits 0 with PASS on clean fixture', () => {
  const dir = mkdtempSync(join(tmpdir(), 'oauth-gate-'));
  try {
    // Provide a minimal repo layout so the default source file is clean.
    const resDir = join(dir, 'android/app/src/main/res/values');
    mkdirSync(resDir, { recursive: true });
    writeFileSync(
      join(resDir, 'strings.xml'),
      makeXml({ clientId: '123-real.apps.googleusercontent.com' })
    );
    const out = execFileSync('node', [GATE], { cwd: dir, encoding: 'utf8' });
    assert.match(out, /OAUTH_IDENTITY_GATE=PASS/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
