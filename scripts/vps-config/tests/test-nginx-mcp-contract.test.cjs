'use strict';

// Contract test for scripts/vps-config/nginx/.
//
// This test asserts the structural and secret-handling contract of the
// nginx reverse-proxy templates for openhands.arelorian.de. It does NOT
// require a running VPS or a live MCP backend; it only inspects the files
// in scripts/vps-config/nginx/ that are committed to the repository.
//
// Why this exists:
//   The repo owns the canonical nginx config. The installer
//   (scripts/vps-config/setup-nginx.sh) copies these files to the VPS at
//   deploy time. Any change here is operator-visible immediately. A
//   contract test makes the trust surface explicit and prevents accidental
//   regressions such as:
//     - accidentally re-exposing legacy /sse or /messages paths;
//     - accidentally adding Bearer auth (which is intentionally NOT yet
//       approved; see issue #1187 body);
//     - accidentally committing a real API key into the template;
//     - accidentally removing the X-API-Key header check.

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const NGINX_DIR = path.resolve(__dirname, '..', 'nginx');
const SERVER_CONF = path.join(NGINX_DIR, 'openhands.arelorian.de.conf');
const MAP_CONF = path.join(NGINX_DIR, '00-openhands-mcp-auth-map.conf');

function readFileOrFail(p) {
  assert.ok(
    fs.existsSync(p),
    `expected nginx template file to exist: ${p}`,
  );
  return fs.readFileSync(p, 'utf8');
}

test('nginx server template: required MCP contract is present', () => {
  const text = readFileOrFail(SERVER_CONF);

  assert.match(
    text,
    /location\s*=\s*\/mcp\s*\{/,
    'server template must define an exact-match location for /mcp (not a prefix)',
  );

  assert.match(
    text,
    /proxy_pass\s+http:\/\/127\.0\.0\.1:8090\/mcp\s*;/,
    'location = /mcp must proxy to 127.0.0.1:8090/mcp (loopback only)',
  );

  assert.match(
    text,
    /\$mcp_authorized\s*!=\s*1/,
    'location = /mcp must check $mcp_authorized != 1 before proxying',
  );

  assert.match(
    text,
    /proxy_set_header\s+X-API-Key\s+\$http_x_api_key\s*;/,
    'location = /mcp must forward the validated X-API-Key to the backend',
  );

  assert.match(
    text,
    /return\s+401\s*;/,
    'unauthenticated /mcp requests must return 401 (no implicit deny)',
  );

  assert.match(
    text,
    /listen\s+443\s+ssl\s+http2/,
    'server must keep TLS 1.2/1.3 termination on 443',
  );
});

test('nginx server template: legacy MCP transports are NOT exposed', () => {
  const text = readFileOrFail(SERVER_CONF);

  assert.doesNotMatch(
    text,
    /location\s+(\^~|~|\/sse|\/messages)/,
    'server template must not define /sse or /messages proxying; Streamable-HTTP /mcp is the only MCP transport',
  );

  // Negative proxy_pass to 8090 is forbidden except for the exact-match
  // /mcp location, which is asserted in the previous test. We use a
  // lookbehind here so the existing `proxy_pass http://127.0.0.1:8090/mcp;`
  // does not trip the rule.
  assert.doesNotMatch(
    text,
    /proxy_pass\s+http:\/\/127\.0\.0\.1:8090(?!\/mcp\s*;)/,
    'no proxy_pass to 8090 may exist for any path other than the exact-match /mcp',
  );
});

test('nginx server template: does NOT introduce Bearer auth', () => {
  const text = readFileOrFail(SERVER_CONF);

  assert.doesNotMatch(
    text,
    /\$http_authorization\b/,
    'server template must not reference $http_authorization (Bearer auth is not approved for /mcp)',
  );

  assert.doesNotMatch(
    text,
    /proxy_set_header\s+Authorization\b/,
    'server template must not forward an Authorization header to the backend',
  );
});

test('nginx server template: contains no real secrets', () => {
  const text = readFileOrFail(SERVER_CONF);

  // This regex deliberately looks for accidental leakage. It only flags
  // strings that look like 32+ char hex/base64 secrets inline. It is not
  // a substitute for the hardcode scanner, but it catches the worst class
  // of mistake before a merge.
  assert.doesNotMatch(
    text,
    /[A-Za-z0-9_\-]{32,}\s+1\s*;/,
    'server template must not inline any X-API-Key value (the key lives only on the VPS in /opt/sovereign-owner-managed/...)',
  );
});

test('nginx http-context map: defines $mcp_authorized and includes the key file', () => {
  const text = readFileOrFail(MAP_CONF);

  assert.match(
    text,
    /map\s+\$http_x_api_key\s+\$mcp_authorized\s*\{/,
    'map directive must bind $http_x_api_key to $mcp_authorized (stable contract identifier)',
  );

  assert.match(
    text,
    /default\s+0\s*;/,
    'map must default to 0 so missing or unknown keys are denied',
  );

  assert.match(
    text,
    /include\s+\/etc\/nginx\/conf\.d\/openhands-mcp-api-key\.map\s*;/,
    'map must include the operator-generated .map file; the install path is part of the contract',
  );
});

test('nginx templates: do not embed loopback-overriding addresses', () => {
  const serverText = readFileOrFail(SERVER_CONF);
  const mapText = readFileOrFail(MAP_CONF);

  // Defence-in-depth: no public IP literal may appear as a proxy_pass
  // target or as a literal hostname mapping.
  assert.doesNotMatch(
    serverText,
    /proxy_pass\s+http:\/\/(?!127\.0\.0\.1)(?!unix:)/,
    'no proxy_pass may target a non-loopback address',
  );
  assert.doesNotMatch(
    mapText,
    /\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b/,
    'map template must not contain any IP literal',
  );
});
