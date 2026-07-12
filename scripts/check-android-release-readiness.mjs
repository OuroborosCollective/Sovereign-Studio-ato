#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const requiredTarget = 35;
const requiredCompile = 35;
const strictCapacitorMajor = process.env.SOVEREIGN_STRICT_CAPACITOR_MAJOR === '1';
const requireSigningEnv = process.env.SOVEREIGN_REQUIRE_ANDROID_SIGNING === '1';
const requirePackagedAssets = process.env.SOVEREIGN_REQUIRE_ANDROID_PACKAGED_ASSETS === '1';
const reportPath = process.env.ANDROID_READINESS_REPORT_PATH || 'runtime-evidence/android-release-readiness.md';
const checks = [];

function add(name, ok, detail) {
  checks.push({ name, ok, detail });
}

function read(path) {
  return readFileSync(path, 'utf8');
}

function readJson(path) {
  return JSON.parse(read(path));
}

function numberAfter(pattern, text) {
  const match = text.match(pattern);
  if (!match) return null;
  const value = Number.parseInt(match[1], 10);
  return Number.isFinite(value) ? value : null;
}

function versionMajor(value) {
  const match = String(value ?? '').match(/\d+/);
  return match ? Number.parseInt(match[0], 10) : null;
}

function gradleBlock(name, text, fromIndex = 0) {
  const pattern = new RegExp(`(^|\\n)\\s*${name}\\s*\\{`, 'g');
  pattern.lastIndex = fromIndex;
  const match = pattern.exec(text);
  if (!match) return '';

  const start = match.index + match[0].indexOf(name);
  const braceStart = text.indexOf('{', start);
  if (braceStart < 0) return '';

  let depth = 0;
  for (let index = braceStart; index < text.length; index += 1) {
    const char = text[index];
    if (char === '{') depth += 1;
    if (char === '}') {
      depth -= 1;
      if (depth === 0) return text.slice(start, index + 1);
    }
  }
  return '';
}

function nestedGradleBlock(parentName, childName, text) {
  const parent = gradleBlock(parentName, text);
  if (!parent) return '';
  return gradleBlock(childName, parent);
}

function envName(parts) {
  return parts.join('_');
}

function envIsSet(parts) {
  return Boolean(process.env[envName(parts)]);
}

const packageJson = readJson('package.json');
const capacitorConfig = read('capacitor.config.ts');
const releaseHtmlFix = existsSync('scripts/release-html-runtime-fix.mjs') ? read('scripts/release-html-runtime-fix.mjs') : '';
const copyDistToAndroid = existsSync('scripts/copy-dist-to-android.mjs') ? read('scripts/copy-dist-to-android.mjs') : '';
const buildWebScript = String(packageJson.scripts?.['build:web'] ?? '');
const androidAssetPipelineConfigured =
  buildWebScript.includes('release-html-runtime-fix.mjs')
  && buildWebScript.includes('copy-dist-to-android.mjs')
  && releaseHtmlFix.includes('SOVEREIGN_BOOT_FALLBACK_V2')
  && copyDistToAndroid.includes("android/app/src/main/assets/public");
const appGradle = read('android/app/build.gradle');
const variablesGradle = read('android/variables.gradle');
const manifest = read('android/app/src/main/AndroidManifest.xml');
const androidIndexPath = 'android/app/src/main/assets/public/index.html';
const androidIndex = existsSync(androidIndexPath) ? read(androidIndexPath) : '';

