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

function exists(filePath) { return fs.existsSync(filePath); }
function read(filePath) { return exists(filePath) ? fs.readFileSync(filePath, 'utf8') : ''; }
function pass(id, message, details = {}) { report.checks.push({ id, ok: true, message, details }); }
function fail(id, message, details = {}) {
  report.checks.push({ id, ok: false, message, details });
  report.errors.push({ id, message, details });
}
function warn(id, message, details = {}) { report.warnings.push({ id, message, details }); }
function requireFile(filePath, message) {
  if (exists(filePath)) pass(`file:${filePath}`, message, { filePath });
  else fail(`file:${filePath}`, `Missing required file: ${filePath}`, { filePath, message });
}
function requireText(filePath, pattern, id, message) {
  if (pattern.test(read(filePath))) pass(id, message, { filePath });
  else fail(id, message, { filePath, pattern: String(pattern) });
}
function forbidText(filePath, pattern, id, message) {
  if (!pattern.test(read(filePath))) pass(id, message, { filePath });
  else fail(id, message, { filePath, pattern: String(pattern) });
}

function safeSummaryPath() {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY;
  const runnerTemp = process.env.RUNNER_TEMP;
  if (!summaryPath || !runnerTemp) return null;
  const resolvedSummary = path.resolve(summaryPath);
  const resolvedTemp = path.resolve(runnerTemp);
  const relative = path.relative(resolvedTemp, resolvedSummary);
  if (relative.startsWith('..') || path.isAbsolute(relative)) return null;
  return resolvedSummary;
}

