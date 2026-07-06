#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const REPORT_DIR = '.security-reports';
const REPORT_PATH = path.join(REPORT_DIR, 'sovereign-live-path-contract.json');
const SRC_ROOT = 'src';

const report = {
  name: 'Sovereign Live Path Scan',
  generatedAt: new Date().toISOString(),
  status: 'unknown',
  scannedFiles: 0,
  checks: [],
  warnings: [],
  errors: [],
};

const legacyMobileModules = [
  'mobile-agent-monitor',
  'mobile-more-menu',
  'mobile-setup-drawer',
  'mobile-workspace-order',
  'mobile-operator-coach',
  'mobile-workbench-console',
];

const ignoredDirs = new Set(['node_modules', 'dist', 'build', 'coverage', '.git', '.gradle']);
const liveExtensions = new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs']);
const testPathPattern = /\.test\.[cm]?[tj]sx?$|\.spec\.[cm]?[tj]sx?$|__tests__|test-utils|testing/;
const oldBootMarker = /installMobile[A-Za-z0-9]+/;
const placeholderMarker = /TODO_PLACEHOLDER|FAKE_IMPLEMENTATION|DUMMY_IMPLEMENTATION|not implemented/i;
const testDoubleMarker = /vi\.mock\(|jest\.mock\(|mockImplementation\(/;

function exists(filePath) {
  return fs.existsSync(filePath);
}

function read(filePath) {
  return exists(filePath) ? fs.readFileSync(filePath, 'utf8') : '';
}

function normalize(filePath) {
  return filePath.replaceAll(path.sep, '/');
}

function pass(id, message, details = {}) {
  report.checks.push({ id, ok: true, message, details });
}

function fail(id, message, details = {}) {
  report.checks.push({ id, ok: false, message, details });
  report.errors.push({ id, message, details });
}

function warn(id, message, details = {}) {
  report.warnings.push({ id, message, details });
}

function isIgnored(filePath) {
  return filePath.split(path.sep).some((part) => ignoredDirs.has(part));
}

function isLiveFile(filePath) {
  return liveExtensions.has(path.extname(filePath));
}

function isTestFile(filePath) {
  return testPathPattern.test(normalize(filePath));
}

function walk(dir) {
  if (!exists(dir)) return [];
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (isIgnored(fullPath)) continue;
    if (entry.isDirectory()) files.push(...walk(fullPath));
    else if (entry.isFile() && isLiveFile(fullPath)) files.push(fullPath);
  }
  return files;
}

function safeSummaryPath() {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY;
  if (typeof summaryPath !== 'string' || !summaryPath.trim()) return null;
  const resolved = path.resolve(summaryPath);
  if (!path.isAbsolute(resolved)) return null;
  if (path.basename(resolved) !== 'summary.md') return null;
  return resolved;
}

function writeReport() {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  report.status = report.errors.length === 0 ? 'pass' : 'fail';
  fs.writeFileSync(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`);

  const summary = safeSummaryPath();
  if (summary) {
    const lines = [
      '## Sovereign Live Path Scan',
      '',
      `Status: **${report.status}**`,
      `Scanned files: **${report.scannedFiles}**`,
      `Checks: **${report.checks.length}**`,
      `Errors: **${report.errors.length}**`,
      `Warnings: **${report.warnings.length}**`,
      '',
      '### Errors',
      ...(report.errors.length ? report.errors.map((item) => `- ${item.id}: ${item.message}`) : ['- none']),
      '',
      '### Warnings',
      ...(report.warnings.length ? report.warnings.map((item) => `- ${item.id}: ${item.message}`) : ['- none']),
      '',
    ];
    fs.appendFileSync(summary, `${lines.join('\n')}\n`);
  }

  console.log(JSON.stringify(report, null, 2));
}

function scanFiles(files) {
  report.scannedFiles = files.length;

  for (const filePath of files) {
    const source = read(filePath);
    const normalized = normalize(filePath);
    const isTest = isTestFile(filePath);
    const isLegacyMobileModule = legacyMobileModules.some((moduleName) => normalized === `src/${moduleName}.ts`);

    if (!isTest && testDoubleMarker.test(source)) {
      fail(`test-double:${normalized}`, 'Test-double API appears in non-test live path.', { filePath: normalized });
    }

    if (!isTest && placeholderMarker.test(source)) {
      fail(`placeholder:${normalized}`, 'Placeholder implementation marker appears in non-test live path.', { filePath: normalized });
    }

    if (oldBootMarker.test(source)) {
      if (isTest) {
        pass(`legacy-marker-test:${normalized}`, 'Legacy mobile boot markers are allowed in regression tests.', { filePath: normalized });
      } else if (isLegacyMobileModule) {
        warn(`legacy-mobile-module:${normalized}`, 'Legacy mobile DOM module still exists. It is allowed only while absent from main.tsx boot path.', { filePath: normalized });
      } else {
        warn(`legacy-marker:${normalized}`, 'Legacy mobile marker appears outside boot path. Review before reusing it.', { filePath: normalized });
      }
    }
  }
}

function scanMainBootPath() {
  const mainPath = 'src/main.tsx';
  if (!exists(mainPath)) {
    fail('main:missing', 'src/main.tsx is missing.');
    return;
  }

  const source = read(mainPath);

  for (const moduleName of legacyMobileModules) {
    const importToken = `./${moduleName}`;
    if (source.includes(importToken)) {
      fail(`main:legacy-import:${moduleName}`, `main.tsx must not import legacy mobile module ${moduleName}.`, { moduleName });
    } else {
      pass(`main:no-legacy-import:${moduleName}`, `main.tsx does not import ${moduleName}.`, { moduleName });
    }
  }

  if (/installViewportRuntime/.test(source)) pass('main:viewport-runtime', 'Viewport runtime is installed.');
  else fail('main:viewport-runtime', 'Viewport runtime installation is missing.');

  if (/installCodeWorkspacePersistenceRuntime/.test(source)) pass('main:persistence-runtime', 'Workspace persistence runtime is installed.');
  else fail('main:persistence-runtime', 'Workspace persistence runtime installation is missing.');
}

function scanRuntimeContracts() {
  const app = read('src/App.tsx');
  const builder = read('src/features/product/containers/BuilderContainer.tsx');
  const monitor = read('src/global-runtime-monitor.tsx');

  if (/BuilderContainer/.test(app)) pass('app:builder-live-path', 'App routes live work to BuilderContainer.');
  else fail('app:builder-live-path', 'App must route live work to BuilderContainer.');

  if (/appendActionEvent|SovereignActionStreamPanel/.test(builder)) pass('builder:action-stream-runtime', 'Builder publishes route/action state through the action stream.');
  else fail('builder:action-stream-runtime', 'Builder must publish route/action state through the action stream.');

  if (/addLog|appendChatLine|buildLocalExecutorStatusAnswer/.test(builder)) pass('builder:runtime-feedback', 'Builder keeps runtime feedback visible in chat.');
  else fail('builder:runtime-feedback', 'Builder must keep runtime feedback visible in chat.');

  if (/stripTokenFromText|stripSecrets|validateGitHubTokenForRepo|validateGitHubTokenFormat/.test(builder)) pass('builder:redaction-and-access-validation', 'Builder validates/redacts visible runtime access values.');
  else fail('builder:redaction-and-access-validation', 'Builder must validate/redact visible runtime access values.');

  if (monitor) {
    if (/sovereign:runtime-coach-state/.test(monitor)) pass('monitor:coach-bus', 'Global monitor reads coach state events.');
    else fail('monitor:coach-bus', 'Global monitor must read coach state events.');

    if (/sovereign:telemetry-event/.test(monitor)) pass('monitor:telemetry-bus', 'Global monitor reads telemetry events.');
    else fail('monitor:telemetry-bus', 'Global monitor must read telemetry events.');
  } else {
    warn('monitor:missing', 'Global monitor file is missing. One central monitor is preferred.');
  }
}

function run() {
  const files = walk(SRC_ROOT);
  if (!files.length) fail('scanner:no-files', 'No src live files found.', { root: SRC_ROOT });
  else pass('scanner:files-found', 'Src live files found for scan.', { count: files.length });

  scanFiles(files);
  scanMainBootPath();
  scanRuntimeContracts();
}

try {
  run();
} catch (error) {
  fail('scanner:unexpected-error', 'Live path scanner crashed.', { error: String(error) });
} finally {
  writeReport();
}

if (report.errors.length > 0) process.exit(1);
