#!/usr/bin/env node
/**
 * Release OAuth Identity Gate (issue #1567)
 *
 * Fail-closed release gate for Android OAuth identity/branding:
 *   1. google_client_id must not contain a REPLACE_WITH_ placeholder
 *      (the real client ID must be injected via build config / CI secret).
 *   2. app_name / title_activity_main must not contain "NOCode"
 *      (user-visible branding is "Sovereign Studio").
 *
 * Checks the source strings.xml and, optionally, a merged release resources
 * file passed as an additional argument (e.g. the merged values.xml from a
 * Gradle release build).
 *
 * Usage:
 *   node scripts/release-oauth-identity-gate.mjs [extra-merged-strings.xml ...]
 *
 * Exit codes:
 *   0 - OAUTH_IDENTITY_GATE=PASS
 *   1 - OAUTH_IDENTITY_GATE=BLOCKED (violations printed)
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

export const PLACEHOLDER_PATTERN = /REPLACE_WITH_[A-Z0-9_]*/i;
export const LEGACY_BRAND_PATTERN = /nocode/i;

/** Extract <string name="...">value</string> entries from resources XML. */
export function extractStrings(xml) {
  const entries = new Map();
  const re = /<string\s+name="([^"]+)"[^>]*>([^<]*)<\/string>/g;
  let m;
  while ((m = re.exec(xml)) !== null) {
    entries.set(m[1], m[2]);
  }
  return entries;
}

/**
 * Check one strings XML source. Returns a list of violation strings
 * (empty array = pass).
 */
export function checkStringsXml(xml, label = 'strings.xml') {
  const violations = [];
  const strings = extractStrings(xml);

  const clientId = strings.get('google_client_id');
  if (clientId !== undefined && PLACEHOLDER_PATTERN.test(clientId)) {
    violations.push(
      `${label}: google_client_id still contains placeholder "${clientId}". ` +
        'Inject the real Google OAuth client ID via build config / CI secret before release.'
    );
  }

  for (const name of ['app_name', 'title_activity_main']) {
    const value = strings.get(name);
    if (value !== undefined && LEGACY_BRAND_PATTERN.test(value)) {
      violations.push(
        `${label}: ${name} contains legacy branding "${value}". ` +
          'User-visible app name must be "Sovereign Studio" (issue #1567).'
      );
    }
  }

  return violations;
}

export function runGate(files) {
  const violations = [];
  for (const file of files) {
    if (!fs.existsSync(file)) {
      violations.push(`${file}: required resource file not found.`);
      continue;
    }
    violations.push(...checkStringsXml(fs.readFileSync(file, 'utf8'), file));
  }
  return violations;
}

const isMain =
  process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname);

if (isMain) {
  const root = process.cwd();
  const sourceStrings = path.join(root, 'android/app/src/main/res/values/strings.xml');
  const extraFiles = process.argv.slice(2).map((f) => path.resolve(root, f));
  const files = [sourceStrings, ...extraFiles];

  const violations = runGate(files);

  if (violations.length > 0) {
    console.error('OAUTH_IDENTITY_GATE=BLOCKED');
    for (const v of violations) console.error(`  - ${v}`);
    process.exit(1);
  }
  console.log('OAUTH_IDENTITY_GATE=PASS');
  process.exit(0);
}
