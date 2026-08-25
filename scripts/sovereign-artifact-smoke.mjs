#!/usr/bin/env node
/**
 * Sovereign E2E smoke gate.
 *
 * Checks the real build artifacts produced by the current Android-first
 * web/Capacitor app. This replaces the stale React-Native runner path that
 * no longer exists in this repository.
 */
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const failures = [];

function checkFile(label, relativePath, validate) {
  const absolutePath = path.join(root, relativePath);
  if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isFile()) {
    failures.push(`${label}: missing ${relativePath}`);
    return;
  }

  if (!validate) return;

  const content = fs.readFileSync(absolutePath, 'utf8');
  const result = validate(content);
  if (result !== true) failures.push(`${label}: ${result}`);
}

function checkDirectory(label, relativePath) {
  const absolutePath = path.join(root, relativePath);
  if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isDirectory()) {
    failures.push(`${label}: missing ${relativePath}`);
  }
}

checkFile('web build index', 'dist/index.html', (content) => {
  if (!content.includes('<script')) return 'index has no script tag';
  if (!content.includes('<div id="root"')) return 'index has no React root';
  return true;
});

checkDirectory('web build assets', 'dist/assets');
checkFile('release coverage map', 'dist/generated/test-coverage-map.json', (content) => {
  try {
    const report = JSON.parse(content);
    if (!Number.isInteger(report.totalTestFiles) || report.totalTestFiles < 1) return 'coverage map has no positive totalTestFiles';
    if (!Array.isArray(report.files) || report.files.length < 1) return 'coverage map has no files array';
    return true;
  } catch {
    return 'coverage map is not valid JSON';
  }
});
checkDirectory('android project', 'android/app');
checkFile('android webview index', 'android/app/src/main/assets/public/index.html', (content) => {
  if (!content.includes('<script')) return 'android index has no script tag';
  if (!content.includes('<div id="root"')) return 'android index has no React root';
  return true;
});
checkFile('android coverage map', 'android/app/src/main/assets/public/generated/test-coverage-map.json', (content) => {
  try {
    const report = JSON.parse(content);
    return Number.isInteger(report.totalTestFiles) && report.totalTestFiles > 0
      ? true
      : 'android coverage map has no positive totalTestFiles';
  } catch {
    return 'android coverage map is not valid JSON';
  }
});

if (failures.length > 0) {
  console.error('Sovereign E2E smoke failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log('Sovereign E2E smoke passed: build artifacts and Android handoff are present.');
