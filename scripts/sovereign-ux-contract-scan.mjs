#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const REPORT_DIR = '.security-reports';
const REPORT_PATH = path.join(REPORT_DIR, 'sovereign-ux-contract.json');

const report = {
  name: 'Sovereign UX Contract Scan',
  generatedAt: new Date().toISOString(),
  status: 'unknown',
  checks: [],
  warnings: [],
  errors: [],
};

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

function requireFile(filePath, message) {
  if (exists(filePath)) pass(`file:${filePath}`, message, { filePath });
  else fail(`file:${filePath}`, `Missing required file: ${filePath}`, { filePath, message });
}

function requireText(filePath, pattern, id, message) {
  const source = read(filePath);
  if (pattern.test(source)) pass(id, message, { filePath });
  else fail(id, message, { filePath, pattern: String(pattern) });
}

function warnText(filePath, pattern, id, message) {
  const source = read(filePath);
  if (pattern.test(source)) pass(id, message, { filePath });
  else warn(id, message, { filePath, pattern: String(pattern) });
}

function countMatches(filePath, pattern) {
  const source = read(filePath);
  const flags = pattern.flags.includes('g') ? pattern.flags : `${pattern.flags}g`;
  const regex = new RegExp(pattern.source, flags);
  return [...source.matchAll(regex)].length;
}

function getSafeGithubStepSummaryPath() {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY;
  if (typeof summaryPath !== 'string' || summaryPath.trim() === '') return null;

  const runnerTemp = process.env.RUNNER_TEMP;
  if (typeof runnerTemp !== 'string' || runnerTemp.trim() === '') return null;

  const resolvedSummaryPath = path.resolve(summaryPath);
  const resolvedRunnerTemp = path.resolve(runnerTemp);
  const relative = path.relative(resolvedRunnerTemp, resolvedSummaryPath);
  if (relative.startsWith('..') || path.isAbsolute(relative)) return null;

  return resolvedSummaryPath;
}

function requireAtLeast(filePath, pattern, min, id, message) {
  const count = countMatches(filePath, pattern);
  if (count >= min) pass(id, message, { filePath, count, min });
  else fail(id, message, { filePath, count, min, pattern: String(pattern) });
}

function requireOneOf(files, pattern, id, message) {
  const matches = files.filter((filePath) => pattern.test(read(filePath)));
  if (matches.length) pass(id, message, { matches });
  else fail(id, message, { files, pattern: String(pattern) });
}

function warnOneOf(files, pattern, id, message) {
  const matches = files.filter((filePath) => pattern.test(read(filePath)));
  if (matches.length) pass(id, message, { matches });
  else warn(id, message, { files, pattern: String(pattern) });
}

