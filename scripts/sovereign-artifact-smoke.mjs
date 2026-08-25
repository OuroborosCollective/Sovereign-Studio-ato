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
const REQUIRED_COVERAGE_FILES = [
  'src/App.test.tsx',
  'backend/tests/test_agent_runtime_routes.py',
  'scripts/tests/test_frontend_test_gate.py',
  'tests/e2e/frontend-endpoint-contract-smoke.spec.ts',
];
const REQUIRED_COVERAGE_ROOTS = ['src', 'backend/tests', 'scripts/tests', 'tests/e2e'];

function validateCoverageMap(content) {
  let report;
  try {
    report = JSON.parse(content);
  } catch {
    return 'coverage map is not valid JSON';
  }
  if (report.schemaVersion !== 'sovereign.test-coverage-map.v2') return 'coverage map schema is not v2';
  if (!Number.isInteger(report.totalTestFiles) || report.totalTestFiles < 1) return 'coverage map has no positive totalTestFiles';
  if (!Array.isArray(report.files) || report.files.length !== report.totalTestFiles) return 'coverage map file count does not match totalTestFiles';
  const files = report.files.map((entry) => entry?.file).filter((file) => typeof file === 'string');
  if (new Set(files).size !== files.length) return 'coverage map contains duplicate test paths';
  for (const file of REQUIRED_COVERAGE_FILES) {
    if (!files.includes(file)) return `coverage map is missing representative test ${file}`;
  }
  for (const testRoot of REQUIRED_COVERAGE_ROOTS) {
    if (!Number.isInteger(report.testRoots?.[testRoot]) || report.testRoots[testRoot] < 1) {
      return `coverage map is missing test root ${testRoot}`;
    }
  }
  return true;
}

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
checkFile('release coverage map', 'dist/generated/test-coverage-map.json', validateCoverageMap);
checkDirectory('android project', 'android/app');
checkFile('android webview index', 'android/app/src/main/assets/public/index.html', (content) => {
  if (!content.includes('<script')) return 'android index has no script tag';
  if (!content.includes('<div id="root"')) return 'android index has no React root';
  return true;
});
checkFile('android coverage map', 'android/app/src/main/assets/public/generated/test-coverage-map.json', validateCoverageMap);

if (failures.length > 0) {
  console.error('Sovereign E2E smoke failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log('Sovereign E2E smoke passed: build artifacts and Android handoff are present.');