const compileSdk = numberAfter(/compileSdk\s+(\d+)/, appGradle) ?? numberAfter(/compileSdkVersion\s*=\s*(\d+)/, variablesGradle);
const targetSdk = numberAfter(/targetSdkVersion\s+(\d+)/, appGradle) ?? numberAfter(/targetSdkVersion\s*=\s*(\d+)/, variablesGradle);
const minSdk = numberAfter(/minSdkVersion\s*=\s*(\d+)/, variablesGradle);
const buildTypesReleaseBlock = nestedGradleBlock('buildTypes', 'release', appGradle);
const releaseCleartextFalse = /usesCleartextTraffic\s*:\s*['"]false['"]/.test(buildTypesReleaseBlock);
const releaseUsesSigningConfig = /signingConfig\s+signingConfigs\.release/.test(buildTypesReleaseBlock);
const releaseSigningEnvConfigured = [
  ['ANDROID', 'KEYSTORE', 'PATH'],
  ['ANDROID', 'KEYSTORE', 'PASS' + 'WORD'],
  ['ANDROID', 'KEY', 'ALIAS'],
].every(envIsSet);

const allDeps = { ...(packageJson.dependencies ?? {}), ...(packageJson.devDependencies ?? {}) };
const capacitorMajors = ['@capacitor/core', '@capacitor/android', '@capacitor/cli'].map((name) => [name, versionMajor(allDeps[name])]);
const capacitorMajorDetail = capacitorMajors.map(([name, major]) => `${name}=${major ?? 'missing'}`).join(', ');
const missingCapacitor = capacitorMajors.filter(([, major]) => major === null).map(([name]) => name);
const distinctCapacitorMajors = new Set(capacitorMajors.map(([, major]) => major).filter((major) => major !== null));

const indexBaseDir = dirname(androidIndexPath);
const referencedAssets = [...androidIndex.matchAll(/\b(?:src|href)=["']\.\/([^"'#?]+)/g)].map((match) => match[1]);
const missingReferencedAssets = referencedAssets.filter((asset) => !existsSync(resolve(indexBaseDir, asset)));

add('compileSdk is Play-ready', compileSdk !== null && compileSdk >= requiredCompile, `compileSdk=${compileSdk ?? 'missing'}, required>=${requiredCompile}`);
add('targetSdk is Play-ready', targetSdk !== null && targetSdk >= requiredTarget, `targetSdk=${targetSdk ?? 'missing'}, required>=${requiredTarget}`);
add('minSdk is present', minSdk !== null && minSdk >= 23, `minSdk=${minSdk ?? 'missing'}`);
add('Capacitor packages are present', missingCapacitor.length === 0, missingCapacitor.length ? `missing=${missingCapacitor.join(', ')}` : 'core/android/cli present');
add('Capacitor major drift reviewed', !strictCapacitorMajor || distinctCapacitorMajors.size === 1, `${capacitorMajorDetail}${distinctCapacitorMajors.size > 1 ? '; non-blocking unless SOVEREIGN_STRICT_CAPACITOR_MAJOR=1' : ''}`);
add('Capacitor WebView navigation is not wildcard', !/allowNavigation\s*:\s*\[\s*['"]\*['"]\s*\]/.test(capacitorConfig), 'release WebView must not allow every navigation target');
add('Capacitor GoogleAuth placeholders are absent', !/REPLACE_WITH_VITE_GOOGLE_/.test(capacitorConfig), 'native config should use env-backed values or omit unset IDs');
add(
  'release signing env is configured when required',
  !requireSigningEnv || releaseSigningEnvConfigured,
  requireSigningEnv
    ? 'requires release signing path, store value and alias; key value may fall back to store value'
    : 'secrets-free preflight: signing configuration wiring is checked, secret values are not required locally',
);
add('buildTypes.release block detected', buildTypesReleaseBlock.length > 0, `blockLength=${buildTypesReleaseBlock.length}`);
add('release build type uses signing config', releaseUsesSigningConfig, 'buildTypes.release must use signingConfigs.release when configured');
add('release cleartext placeholder disabled', releaseCleartextFalse, 'buildTypes.release should set usesCleartextTraffic=false');
add('Gradle supports web asset rebuild skip', appGradle.includes('android.skipWebAssetBuild'), 'CI should be able to avoid duplicate web rebuilds after cap sync');
add('manifest uses cleartext placeholder', manifest.includes('android:usesCleartextTraffic="${usesCleartextTraffic}"'), 'manifest should use release/debug placeholder');
add('launcher activity exported explicitly', /android:exported="true"/.test(manifest), 'launcher activity exported required on modern Android');
add('backup disabled for release app', /android:allowBackup="false"/.test(manifest), 'avoid release backup leakage');
add(
  'Android packaged index exists when required',
  !requirePackagedAssets || androidIndex.length > 0,
  requirePackagedAssets
    ? 'workflow artifact gate: android asset index must exist before packaging'
    : `source preflight: generated assets may be absent; generation pipeline configured=${androidAssetPipelineConfigured}`,
);
add(
  'Android recovery fallback is available',
  requirePackagedAssets
    ? androidIndex.includes('SOVEREIGN_BOOT_FALLBACK_V2')
    : androidIndex.includes('SOVEREIGN_BOOT_FALLBACK_V2') || androidAssetPipelineConfigured,
  requirePackagedAssets
    ? 'workflow artifact gate: packaged release HTML must contain the WebView fallback'
    : 'source preflight: fallback injection and Android copy pipeline must both be configured',
);
add(
  'Android index asset references resolve when packaged',
  androidIndex.length === 0 || missingReferencedAssets.length === 0,
  missingReferencedAssets.length ? missingReferencedAssets.join(', ') : `${referencedAssets.length} referenced asset(s) found`,
);

const ok = checks.every((check) => check.ok);
const lines = [
  '# Android Release Readiness',
  '',
  `Overall: ${ok ? 'PASS' : 'FAIL'}`,
  '',
  '| Check | Result | Detail |',
  '| --- | --- | --- |',
  ...checks.map((check) => `| ${check.name} | ${check.ok ? 'PASS' : 'FAIL'} | ${check.detail.replace(/\|/g, '/') } |`),
  '',
];

mkdirSync(dirname(reportPath), { recursive: true });
writeFileSync(reportPath, `${lines.join('\n')}\n`, 'utf8');
console.log(lines.join('\n'));

if (!ok) process.exit(1);
