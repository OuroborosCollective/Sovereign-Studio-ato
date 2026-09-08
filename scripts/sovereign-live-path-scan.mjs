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

function exists(filePath) { return fs.existsSync(filePath); }
function read(filePath) { return exists(filePath) ? fs.readFileSync(filePath, 'utf8') : ''; }
function normalize(filePath) { return filePath.replaceAll(path.sep, '/'); }
function pass(id, message, details = {}) { report.checks.push({ id, ok: true, message, details }); }
function fail(id, message, details = {}) {
  report.checks.push({ id, ok: false, message, details });
  report.errors.push({ id, message, details });
}
function warn(id, message, details = {}) { report.warnings.push({ id, message, details }); }
function isIgnored(filePath) { return filePath.split(path.sep).some((part) => ignoredDirs.has(part)); }
function isLiveFile(filePath) { return liveExtensions.has(path.extname(filePath)); }
function isTestFile(filePath) { return testPathPattern.test(normalize(filePath)); }

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
  const runnerTemp = process.env.RUNNER_TEMP;

  if (typeof summaryPath !== 'string' || !summaryPath.trim()) return null;
  if (typeof runnerTemp !== 'string' || !runnerTemp.trim()) return null;

  const trustedRoot = path.resolve(runnerTemp);
  const resolved = path.resolve(summaryPath);
  const relativeToRoot = path.relative(trustedRoot, resolved);

  if (
    relativeToRoot === '..'
    || relativeToRoot.startsWith(`..${path.sep}`)
    || path.isAbsolute(relativeToRoot)
  ) {
    return null;
  }

  if (!/^step_summary_[A-Za-z0-9-]+$/.test(path.basename(resolved))) {
    return null;
  }

  return resolved;
}

