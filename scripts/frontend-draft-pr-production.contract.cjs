const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const source = readFileSync('tests/e2e/frontend-draft-pr-production.spec.ts', 'utf8');
const config = readFileSync('playwright.production.config.ts', 'utf8');
const workflow = readFileSync('.github/workflows/frontend-draft-pr-live-canary.yml', 'utf8');

test('production browser cannot silently run a local preview or replace network truth', () => {
  assert.match(config, /testMatch: 'frontend-draft-pr-production\.spec\.ts'/);
  assert.doesNotMatch(config, /webServer|vite|ignoreHTTPSErrors|storageState/);
  assert.doesNotMatch(source, /\.route\(|routeFromHAR|addInitScript|setExtraHTTPHeaders|request\.post\([^\n]*draft-pr/);
  assert.match(source, /const API_ORIGIN = new URL\(APP_URL\)\.origin/);
  assert.match(source, /page\.goto\(APP_URL/);
});
test('actual served revision and asset bytes are checked before credentials and after GitHub', () => {
  assert.match(source, /x-sovereign-user-app-producer/);
  assert.match(source, /CANONICAL_CAPACITOR_WEB_APP/);
  assert.match(source, /x-sovereign-source-revision/);
  assert.match(source, /createHash\('sha256'\)/);
  assert.match(source, /toBe\(initialArtifact\)/);
  assert.ok(source.indexOf('await verifyServedRevision(request);') < source.indexOf('data: { key: ACCOUNT_KEY }'));
  assert.ok(source.lastIndexOf('await verifyServedRevision(request);') > source.indexOf('record.githubVerified = true'));
});
test('only a real UI-created, independently read GitHub draft satisfies success', () => {
  for (const marker of ['await start.click()', 'await draftButton.click()', 'expect(pr.draft).toBe(true)',
    'expect(pr.merged_at).toBeNull()', 'expect(pr.head.sha).toBe(result.publishedHeadSha)',
    'toEqual([FILE_PATH])', 'Buffer.from(file.content', 'record.finalRevisionVerified === true']) {
    assert.ok(source.includes(marker), marker);
  }
  assert.match(source, /harnessRevision: process\.env\.GITHUB_SHA/);
  assert.match(source, /observedRuntimeRevision/);
  assert.match(source, /SOVEREIGN_E2E_PRODUCTION !== '1'/);
});
test('explicit production lane runs contracts and demands its resulting receipt', () => {
  const production = workflow.split('\n  production-draft-pr:\n')[1];
  assert.ok(production);
  assert.match(production, /inputs\.production == true/);
  assert.match(production, /node --test scripts\/frontend-draft-pr-production\.contract\.cjs/);
  assert.match(production, /playwright test --config=playwright\.production\.config\.ts/);
  assert.match(production, /assert\.equal\(receipt\.verified, true\)/);
  assert.doesNotMatch(production, /build:web|vite preview|continue-on-error|\|\| true/);
});
