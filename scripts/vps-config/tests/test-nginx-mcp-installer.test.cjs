'use strict';

// Contract test for scripts/vps-config/setup-nginx.sh.
//
// This test asserts the installer's fail-closed behaviour without actually
// running it. Running the installer requires root, a live nginx, an
// operator-managed key file on disk, and a live MCP backend on port 8090.
// None of those are prerequisites for a meaningful contract test: we only
// need to verify the script expresses the right preconditions, recovery
// paths, and refusal-to-generate-key behaviour.
//
// Why this exists:
//   A previous version of this script wrote the API key file inline as
//   part of the install. That was a regression of the secret-lifecycle
//   rule and is the exact failure mode that #1187 was opened to fix.
//   This test makes that class of regression unreviewable-by-omission.

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const INSTALLER = path.resolve(__dirname, '..', 'setup-nginx.sh');

function readInstaller() {
  assert.ok(
    fs.existsSync(INSTALLER),
    `expected installer at ${INSTALLER}`,
  );
  return fs.readFileSync(INSTALLER, 'utf8');
}

test('installer: is executable and uses strict shell mode', () => {
  const stat = fs.statSync(INSTALLER);
  // 0o111 = any execute bit set; this is the bit pattern we care about.
  assert.ok(
    (stat.mode & 0o111) !== 0,
    `setup-nginx.sh must have at least one execute bit set (got mode ${(stat.mode & 0o777).toString(8)})`,
  );

  const text = readInstaller();
  assert.match(
    text,
    /^set\s+-euo\s+pipefail/m,
    'installer must enable -euo pipefail so any failed command aborts the install',
  );
});

test('installer: refuses to generate or write the operator key', () => {
  const text = readInstaller();

  // The installer must never invent a key. Any of the following patterns
  // would indicate a regression:
  //   - writing to /opt/sovereign-owner-managed/...key...
  //   - calling openssl rand, head -c, xxd, or similar to mint bytes
  //   - using echo <random> > $KEY_FILE
  assert.doesNotMatch(
    text,
    />\s*"?\$KEY_FILE"?|\$\{?KEY_FILE\}?\s*<|tee\s+\$KEY_FILE/,
    'installer must never write the operator API key file directly',
  );

  assert.doesNotMatch(
    text,
    /openssl\s+rand|head\s+-c\s+\d+\s+\/dev\/urandom|xxd\s+-l\s+\d+/,
    'installer must never generate random key material itself',
  );

  // It must require the key file to already exist on disk with the right
  // mode and owner before doing anything else.
  assert.match(
    text,
    /\/opt\/sovereign-owner-managed\/openhands_mcp_api_key\.txt/,
    'installer must reference the canonical operator-managed key path',
  );
  assert.match(
    text,
    /mode\s+0600|mode.*0600/,
    'installer must verify the key file has mode 0600',
  );
  assert.match(
    text,
    /owner.*root:root|root:root/,
    'installer must verify the key file is owned by root:root',
  );
});

test('installer: backs up before changing anything and rolls back on failure', () => {
  const text = readInstaller();

  assert.match(
    text,
    /\/var\/backups\/sovereign-nginx/,
    'installer must write backups under /var/backups/sovereign-nginx',
  );

  assert.match(
    text,
    /nginx -t/,
    'installer must run nginx -t before reloading',
  );

  assert.match(
    text,
    /restore_backup/,
    'installer must call a restore function when nginx -t fails',
  );
});

test('installer: enforces an auth probe that fails closed', () => {
  const text = readInstaller();

  // The post-install probe is what catches a silently-broken map. The
  // installer must refuse to print DONE if /mcp answers anything other
  // than 401 without a key.
  assert.match(
    text,
    /curl[^|]*https:\/\/[^\/]*\/mcp/,
    'installer must probe https://openhands.arelorian.de/mcp after reload',
  );

  assert.match(
    text,
    /expected 401/,
    'installer must assert the unauthenticated probe returns 401 (gate enforced)',
  );
});

test('installer: never echoes the API key value', () => {
  const text = readInstaller();

  // We allow echoing the sha256 fingerprint (KEY_FINGERPRINT) but never
  // the raw key. The following patterns would each indicate a leak.
  assert.doesNotMatch(
    text,
    /echo\s+"?\$KEY_VALUE_FOR_WRITE/,
    'installer must not echo the key value directly',
  );

  assert.doesNotMatch(
    text,
    /cat\s+\$KEY_FILE/,
    'installer must not cat the key file (would expose it in process listings / shell history)',
  );
});