function writeReport() {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  report.status = report.errors.length === 0 ? 'pass' : 'fail';
  fs.writeFileSync(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`);
  const summary = safeSummaryPath();
  if (summary) {
    fs.appendFileSync(summary, [
      '## Sovereign UX Contract Scan', '',
      `Status: **${report.status}**`,
      `Checks: **${report.checks.length}**`,
      `Errors: **${report.errors.length}**`,
      `Warnings: **${report.warnings.length}**`, '',
      ...(report.errors.length ? report.errors.map((item) => `- ${item.id}: ${item.message}`) : ['- No UX contract errors.']),
      '',
    ].join('\n'));
  } else if (process.env.GITHUB_STEP_SUMMARY) {
    warn('github-step-summary-path', 'Skipping unsafe GITHUB_STEP_SUMMARY path.');
  }
  console.log(JSON.stringify(report, null, 2));
}

function run() {
  const app = 'src/App.tsx';
  const wrapper = 'src/SovereignAppWrapper.tsx';
  const release = 'src/features/release/PlayReleaseChat.tsx';
  const builder = 'src/features/product/containers/BuilderContainer.tsx';
  const monitor = 'src/features/product/components/LiveWorkspaceMonitor.tsx';
  const forms = 'src/features/product/runtime/sovereignFormContracts.ts';
  const actions = 'src/features/product/runtime/sovereignActionContracts.ts';

  for (const [file, message] of [
    ['src/index.css', 'Shared CSS and design tokens are required.'],
    ['src/main.tsx', 'App entry is required.'],
    [app, 'Canonical App route is required.'],
    [wrapper, 'Passthrough app wrapper is required.'],
    [release, 'Play Release current-session chat is required.'],
    [builder, 'Builder diagnostics remain a maintained secondary surface.'],
    [monitor, 'Real workspace monitor remains available as a diagnostic surface.'],
    [forms, 'Form contracts remain available.'],
    [actions, 'Action contracts remain available.'],
    ['src/styles/arelogic-brand.css', 'ARELogic visual tokens remain required.'],
  ]) requireFile(file, message);

  requireText('src/main.tsx', /\.\/styles\/arelogic-brand\.css/, 'main:brand-css', 'App entry imports ARELogic brand CSS.');
  requireText(wrapper, /return <App \/>|<App\s*\/\>/, 'wrapper:passthrough', 'Wrapper remains truth-neutral passthrough.');
  forbidText(wrapper, /useState|useEffect|localStorage|sessionStorage|data-testid="sovereign-app-wrapper"/, 'wrapper:no-shadow-state', 'Wrapper must not own product truth or persistence.');

  requireText(app, /PlayReleaseChat/, 'app:release-primary', 'App renders Play Release as primary current-session surface.');
  requireText(app, /data-testid="sovereign-chat-app"/, 'app:root-test-id', 'Primary app has stable root test id.');
  requireText(app, /data-layout="chat-first-agent-zero-background"/, 'app:layout', 'Primary app remains chat first.');
  requireText(app, /data-primary-surface="play-release-chat"/, 'app:primary-marker', 'Primary surface identity is explicit.');
  requireText(app, /data-truth-scope="current-chat-session-only"/, 'app:truth-scope', 'Current-session truth scope is explicit.');
  requireText(app, /EvidenceObservatoryAtlas[\s\S]*\/observatory[\s\S]*\/evidence-observatory/, 'app:observatory-separated', 'Evidence Observatory remains an explicit non-default route.');
  forbidText(app, /RESTORE_LATEST_JOB|BuilderContainer/, 'app:no-historical-auto-adopt', 'Default App must not auto-adopt historical jobs or mount the legacy Builder as current truth.');

  requireText(release, /evaluateInputPolicy\(text\)/, 'release:secret-guard', 'Release chat guards input before LLM/repository execution.');
  requireText(release, /fetchSovereignLlmRouteCatalog/, 'release:route-catalog', 'Release chat reads server-authoritative model routes.');
  requireText(release, /fetchSovereignDirectLlmInterpretation/, 'release:typed-intent', 'Repository intent comes through the typed LLM interpretation boundary.');
  requireText(release, /deriveRepositoryActionFallback/, 'release:degraded-owned-intent', 'Malformed model prose can only fall back to user-owned repository intent.');
  requireText(release, /pendingRepositoryAction/, 'release:pending-action', 'Repository writes are represented as pending visible actions first.');
  requireText(release, /confirmPendingRepositoryAction/, 'release:visible-confirmation', 'Repository execution requires visible confirmation.');
  requireText(release, /startRepositoryExecution/, 'release:agent-runtime', 'Mission execution uses the canonical Agent runtime.');
  requireText(release, /prepareDraftPr/, 'release:draft-prepare', 'Draft PR preparation uses the server gate.');
  requireText(release, /createDraftPr/, 'release:draft-create', 'Draft PR creation uses the server runtime.');
  requireText(release, /readbackHeadSha/, 'release:github-readback', 'Draft PR success is reported from GitHub head readback.');
  requireText(release, /Draft PR erstellen/, 'release:draft-visible', 'Draft PR action is visible to the user.');
  requireText(release, /initiateGitHubOAuth/, 'release:github-oauth', 'GitHub OAuth remains an explicit integration boundary.');
  requireText(release, /GitHub sicher verbinden/, 'release:github-oauth-visible', 'GitHub connection consent is visible.');
  forbidText(release, /listJobs\(|RESTORE_LATEST_JOB/, 'release:no-history-auto-adopt', 'Release chat must not auto-adopt historical jobs.');

  requireText(forms, /SOVEREIGN_FORM_REPO_URL/, 'form:repo-url', 'Repo URL contract remains defined.');
  requireText(forms, /SOVEREIGN_FORM_PRIVATE_ACCESS/, 'form:private-access', 'Private-access contract remains defined.');
  requireText(forms, /sensitive:\s*true/, 'form:sensitive', 'Sensitive form fields remain marked.');
  requireText(forms, /inputType:\s*['"]password['"]/, 'form:password', 'Private access remains password-typed.');
  requireText(actions, /SOVEREIGN_ACTION_DRAFT_PR/, 'action:draft-pr', 'Draft PR action contract remains defined.');
  requireText(actions, /SOVEREIGN_ACTION_LOAD_REPO/, 'action:load-repo', 'Repository load action contract remains defined.');

  requireText(builder, /MonitorCommunicationDock|SovereignActionStreamPanel/, 'builder:secondary-diagnostics', 'Builder retains diagnostic/action-stream capability as a secondary surface.');
  requireText(monitor, /live-workspace-monitor-desktop|DESKTOP · LIVE READBACK/, 'monitor:desktop-readback', 'Real desktop readback remains available.');

  requireText('src/index.css', /@media[\s\S]*max-width/, 'css:responsive', 'Responsive CSS remains present.');
  forbidText(app, /ProductMagicApp|tabbar__root|automation__panel|operator-monitor/, 'app:no-retired-shell', 'Retired product/dashboard shells must stay out of the live App route.');
}

try { run(); }
catch (error) { fail('ux:unexpected-error', 'UX contract scan crashed.', { error: String(error) }); }
finally { writeReport(); }

if (report.errors.length > 0) process.exit(1);