function writeReport() {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  report.status = report.errors.length === 0 ? 'pass' : 'fail';
  fs.writeFileSync(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`);
  const summary = safeSummaryPath();
  if (summary) {
    fs.appendFileSync(summary, [
      '## Sovereign Live Path Scan', '',
      `Status: **${report.status}**`,
      `Scanned files: **${report.scannedFiles}**`,
      `Errors: **${report.errors.length}**`,
      `Warnings: **${report.warnings.length}**`, '',
      '### Errors',
      ...(report.errors.length ? report.errors.map((item) => `- ${item.id}: ${item.message}`) : ['- none']),
      '',
    ].join('\n') + '\n');
  }
  console.log(JSON.stringify(report, null, 2));
}

function scanFiles(files) {
  report.scannedFiles = files.length;
  for (const filePath of files) {
    const source = read(filePath);
    const normalized = normalize(filePath);
    const isTest = isTestFile(filePath);
    const isLegacyMobileModule = legacyMobileModules.some((name) => normalized === `src/${name}.ts`);
    if (!isTest && testDoubleMarker.test(source)) {
      fail(`test-double:${normalized}`, 'Test-double API appears in non-test live path.', { filePath: normalized });
    }
    if (!isTest && placeholderMarker.test(source)) {
      fail(`placeholder:${normalized}`, 'Placeholder implementation marker appears in non-test live path.', { filePath: normalized });
    }
    if (oldBootMarker.test(source)) {
      if (isTest) pass(`legacy-marker-test:${normalized}`, 'Legacy mobile boot markers are allowed in regression tests.');
      else if (isLegacyMobileModule) warn(`legacy-mobile-module:${normalized}`, 'Legacy mobile DOM module exists but must stay outside main boot.');
      else warn(`legacy-marker:${normalized}`, 'Legacy mobile marker appears outside the boot path.');
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
    if (source.includes(importToken)) fail(`main:legacy-import:${moduleName}`, `main.tsx must not import ${moduleName}.`);
    else pass(`main:no-legacy-import:${moduleName}`, `main.tsx does not import ${moduleName}.`);
  }
  if (/installViewportRuntime/.test(source)) pass('main:viewport-runtime', 'Viewport runtime is installed.');
  else fail('main:viewport-runtime', 'Viewport runtime installation is missing.');
  if (/installCodeWorkspacePersistenceRuntime/.test(source)) pass('main:persistence-runtime', 'Workspace persistence runtime is installed.');
  else fail('main:persistence-runtime', 'Workspace persistence runtime installation is missing.');
}

function scanRuntimeContracts() {
  const app = read('src/App.tsx');
  const release = read('src/features/release/PlayReleaseChat.tsx');
  const builder = read('src/features/product/containers/BuilderContainer.tsx');

  if (
    /PlayReleaseChat/.test(app)
    && /data-testid="sovereign-chat-app"/.test(app)
    && /data-layout="chat-first-agent-zero-background"/.test(app)
    && /data-primary-surface="play-release-chat"/.test(app)
    && /data-truth-scope="current-chat-session-only"/.test(app)
    && /EvidenceObservatoryAtlas/.test(app)
    && /window\.location\.pathname === '\/observatory'/.test(app)
    && !/RESTORE_LATEST_JOB/.test(app)
  ) {
    pass('app:current-session-live-path', 'App uses Play Release as current-session truth and keeps the observatory separate.');
  } else {
    fail('app:current-session-live-path', 'Default App must use current-session Play Release truth without automatic historical job adoption.');
  }

  if (
    /evaluateInputPolicy\(text\)/.test(release)
    && /fetchSovereignDirectLlmInterpretation/.test(release)
    && /deriveRepositoryActionFallback/.test(release)
    && /pendingRepositoryAction/.test(release)
    && /confirmPendingRepositoryAction/.test(release)
  ) pass('release:review-gated-action', 'Release chat guards input and requires a visible repository-action confirmation.');
  else fail('release:review-gated-action', 'Release chat must keep input guard and visible action confirmation on the live path.');

  if (
    /startRepositoryExecution/.test(release)
    && /prepareDraftPr/.test(release)
    && /createDraftPr/.test(release)
    && /readbackHeadSha/.test(release)
    && /Draft PR erstellen/.test(release)
  ) pass('release:draft-pr-runtime', 'Mission execution and Draft PR creation remain bound to backend/GitHub readback.');
  else fail('release:draft-pr-runtime', 'Release chat must execute mission → Agent → Draft PR → readback on the live path.');

  if (!/listJobs\(/.test(release) && !/RESTORE_LATEST_JOB/.test(release)) {
    pass('release:no-implicit-history-adoption', 'Release chat does not auto-adopt historical jobs as current truth.');
  } else {
    fail('release:no-implicit-history-adoption', 'Historical jobs must not become current release-chat truth implicitly.');
  }

  if (/fetchSovereignLlmRouteCatalog/.test(release) && /LLM Route/.test(release)) {
    pass('release:runtime-route-catalog', 'Release chat exposes the server-authoritative route catalog.');
  } else fail('release:runtime-route-catalog', 'Release chat must expose the live LLM route catalog.');

  if (/initiateGitHubOAuth/.test(release) && /GitHub sicher verbinden/.test(release)) {
    pass('release:github-consent', 'GitHub connection remains behind an explicit visible OAuth action.');
  } else fail('release:github-consent', 'GitHub connection must remain explicitly user-visible.');

  if (/SovereignActionStreamPanel|MonitorCommunicationDock/.test(builder)) {
    pass('builder:secondary-diagnostics-retained', 'Legacy Builder diagnostics remain available as a secondary maintained component.');
  } else warn('builder:secondary-diagnostics-missing', 'Builder diagnostics were not detected; verify secondary tooling before removal.');
}

function run() {
  const files = walk(SRC_ROOT);
  if (!files.length) fail('scanner:no-files', 'No src live files found.', { root: SRC_ROOT });
  else pass('scanner:files-found', 'Src live files found for scan.', { count: files.length });
  scanFiles(files);
  scanMainBootPath();
  scanRuntimeContracts();
}

try { run(); }
catch (error) { fail('scanner:unexpected-error', 'Live path scanner crashed.', { error: String(error) }); }
finally { writeReport(); }

if (report.errors.length > 0) process.exit(1);
