const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { requireCanaryAccountKey, assertCanarySession } = require('./frontend-draft-pr-production-auth.cjs');
const source = readFileSync('tests/e2e/frontend-draft-pr-production.spec.ts', 'utf8');
const config = readFileSync('playwright.production.config.ts', 'utf8');
const workflow = readFileSync('.github/workflows/frontend-draft-pr-live-canary.yml', 'utf8');

test('production authentication never falls back to a guest or creates an account', () => {
  for (const key of ['', '  ', undefined, null, false, 123]) {
    assert.throws(() => requireCanaryAccountKey(key), /CANARY_AUTH_REQUIRED_NO_GUEST_FALLBACK/);
  }
  assert.doesNotThrow(() => requireCanaryAccountKey('test-only-key'));
  assert.match(source, /requireCanaryAccountKey\(ACCOUNT_KEY\)/);
  assert.doesNotMatch(source, /if \(ACCOUNT_KEY\)|\/api\/auth\/(?:guest|register)|randomBytes/);
  assert.ok(source.indexOf('requireCanaryAccountKey(ACCOUNT_KEY)') < source.indexOf('await verifyServedRevision(request);'));
});

test('a guest, banned user, changed identity or unverified balance cannot authorize execution', () => {
  const id = '11111111-1111-4111-8111-111111111111';
  const valid = { id, isGuest: false, isBanned: false, creditStateVerified: true, credits: 500 };
  assert.doesNotThrow(() => assertCanarySession(valid, id));
  for (const change of [{ isGuest: true }, { isGuest: undefined }, { isBanned: true }, { isBanned: undefined },
    { creditStateVerified: false }, { creditStateVerified: undefined }, { credits: '500' }, { credits: NaN },
    { credits: -1 }, { credits: 0 }, { id: '22222222-2222-4222-8222-222222222222' }, { id: '' }]) {
    assert.throws(() => assertCanarySession({ ...valid, ...change }, id));
  }
  assert.throws(() => assertCanarySession(null, id));
  assert.throws(() => assertCanarySession([], id));
});

test('the same real account and a visible catalog-backed Free route are required', () => {
  assert.match(source, /assertCanarySession\(initialSession, initialSession\.id\)/);
  assert.match(source, /assertCanarySession\(session, initialSession\.id\)/);
  assert.match(source, /page\.getByLabel\('LLM Route'/);
  assert.match(source, /routeSelect\.selectOption\(freeRoute!/);
  assert.match(source, /record\.creditStateVerified = session\.creditStateVerified/);
  assert.doesNotMatch(source, /provider_funded_delta|signup_bonus|initial_credits|\/api\/admin\/|UPDATE admin_users|INSERT INTO credit_ledger/);
});

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
