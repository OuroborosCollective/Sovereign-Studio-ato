#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const REPORT_DIR = '.security-reports';
const REPORT_PATH = path.join(REPORT_DIR, 'sovereign-live-path-contract.json');
const ROOTS = ['src'];

const report = {
  name: 'Sovereign Live Path Scan',
  generatedAt: new Date().toISOString(),
  status: 'unknown',
  scannedFiles: 0,
  checks: [],
  warnings: [],
  errors: [],
};

const IGNORED_PARTS = new Set([
  'node_modules',
  'dist',
  'build',
  'coverage',
  '.git',
  '.gradle',
]);

const LIVE_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs']);

const LIVE_ALLOWED_TEST_PATTERNS = [
  /\.test\.[cm]?[tj]sx?$/,
  /\.spec\.[cm]?[tj]sx?$/,
  /__tests__/,
  /test-utils/,
  /testing/,
];

const TEXT_ALLOWED_PATHS = [
  'src/features/product/runtime/sovereignTelemetry.ts',
];

const OLD_DOM_INSTALLER_PATTERN = /installMobileAgentMonitor|installMobileMoreMenu|installMobileSetupDrawer|installMobileWorkspaceOrder|installMobileRuntimeModules/;
const RUNTIME_DOM_MUTATION_PATTERN = /MutationObserver|querySelectorAll\(|querySelector\(|dispatchEvent\(new MouseEvent|\.click\(\)/;
const TEST_DOUBLE_PATTERN = /vi\.mock\(|jest\.mock\(|mockImplementation\(|mockResolvedValue\(|mockRejectedValue\(/;
const PLACEHOLDER_PATTERN = /TODO_PLACEHOLDER|FAKE_IMPLEMENTATION|DUMMY_IMPLEMENTATION|throw new Error\(['"]not implemented|return null;\s*\/\/\s*placeholder/i;
const SECRET_PATTERN = /ghp_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._~+/=-]{10,}/;
const NETWORK_TRUTH_PATTERN = /fetch\(['"]https?:\/\/|axios\.|XMLHttpRequest/;

function exists(filePath) {
  return fs.existsSync(filePath);
}

function read(filePath) {
  return exists(filePath) ? fs.readFileSync(filePath, 'utf8') : '';
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

function isIgnoredPath(filePath) {
  const parts = filePath.split(path.sep);
  return parts.some((part) => IGNORED_PARTS.has(part));
}

function isTestPath(filePath) {
  const normalized = filePath.replaceAll(path.sep, '/');
  return LIVE_ALLOWED_TEST_PATTERNS.some((pattern) => pattern.test(normalized));
}

function isTextAllowedPath(filePath) {
  const normalized = filePath.replaceAll(path.sep, '/');
  return TEXT_ALLOWED_PATHS.includes(normalized);
}

function isLiveFile(filePath) {
  return LIVE_EXTENSIONS.has(path.extname(filePath));
}

function walk(dir) {
  if (!exists(dir)) return [];
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (isIgnoredPath(fullPath)) continue;
    if (entry.isDirectory()) files.push(...walk(fullPath));
    else if (entry.isFile() && isLiveFile(fullPath)) files.push(fullPath);
  }
  return files;
}

function writeReport() {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  report.status = report.errors.length === 0 ? 'pass' : 'fail';
  fs.writeFileSync(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`);

  if (process.env.GITHUB_STEP_SUMMARY) {
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
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${lines.join('\n')}\n`);
  }

  console.log(JSON.stringify(report, null, 2));
}

function scanLiveFiles(files) {
  report.scannedFiles = files.length;

  for (const filePath of files) {
    const source = read(filePath);
    const normalized = filePath.replaceAll(path.sep, '/');
    const testFile = isTestPath(filePath);
    const textAllowed = isTextAllowedPath(filePath);

    if (SECRET_PATTERN.test(source)) {
      fail(`secret:${normalized}`, 'Secret-like value found in repository live path.', { filePath: normalized });
    }

    if (!testFile && TEST_DOUBLE_PATTERN.test(source)) {
      fail(`test-double:${normalized}`, 'Test-double API appears in non-test live path.', { filePath: normalized });
    }

    if (!testFile && PLACEHOLDER_PATTERN.test(source)) {
      fail(`placeholder:${normalized}`, 'Placeholder implementation marker appears in non-test live path.', { filePath: normalized });
    }

    if (OLD_DOM_INSTALLER_PATTERN.test(source)) {
      if (normalized === 'src/appShellContract.test.ts') {
        pass(`dom-installer-regression-token:${normalized}`, 'Old DOM installer tokens are allowed in regression test only.', { filePath: normalized });
      } else {
        fail(`old-dom-installer:${normalized}`, 'Old mobile DOM installer token appears outside the approved regression test.', { filePath: normalized });
      }
    }

    if (!testFile && !textAllowed && /\bmock\b|\bstub\b|\bfacade\b/i.test(source)) {
      warn(`live-path-wording:${normalized}`, 'Live file contains mock/stub/facade wording. Review that this is not a live fake truth path.', { filePath: normalized });
    }

    if (!testFile && RUNTIME_DOM_MUTATION_PATTERN.test(source)) {
      if (normalized === 'src/main.tsx' || normalized === 'src/global-runtime-monitor.tsx') {
        pass(`allowed-dom-runtime:${normalized}`, 'DOM access is limited to approved shell/monitor boot path.', { filePath: normalized });
      } else {
        warn(`dom-access:${normalized}`, 'DOM access appears in live code. Ensure it is not used as truth path or auto-click driver.', { filePath: normalized });
      }
    }

    if (!testFile && NETWORK_TRUTH_PATTERN.test(source)) {
      if (/github|workflow|externalMemory|fetchWorkflow|publishPackage/i.test(normalized)) {
        pass(`network-runtime:${normalized}`, 'Network access appears in an approved integration runtime.', { filePath: normalized });
      } else {
        warn(`network-runtime:${normalized}`, 'Network access appears in live code. Review runtime validation and error handling.', { filePath: normalized });
      }
    }
  }
}

function runRequiredPathChecks() {
  if (!exists('src/main.tsx')) fail('required:main', 'src/main.tsx is missing.');
  else {
    const main = read('src/main.tsx');
    if (OLD_DOM_INSTALLER_PATTERN.test(main)) fail('main:old-dom-installers', 'main.tsx must not boot old DOM installer modules.');
    else pass('main:old-dom-installers', 'main.tsx does not boot old DOM installer modules.');

    if (/installViewportRuntime/.test(main)) pass('main:viewport-runtime', 'Viewport runtime is installed.');
    else fail('main:viewport-runtime', 'Viewport runtime installation is missing.');

    if (/installCodeWorkspacePersistenceRuntime/.test(main)) pass('main:persistence-runtime', 'Workspace persistence runtime is installed.');
    else fail('main:persistence-runtime', 'Workspace persistence runtime installation is missing.');
  }

  if (exists('src/global-runtime-monitor.tsx')) {
    const monitor = read('src/global-runtime-monitor.tsx');
    if (/sovereign:runtime-coach-state/.test(monitor)) pass('monitor:coach-bus', 'Global monitor reads coach state events.');
    else fail('monitor:coach-bus', 'Global monitor must read coach state events.');

    if (/sovereign:telemetry-event/.test(monitor)) pass('monitor:telemetry-bus', 'Global monitor reads telemetry events.');
    else fail('monitor:telemetry-bus', 'Global monitor must read telemetry events.');
  } else {
    warn('monitor:file-missing', 'Global monitor file is missing. One central monitor is preferred.');
  }

  if (exists('src/App.tsx')) {
    const app = read('src/App.tsx');
    if (/runSequentialStep/.test(app)) pass('app:sequential-runtime', 'App uses sequential runtime steps.');
    else fail('app:sequential-runtime', 'App must route critical actions through sequential runtime.');

    if (/pushTelemetry/.test(app)) pass('app:telemetry', 'App publishes telemetry.');
    else fail('app:telemetry', 'App must publish telemetry.');

    if (/stripTokenFromText/.test(app)) pass('app:token-redaction', 'App redacts token-like text from visible/runtime messages.');
    else fail('app:token-redaction', 'App must redact token-like text from visible/runtime messages.');
  }
}

function run() {
  const files = ROOTS.flatMap(walk);
  if (!files.length) fail('scanner:no-files', 'No live files found to scan.', { roots: ROOTS });
  else pass('scanner:files-found', 'Live files found for scan.', { count: files.length, roots: ROOTS });

  scanLiveFiles(files);
  runRequiredPathChecks();
}

try {
  run();
} catch (error) {
  fail('scanner:unexpected-error', 'Live path scanner crashed.', { error: String(error) });
} finally {
  writeReport();
}

if (report.errors.length > 0) process.exit(1);
