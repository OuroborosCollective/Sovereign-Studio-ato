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

function warnIfText(filePath, pattern, id, message) {
  const source = read(filePath);
  if (pattern.test(source)) warn(id, message, { filePath, pattern: String(pattern) });
  else pass(id, message, { filePath });
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
  requireFile('src/main.tsx', 'App entry is required for boot-path style imports.');
  requireFile('src/styles/arelogic-brand.css', 'ARELogic visual tokens must be part of the app style contract.');
  requireFile('src/features/product/containers/RepoSnapshotContainer.tsx', 'Repo UX container is required.');
  requireFile('src/features/product/containers/BuilderContainer.tsx', 'Builder UX container is required.');
  requireFile('src/features/product/runtime/sovereignProductTemplate.ts', 'Product template UX contract is required.');
  requireFile('src/features/product/runtime/sovereignStyleContract.ts', 'Product style contract is required.');
  requireFile('src/features/product/runtime/sovereignComponentContracts.ts', 'Product component contract is required.');
  requireFile('src/features/product/runtime/arelogicBrandContract.ts', 'ARELogic brand contract is required.');

  // Form contracts validation
  requireFile('src/features/product/runtime/sovereignFormContracts.ts', 'Form contracts file is required.');
  requireText('src/features/product/runtime/sovereignFormContracts.ts', /SOVEREIGN_FORM_REPO_URL/, 'form:repo-url-contract', 'Repo URL form contract must exist.');
  requireText('src/features/product/runtime/sovereignFormContracts.ts', /SOVEREIGN_FORM_PRIVATE_ACCESS/, 'form:private-access-contract', 'Private access form contract must exist.');
  requireText('src/features/product/runtime/sovereignFormContracts.ts', /SOVEREIGN_FORM_BRANCH|SOVEREIGN_FORM_REPO_BRANCH/, 'form:branch-contract', 'Branch form contract must exist.');
  requireText('src/features/product/runtime/sovereignFormContracts.ts', /SOVEREIGN_FORM_MISSION/, 'form:mission-contract', 'Mission form contract must exist.');
  requireText('src/features/product/runtime/sovereignFormContracts.ts', /sensitive:\s*true/, 'form:sensitive-flag', 'Sensitive fields must be marked as sensitive.');
  requireText('src/features/product/runtime/sovereignFormContracts.ts', /inputType:\s*['"]password['"]/, 'form:password-type', 'Private access must use password input type.');
  requireText('src/features/product/runtime/sovereignFormContracts.ts', /autoComplete:\s*['"]off['"]/, 'form:autocomplete-off', 'Private access must use autocomplete off.');
  requireText('src/features/product/runtime/sovereignFormContracts.ts', /testId:\s*['"]repo-url__input['"]/, 'form:repo-url-test-id', 'Repo URL must have stable test-id.');
  requireText('src/features/product/runtime/sovereignFormContracts.ts', /testId:\s*['"]private-access__input['"]/, 'form:private-access-test-id', 'Private access must have stable test-id.');

  // Action contracts validation
  requireFile('src/features/product/runtime/sovereignActionContracts.ts', 'Action contracts file is required.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_LOAD_REPO/, 'action:load-repo-contract', 'Load repo action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_SAVE_SESSION/, 'action:save-session-contract', 'Save session action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_RESTORE_SESSION/, 'action:restore-session-contract', 'Restore session action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_CLEAR_VIEW/, 'action:clear-view-contract', 'Clear view action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_DRAFT_PR/, 'action:draft-pr-contract', 'Draft PR action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_REPAIR_LOG/, 'action:repair-log-contract', 'Repair log action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_MONITOR_TOGGLE/, 'action:monitor-toggle-contract', 'Monitor toggle action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /testId:\s*['"]repo-snapshot__load-repo['"]/, 'action:load-repo-test-id', 'Load repo must have stable test-id.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /testId:\s*['"]builder__draft-pr['"]/, 'action:draft-pr-test-id', 'Draft PR must have stable test-id.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /kind:\s*['"]primary['"]/, 'action:primary-kind', 'Primary actions must be classified as primary.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /kind:\s*['"]destructive['"]/, 'action:destructive-kind', 'Destructive actions must be classified as destructive.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /requiresRepo:\s*(true|false)/, 'action:requires-repo-flag', 'Actions must have requiresRepo flag.');

  requireText('src/main.tsx', /\.\/styles\/arelogic-brand\.css/, 'main:brand-css-import', 'App entry must import ARELogic visual tokens after the base style layer.');

  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /Repository Snapshot/, 'repo:title-visible', 'Repo card title must be visible.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /SOVEREIGN_ACTION_LOAD_REPO/, 'repo:load-action-visible', 'Repo load action must be bound to contract.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /SOVEREIGN_ACTION_SAVE_SESSION/, 'repo:save-action-visible', 'Session save action must be bound to contract.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /SOVEREIGN_ACTION_RESTORE_SESSION/, 'repo:restore-action-visible', 'Session restore action must be bound to contract.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /SOVEREIGN_ACTION_CLEAR_VIEW/, 'repo:clear-action-visible', 'Clear view action must be bound to contract.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /Repo geladen|Repo fehlt/, 'repo:status-pill-visible', 'Repo loaded/missing state must be visible.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /Privater Zugang/, 'repo:private-access-visible', 'Private access state must be visible.');

  requireText('src/features/product/containers/BuilderContainer.tsx', /Ideenfabrik/, 'builder:title-visible', 'Builder title must be visible.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /SOVEREIGN_ACTION_ANALYZE_MISSION/, 'builder:analyze-visible', 'Analyze action must be bound to contract.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /SOVEREIGN_ACTION_START_TASK/, 'builder:start-visible', 'Start action must be bound to contract.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /SOVEREIGN_ACTION_REPAIR_LOG/, 'builder:repair-visible', 'Repair action must be bound to contract.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /SOVEREIGN_ACTION_DRAFT_PR/, 'builder:draft-visible', 'Draft PR action must be bound to contract.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /Schritt 2|2 ·|Interne Prüfung/, 'builder:step-two-guidance', 'Builder must guide the user through analysis step.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /Agent starten|submit.*task|start.*task/i, 'builder:step-three-guidance', 'Builder must provide action to start the agent task.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /disabledReason/, 'builder:disabled-reason', 'Builder must expose disabled reason from runtime state.');

  // Container and contract binding validation
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /getSovereignContainerContract\(['"]repo-snapshot['"]\)/, 'repo:container-contract-bound', 'Repo snapshot must use container contract.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /SOVEREIGN_FORM_REPO_URL/, 'repo:repo-url-form-bound', 'Repo snapshot must bind repo URL form contract.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /SOVEREIGN_FORM_PRIVATE_ACCESS/, 'repo:private-access-form-bound', 'Repo snapshot must bind private access form contract.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /SOVEREIGN_ACTION_LOAD_REPO/, 'repo:load-repo-action-bound', 'Repo snapshot must bind load repo action contract.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /SOVEREIGN_ACTION_SAVE_SESSION/, 'repo:save-session-action-bound', 'Repo snapshot must bind save session action contract.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /type=\{\s*SOVEREIGN_FORM_PRIVATE_ACCESS\.inputType/, 'repo:private-access-password-type', 'Private access must use password type from contract.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /autoComplete=\{\s*SOVEREIGN_FORM_PRIVATE_ACCESS\.autoComplete/, 'repo:private-access-autocomplete-off', 'Private access must use autocomplete off from contract.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /SOVEREIGN_FORM_MISSION/, 'builder:mission-form-bound', 'Builder must bind mission form contract.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /SOVEREIGN_ACTION_ANALYZE_MISSION/, 'builder:analyze-mission-action-bound', 'Builder must bind analyze mission action contract.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /SOVEREIGN_ACTION_DRAFT_PR/, 'builder:draft-pr-action-bound', 'Builder must bind draft PR action contract.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /SOVEREIGN_ACTION_REPAIR_LOG/, 'builder:repair-log-action-bound', 'Builder must bind repair log action contract.');
  requireText('src/global-runtime-monitor.tsx', /SOVEREIGN_ACTION_MONITOR_TOGGLE/, 'monitor:monitor-toggle-bound', 'Global monitor must bind monitor toggle action contract.');

  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /repo/, 'template:repo-tab', 'Product template must expose repo tab.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /builder/, 'template:builder-tab', 'Product template must expose builder tab.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /files/, 'template:files-tab', 'Product template must expose files tab.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /diff/, 'template:diff-tab', 'Product template must expose diff tab.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /monitor|telemetry/, 'template:monitor-or-telemetry-tab', 'Product template must expose monitor or telemetry visibility.');

  requireText('src/features/product/runtime/sovereignStyleContract.ts', /SOVEREIGN_APP_CLASSES/, 'style:app-classes-contract', 'Style contract must expose app class names.');
  requireText('src/features/product/runtime/sovereignStyleContract.ts', /SOVEREIGN_TAB_STYLE_CONTRACT/, 'style:tab-contract', 'Style contract must expose tab style metadata.');
  requireText('src/features/product/runtime/sovereignStyleContract.ts', /dataRole/, 'style:data-role-contract', 'Style contract must expose stable data roles.');
  requireText('src/features/product/runtime/sovereignStyleContract.ts', /mobilePriority/, 'style:mobile-priority-contract', 'Style contract must expose mobile priorities.');

  requireText('src/features/product/runtime/sovereignComponentContracts.ts', /SOVEREIGN_APP_SHELL_CONTRACT/, 'component:app-shell-contract', 'Component contract must expose app shell contract.');
  requireText('src/features/product/runtime/sovereignComponentContracts.ts', /SOVEREIGN_TABBAR_CONTRACT/, 'component:tabbar-contract', 'Component contract must expose tabbar contract.');
  requireText('src/features/product/runtime/sovereignComponentContracts.ts', /SOVEREIGN_ACTION_BUTTON_CONTRACT/, 'component:action-button-contract', 'Component contract must expose action button contract.');
  requireText('src/features/product/runtime/sovereignComponentContracts.ts', /SOVEREIGN_TEST_ID_PATTERN/, 'component:test-id-pattern', 'Component contract must expose test id pattern.');

  requireText('src/features/product/runtime/arelogicBrandContract.ts', /ARELOGIC_BRAND_PRIORITY/, 'brand:priority-contract', 'Brand contract must expose priority ordering.');
  requireText('src/features/product/runtime/arelogicBrandContract.ts', /runtime-contracts[\s\S]*accessibility-contracts[\s\S]*component-contracts[\s\S]*brand-visual-layer/, 'brand:priority-order', 'Brand visuals must remain behind runtime, accessibility and component contracts.');
  requireText('src/features/product/runtime/arelogicBrandContract.ts', /ARELOGIC_BRAND_TOKENS/, 'brand:token-contract', 'Brand contract must expose token definitions.');
  requireText('src/features/product/runtime/arelogicBrandContract.ts', /--are-void/, 'brand:void-token-contract', 'Brand contract must expose ARE void token.');
  requireText('src/features/product/runtime/arelogicBrandContract.ts', /--are-ion/, 'brand:ion-token-contract', 'Brand contract must expose ARE ion token.');
  requireText('src/features/product/runtime/arelogicBrandContract.ts', /--are-matter/, 'brand:matter-token-contract', 'Brand contract must expose ARE matter token.');
  requireText('src/features/product/runtime/arelogicBrandContract.ts', /SOVEREIGN_APP_CLASSES/, 'brand:sovereign-style-link', 'Brand contract must attach to Sovereign style contracts instead of replacing them.');

  requireText('src/styles/arelogic-brand.css', /--are-void/, 'brand-css:void-token', 'Brand CSS must expose ARE void token.');
  requireText('src/styles/arelogic-brand.css', /--are-ion/, 'brand-css:ion-token', 'Brand CSS must expose ARE ion token.');
  requireText('src/styles/arelogic-brand.css', /--are-matter/, 'brand-css:matter-token', 'Brand CSS must expose ARE matter token.');
  requireText('src/styles/arelogic-brand.css', /\.sovereign-app-shell/, 'brand-css:shell-binding', 'Brand CSS must bind through existing Sovereign shell class.');
  requireText('src/styles/arelogic-brand.css', /\.sovereign-tab-active/, 'brand-css:tab-binding', 'Brand CSS must bind through existing Sovereign tab class.');
  requireText('src/styles/arelogic-brand.css', /\.sovereign-status-dot-green/, 'brand-css:status-binding', 'Brand CSS must bind through existing Sovereign status classes.');

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
  requireText('src/index.css', /\.sovereign-app-shell/, 'css:app-shell-class', 'Stable app shell class must exist.');
  requireText('src/index.css', /\.sovereign-app-title/, 'css:app-title-class', 'Stable app title class must exist.');
  requireText('src/index.css', /\.sovereign-tabbar/, 'css:tabbar-class', 'Stable tabbar class must exist.');
  requireText('src/index.css', /\.sovereign-tab\b/, 'css:tab-class', 'Stable tab class must exist.');
  requireText('src/index.css', /\.sovereign-tab-active/, 'css:active-tab-class', 'Stable active tab class must exist.');
  requireText('src/index.css', /\.sovereign-card/, 'css:card-class', 'Stable card class must exist.');
  requireText('src/index.css', /\.sovereign-select/, 'css:select-class', 'Stable select class must exist.');
  requireText('src/index.css', /\.sovereign-status-pill/, 'css:status-pill-class', 'Stable status pill class must exist.');

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

  requireText('src/App.tsx', /sovereign-app-shell/, 'app:stable-shell-class-bound', 'App shell must bind stable shell class.');
  requireText('src/App.tsx', /sovereign-tabbar/, 'app:stable-tabbar-class-bound', 'App tabbar must bind stable tabbar class.');
  requireText('src/App.tsx', /data-role="sovereign-app-shell"/, 'app:shell-data-role-bound', 'App shell must bind sovereign-app-shell data-role.');
  requireText('src/App.tsx', /data-testid="app-shell__root"/, 'app:shell-test-id-bound', 'App shell must bind app-shell__root test-id.');
  requireText('src/App.tsx', /role="tablist"/, 'app:tabbar-role-bound', 'Tabbar must bind tablist role.');
  requireText('src/App.tsx', /aria-label="Sovereign workspace tabs"/, 'app:tabbar-aria-label-bound', 'Tabbar must bind Sovereign workspace tabs aria-label.');
  requireText('src/App.tsx', /data-testid="tabbar__root"/, 'app:tabbar-test-id-bound', 'Tabbar must bind tabbar__root test-id.');
  requireText('src/App.tsx', /role="tab"/, 'app:tab-role-bound', 'Tab buttons must bind tab role.');
  requireText('src/App.tsx', /aria-selected=/, 'app:tab-aria-selected-bound', 'Tab buttons must bind aria-selected.');
  requireText('src/App.tsx', /data-testid=\{tab\.testId\}/, 'app:tab-test-id-bound', 'Tab buttons must bind test-id from tab contract.');
  requireText('src/App.tsx', /sovereign-automation-panel/, 'app:automation-panel-class-bound', 'Automation panel must bind sovereign-automation-panel class.');
  requireText('src/App.tsx', /data-testid="automation__panel"/, 'app:automation-panel-test-id-bound', 'Automation panel must bind automation__panel test-id.');
  requireText('src/App.tsx', /SOVEREIGN_APP_CLASSES\.select|sovereign-select/, 'app:automation-select-class-bound', 'Automation select must bind sovereign-select class via contract.');
  requireText('src/App.tsx', /data-testid="automation__mode-select"/, 'app:automation-select-test-id-bound', 'Automation select must bind automation__mode-select test-id.');

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

  warnIfText('src/index.css', /#root > div\.min-h-screen/, 'css:no-root-fallback', 'CSS should use contract classes instead of fragile root selectors.');
  warnIfText('src/index.css', /nth-of-type/, 'css:no-nth-of-type', 'CSS should use contract selectors instead of nth-of-type patterns.');
  warnIfText('src/main.tsx', /#root > div/, 'main:no-root-fallback', 'main.tsx should use contract class selectors instead of fragile root selectors.');
}

try {
  run();
} catch (error) {
  fail('scanner:unexpected-error', 'UX contract scanner crashed.', { error: String(error) });
} finally {
  writeReport();
}

if (report.errors.length > 0) process.exit(1);