function writeReport() {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  report.status = report.errors.length === 0 ? 'pass' : 'fail';
  fs.writeFileSync(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`);

  const githubStepSummaryPath = getSafeGithubStepSummaryPath();
  if (githubStepSummaryPath) {
    const lines = [
      '## Sovereign UX Contract Scan',
      '',
      `Status: **${report.status}**`,
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
    fs.appendFileSync(githubStepSummaryPath, `${lines.join('\n')}\n`);
  } else if (process.env.GITHUB_STEP_SUMMARY) {
    warn('github-step-summary-path', 'Skipping unsafe GITHUB_STEP_SUMMARY path.', {
      providedPath: process.env.GITHUB_STEP_SUMMARY,
    });
  }

  console.log(JSON.stringify(report, null, 2));
}

function run() {
  requireFile('src/index.css', 'Shared CSS and design tokens are required.');
  requireFile('src/App.tsx', 'App shell is required for global UX flow.');
  requireFile('src/features/product/containers/RepoSnapshotContainer.tsx', 'Repo UX container is required.');
  requireFile('src/features/product/containers/BuilderContainer.tsx', 'Builder UX container is required.');
  requireFile('src/features/product/runtime/sovereignProductTemplate.ts', 'Product template UX contract is required.');

  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /Repository Snapshot/, 'repo:title-visible', 'Repo card title must be visible.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /Load Repo/, 'repo:load-action-visible', 'Repo load action must be visible.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /Save Session/, 'repo:save-action-visible', 'Session save action must be visible.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /Restore Session/, 'repo:restore-action-visible', 'Session restore action must be visible.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /Clear View/, 'repo:clear-action-visible', 'Clear view action must be visible.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /Repo geladen|Repo fehlt/, 'repo:status-pill-visible', 'Repo loaded/missing state must be visible.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /Privater Zugang/, 'repo:private-access-visible', 'Private access state must be visible.');

  requireText('src/features/product/containers/BuilderContainer.tsx', /Ideenfabrik/, 'builder:title-visible', 'Builder title must be visible.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /Auftrag analysieren/, 'builder:analyze-visible', 'Analyze action must be visible.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /Auftrag starten/, 'builder:start-visible', 'Start action must be visible.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /Fehlerlog reparieren/, 'builder:repair-visible', 'Repair action must be visible.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /Draft PR/, 'builder:draft-visible', 'Draft PR action must be visible.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /Schritt 2|2 ·/, 'builder:step-two-guidance', 'Builder must guide the user through analysis step.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /Schritt 3|3 ·/, 'builder:step-three-guidance', 'Builder must guide the user through start step.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /disabledReason/, 'builder:disabled-reason', 'Builder must expose disabled reason from runtime state.');

  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /repo/, 'template:repo-tab', 'Product template must expose repo tab.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /builder/, 'template:builder-tab', 'Product template must expose builder tab.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /files/, 'template:files-tab', 'Product template must expose files tab.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /diff/, 'template:diff-tab', 'Product template must expose diff tab.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /monitor|telemetry/, 'template:monitor-or-telemetry-tab', 'Product template must expose monitor or telemetry visibility.');

  requireText('src/index.css', /:root/, 'css:root-tokens', 'CSS root tokens must exist.');
  requireText('src/index.css', /--surface-1/, 'css:surface-token', 'Surface design token must exist.');
  requireText('src/index.css', /--accent/, 'css:accent-token', 'Accent design token must exist.');
  requireText('src/index.css', /--good/, 'css:good-token', 'Good status token must exist.');
  requireText('src/index.css', /--warn/, 'css:warn-token', 'Warning status token must exist.');
  requireText('src/index.css', /--bad/, 'css:bad-token', 'Bad status token must exist.');
  requireText('src/index.css', /safe-area-inset/, 'css:safe-area', 'Android safe-area support must exist.');
  requireText('src/index.css', /@media \(max-width: 767px\)/, 'css:mobile-media-query', 'Mobile media query must exist.');
  requireText('src/index.css', /border-radius/, 'css:card-rounding', 'Card/pill visual rounding must be defined.');
  requireText('src/index.css', /box-shadow/, 'css:depth', 'Visual depth/shadow must be defined.');

  if (exists('src/global-runtime-monitor.tsx')) {
    requireText('src/global-runtime-monitor.tsx', /Agenten-Monitor|Sovereign Bot|Next Action|Log anzeigen|Log einklappen/, 'monitor:global-copy', 'Global monitor must provide readable status copy and log controls.');
    requireText('src/global-runtime-monitor.tsx', /sovereign:runtime-coach-state/, 'monitor:coach-state-event', 'Global monitor must read coach state events.');
    requireText('src/global-runtime-monitor.tsx', /sovereign:telemetry-event/, 'monitor:telemetry-event', 'Global monitor must read telemetry events.');
    requireText('src/index.css', /sovereign-global-monitor/, 'monitor:css-class', 'Global monitor CSS class must exist.');
    requireText('src/index.css', /sovereign-monitor-log/, 'monitor:log-css-class', 'Global monitor log CSS class must exist.');
    requireText('src/index.css', /sovereign-status-dot/, 'monitor:status-dot-css-class', 'Global monitor status dot CSS class must exist.');
  } else {
    warn('monitor:global-missing', 'Global monitor is absent. Repo-local monitor may still be present, but global one-log UX is preferred.');
    warnText('src/features/product/containers/RepoSnapshotContainer.tsx', /Agenten-Monitor/, 'monitor:repo-local-copy', 'Repo-local monitor copy should exist if no global monitor exists.');
  }

  requireOneOf(
    ['src/App.tsx', 'src/global-runtime-monitor.tsx', 'src/features/product/containers/RepoSnapshotContainer.tsx'],
    /Next Action|Aktion:/,
    'ux:next-action-visible',
    'A next action must be visible to the user.',
  );

  warnOneOf(
    ['src/global-runtime-monitor.tsx', 'src/features/product/containers/TelemetryContainer.tsx', 'src/features/product/containers/RepoSnapshotContainer.tsx'],
    /Log|Telemetry|events|monitor/i,
    'ux:log-visible',
    'At least one user-visible log or telemetry surface should exist.',
  );

  requireAtLeast('src/features/product/containers/BuilderContainer.tsx', /button/g, 4, 'builder:minimum-actions', 'Builder should expose multiple clear actions.');

  const repoMonitorCount = countMatches('src/features/product/containers/RepoSnapshotContainer.tsx', /react-coach-monitor/g);
  const globalMonitorExists = exists('src/global-runtime-monitor.tsx');
  if (globalMonitorExists && repoMonitorCount > 0) {
    warn('ux:duplicate-monitor-surface', 'Global monitor exists while repo-local monitor markup still exists. CSS may hide it, but future cleanup is recommended.', { repoMonitorCount });
  } else {
    pass('ux:monitor-surface-count', 'Monitor surface count is acceptable.', { repoMonitorCount, globalMonitorExists });
  }
}

try {
  run();
} catch (error) {
  fail('scanner:unexpected-error', 'UX contract scanner crashed.', { error: String(error) });
} finally {
  writeReport();
}

if (report.errors.length > 0) process.exit(1);
