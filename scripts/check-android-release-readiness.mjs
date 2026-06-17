#!/usr/bin/env node
import { readFileSync, writeFileSync } from 'node:fs';

const requiredTarget = 35;
const requiredCompile = 35;
const checks = [];

function add(name, ok, detail) {
  checks.push({ name, ok, detail });
}

function read(path) {
  return readFileSync(path, 'utf8');
}

function numberAfter(pattern, text) {
  const match = text.match(pattern);
  if (!match) return null;
  const value = Number.parseInt(match[1], 10);
  return Number.isFinite(value) ? value : null;
}

function gradleBlock(name, text) {
  const start = text.indexOf(`${name} {`);
  if (start < 0) return '';
  let depth = 0;
  for (let index = start; index < text.length; index += 1) {
    const char = text[index];
    if (char === '{') depth += 1;
    if (char === '}') {
      depth -= 1;
      if (depth === 0) return text.slice(start, index + 1);
    }
  }
  return '';
}

const appGradle = read('android/app/build.gradle');
const variablesGradle = read('android/variables.gradle');
const manifest = read('android/app/src/main/AndroidManifest.xml');

const compileSdk = numberAfter(/compileSdk\s+(\d+)/, appGradle) ?? numberAfter(/compileSdkVersion\s*=\s*(\d+)/, variablesGradle);
const targetSdk = numberAfter(/targetSdkVersion\s+(\d+)/, appGradle) ?? numberAfter(/targetSdkVersion\s*=\s*(\d+)/, variablesGradle);
const minSdk = numberAfter(/minSdkVersion\s*=\s*(\d+)/, variablesGradle);
const releaseBlock = gradleBlock('release', appGradle);
const releaseCleartextFalse = /usesCleartextTraffic\s*:\s*['"]false['"]/.test(releaseBlock);

add('compileSdk is Play-ready', compileSdk !== null && compileSdk >= requiredCompile, `compileSdk=${compileSdk ?? 'missing'}, required>=${requiredCompile}`);
add('targetSdk is Play-ready', targetSdk !== null && targetSdk >= requiredTarget, `targetSdk=${targetSdk ?? 'missing'}, required>=${requiredTarget}`);
add('minSdk is present', minSdk !== null && minSdk >= 23, `minSdk=${minSdk ?? 'missing'}`);
add('release signing env is configured', Boolean(process.env.ANDROID_KEYSTORE_PATH && process.env.ANDROID_KEYSTORE_PASSWORD && process.env.ANDROID_KEY_ALIAS && process.env.ANDROID_KEY_PASSWORD), 'requires ANDROID_KEYSTORE_PATH, ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD');
add('release build type uses signing config', /release\s*\{[\s\S]*signingConfig\s+signingConfigs\.release/.test(appGradle), 'release must use signingConfigs.release when configured');
add('release cleartext placeholder disabled', releaseCleartextFalse, 'release should set usesCleartextTraffic=false');
add('manifest uses cleartext placeholder', manifest.includes('android:usesCleartextTraffic="${usesCleartextTraffic}"'), 'manifest should use release/debug placeholder');
add('launcher activity exported explicitly', /android:exported="true"/.test(manifest), 'launcher activity exported required on modern Android');

const ok = checks.every((check) => check.ok);
const lines = [
  '# Android Release Readiness',
  '',
  `Overall: ${ok ? 'PASS' : 'FAIL'}`,
  '',
  '| Check | Result | Detail |',
  '| --- | --- | --- |',
  ...checks.map((check) => `| ${check.name} | ${check.ok ? 'PASS' : 'FAIL'} | ${check.detail.replace(/\|/g, '/')} |`),
  '',
];

writeFileSync('android-release-readiness.md', `${lines.join('\n')}\n`, 'utf8');
console.log(lines.join('\n'));

if (!ok) process.exit(1);
