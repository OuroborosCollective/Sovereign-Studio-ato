#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const REPORT_DIR = '.security-reports';
const REPORT_PATH = path.join(REPORT_DIR, 'sovereign-ux-contract.json');
const BUILDER = 'src/features/product/containers/BuilderContainer.tsx';
const REPO = 'src/features/product/containers/RepoSnapshotContainer.tsx';
const APP = 'src/App.tsx';
const INDEX_CSS = 'src/index.css';

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

function forbidText(filePath, pattern, id, message) {
  const source = read(filePath);
  if (!pattern.test(source)) pass(id, message, { filePath });
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

function getSafeGithubStepSummaryPath() {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY;
  const runnerTemp = process.env.RUNNER_TEMP;
  if (typeof summaryPath !== 'string' || summaryPath.trim() === '') return null;
  if (typeof runnerTemp !== 'string' || runnerTemp.trim() === '') return null;
  const resolvedSummaryPath = path.resolve(summaryPath);
  const resolvedRunnerTemp = path.resolve(runnerTemp);
  const relative = path.relative(resolvedRunnerTemp, resolvedSummaryPath);
  return relative.startsWith('..') || path.isAbsolute(relative) ? null : resolvedSummaryPath;
}

function writeReport() {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  report.status = report.errors.length === 0 ? 'pass' : 'fail';
  fs.writeFileSync(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`);

  const summaryPath = getSafeGithubStepSummaryPath();
  if (summaryPath) {
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
    fs.appendFileSync(summaryPath, `${lines.join('\n')}\n`);
  }

  console.log(JSON.stringify(report, null, 2));
}

function run() {
  requireFile(INDEX_CSS, 'Shared CSS and design tokens are required.');
  requireFile(APP, 'Chat-only app entry is required for global UX flow.');
  requireFile('src/main.tsx', 'App entry is required for boot-path style imports.');
  requireFile('src/styles/arelogic-brand.css', 'ARELogic visual tokens must be part of the app style contract.');
  requireFile(REPO, 'Repo UX container is required as optional inspection surface.');
  requireFile(BUILDER, 'Builder UX container is required.');
  requireFile('src/features/product/runtime/sovereignProductTemplate.ts', 'Product template UX contract is required.');
  requireFile('src/features/product/runtime/sovereignStyleContract.ts', 'Product style contract is required.');
  requireFile('src/features/product/runtime/sovereignComponentContracts.ts', 'Product component contract is required.');
  requireFile('src/features/product/runtime/arelogicBrandContract.ts', 'ARELogic brand contract is required.');

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

  requireFile('src/features/product/runtime/sovereignActionContracts.ts', 'Action contracts file is required.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_LOAD_REPO/, 'action:load-repo-contract', 'Load repo action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_SAVE_SESSION/, 'action:save-session-contract', 'Save session action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_RESTORE_SESSION/, 'action:restore-session-contract', 'Restore session action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_CLEAR_VIEW/, 'action:clear-view-contract', 'Clear view action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_DRAFT_PR/, 'action:draft-pr-contract', 'Draft PR action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_REPAIR_LOG/, 'action:repair-log-contract', 'Repair log action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /SOVEREIGN_ACTION_MONITOR_TOGGLE/, 'action:monitor-toggle-contract', 'Monitor toggle action contract must exist.');
  requireText('src/features/product/runtime/sovereignActionContracts.ts', /requiresRepo:\s*(true|false)/, 'action:requires-repo-flag', 'Actions must have requiresRepo flag.');

  requireText('src/main.tsx', /\.\/styles\/arelogic-brand\.css/, 'main:brand-css-import', 'App entry must import ARELogic visual tokens after the base style layer.');

  requireText(APP, /data-testid="chat-only-app"/, 'app:chat-only-root-test-id', 'App must expose the chat-only root test-id.');
  requireText(APP, /data-layout="chat-only-live-entry"/, 'app:chat-only-layout', 'App must expose the chat-only live layout contract.');
  requireText(APP, /aria-label="Sovereign Chat"/, 'app:chat-only-aria-label', 'App must label the chat-only live surface.');
  requireText(APP, /BuilderContainer/, 'app:builder-only-surface', 'App must render BuilderContainer as the single live product surface.');
  requireText(APP, /onStartOpenHands=\{startChatOnlyTask\}/, 'app:chat-submit-bound', 'App must keep chat submit wired without visible secondary control shell.');
  forbidText(APP, /data-testid="app-shell__root"|data-testid="tabbar__root"|data-testid="automation__panel"|data-testid="automation__mode-select"|role="tablist"|role="tab"|aria-selected=|Sovereign Canvas Tool|RepoSnapshotContainer|RepoInsightPanelBridge|operator-monitor|decideSovereignAutoView/, 'app:no-old-dashboard-chrome', 'App must not render old dashboard, tabs, automation panel, repo setup, or monitor chrome.');

  requireText(REPO, /Repository Snapshot/, 'repo:title-visible', 'Repo card title must remain available in optional inspection surface.');
  requireText(REPO, /SOVEREIGN_ACTION_LOAD_REPO/, 'repo:load-action-visible', 'Repo load action must be bound to contract.');
  requireText(REPO, /SOVEREIGN_ACTION_SAVE_SESSION/, 'repo:save-action-visible', 'Session save action must be bound to contract.');
  requireText(REPO, /SOVEREIGN_ACTION_RESTORE_SESSION/, 'repo:restore-action-visible', 'Session restore action must be bound to contract.');
  requireText(REPO, /SOVEREIGN_ACTION_CLEAR_VIEW/, 'repo:clear-action-visible', 'Clear view action must be bound to contract.');
  requireText(REPO, /Repo geladen|Repo fehlt/, 'repo:status-pill-visible', 'Repo loaded/missing state must be visible when the optional repo surface is opened.');
  requireText(REPO, /Privater Zugang/, 'repo:private-access-visible', 'Private access state must be visible when the optional repo surface is opened.');

  requireText(BUILDER, /data-layout=["']devchat-replit["']|data-layout=["']devchat-appcontrol-integrated["']|DevChat|Sovereign/, 'builder:devchat-shell-visible', 'Builder must expose the DevChat chat-first shell contract.');
  requireText(BUILDER, /sovereign-chat-body-window|Sovereign Chat Verlauf/, 'builder:chat-timeline-visible', 'Builder must expose the chat timeline surface.');
  requireText(BUILDER, /SOVEREIGN_FORM_MISSION/, 'builder:mission-input-visible', 'Builder must bind mission input to the form contract.');
  requireText(BUILDER, /SOVEREIGN_ACTION_ANALYZE_MISSION/, 'builder:analyze-visible', 'Analyze action must be bound to contract.');
  requireText(BUILDER, /SOVEREIGN_ACTION_START_TASK|Agent starten|startAgentFromChat|onStartOpenHands/i, 'builder:start-visible', 'Start action must be bound to the DevChat runtime path.');
  requireText(BUILDER, /SOVEREIGN_ACTION_REPAIR_LOG/, 'builder:repair-visible', 'Repair action must remain bound to contract.');
  requireText(BUILDER, /SOVEREIGN_ACTION_DRAFT_PR/, 'builder:draft-visible', 'Draft PR action must be bound to contract.');
  requireText(BUILDER, /Repo verbunden|Repo fehlt|effectiveRepoReady|repoReason/, 'builder:repo-state-guidance', 'Builder must surface repo readiness through chat-derived state.');
  requireText(BUILDER, /Runtime Quelle|runtimeSource|openhands-runtime|OpenHands/i, 'builder:runtime-source-guidance', 'Builder must surface the active runtime source.');
  requireText(BUILDER, /Agent starten|SOVEREIGN_ACTION_START_TASK|startAgentFromChat|onStartOpenHands/i, 'builder:agent-start-guidance', 'Builder must provide action to start the agent task.');
  requireText(BUILDER, /disabledReason/, 'builder:disabled-reason', 'Builder must expose disabled reason from runtime state.');

  requireText(REPO, /getSovereignContainerContract\(['"]repo-snapshot['"]\)/, 'repo:container-contract-bound', 'Repo snapshot must use container contract.');
  requireText(REPO, /SOVEREIGN_FORM_REPO_URL/, 'repo:repo-url-form-bound', 'Repo snapshot must bind repo URL form contract.');
  requireText(REPO, /SOVEREIGN_FORM_PRIVATE_ACCESS/, 'repo:private-access-form-bound', 'Repo snapshot must bind private access form contract.');
  requireText(REPO, /type=\{\s*SOVEREIGN_FORM_PRIVATE_ACCESS\.inputType/, 'repo:private-access-password-type', 'Private access must use password type from contract.');
  requireText(REPO, /autoComplete=\{\s*SOVEREIGN_FORM_PRIVATE_ACCESS\.autoComplete/, 'repo:private-access-autocomplete-off', 'Private access must use autocomplete off from contract.');
  requireText(BUILDER, /SOVEREIGN_ACTION_ANALYZE_MISSION/, 'builder:analyze-mission-action-bound', 'Builder must bind analyze mission action contract.');
  requireText(BUILDER, /SOVEREIGN_ACTION_DRAFT_PR/, 'builder:draft-pr-action-bound', 'Builder must bind draft PR action contract.');
  requireText(BUILDER, /SOVEREIGN_ACTION_REPAIR_LOG/, 'builder:repair-log-action-bound', 'Builder must bind repair log action contract.');
  requireText('src/global-runtime-monitor.tsx', /SOVEREIGN_ACTION_MONITOR_TOGGLE/, 'monitor:monitor-toggle-bound', 'Global monitor must bind monitor toggle action contract.');

  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /repo/, 'template:repo-tab', 'Product template must expose repo tab as optional inspection surface.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /builder/, 'template:builder-tab', 'Product template must expose builder tab.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /files/, 'template:files-tab', 'Product template must expose files tab as optional inspection surface.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /diff/, 'template:diff-tab', 'Product template must expose diff tab as optional inspection surface.');
  requireText('src/features/product/runtime/sovereignProductTemplate.ts', /monitor|telemetry/, 'template:monitor-or-telemetry-tab', 'Product template must expose monitor or telemetry visibility as optional inspection surface.');

  requireText('src/features/product/runtime/sovereignStyleContract.ts', /SOVEREIGN_APP_CLASSES/, 'style:app-classes-contract', 'Style contract must expose app class names.');
  requireText('src/features/product/runtime/sovereignStyleContract.ts', /SOVEREIGN_TAB_STYLE_CONTRACT/, 'style:tab-contract', 'Style contract must expose tab style metadata.');
  requireText('src/features/product/runtime/sovereignStyleContract.ts', /dataRole/, 'style:data-role-contract', 'Style contract must expose stable data roles.');
  requireText('src/features/product/runtime/sovereignStyleContract.ts', /mobilePriority/, 'style:mobile-priority-contract', 'Style contract must expose mobile priorities.');

  requireText('src/features/product/runtime/sovereignComponentContracts.ts', /SOVEREIGN_APP_SHELL_CONTRACT/, 'component:app-shell-contract', 'Component contract must expose app shell contract metadata.');
  requireText('src/features/product/runtime/sovereignComponentContracts.ts', /SOVEREIGN_TABBAR_CONTRACT/, 'component:tabbar-contract', 'Component contract must expose optional tabbar contract metadata.');
  requireText('src/features/product/runtime/sovereignComponentContracts.ts', /SOVEREIGN_ACTION_BUTTON_CONTRACT/, 'component:action-button-contract', 'Component contract must expose action button contract.');
  requireText('src/features/product/runtime/sovereignComponentContracts.ts', /SOVEREIGN_TEST_ID_PATTERN/, 'component:test-id-pattern', 'Component contract must expose test id pattern.');

  requireText('src/features/product/runtime/arelogicBrandContract.ts', /ARELOGIC_BRAND_PRIORITY/, 'brand:priority-contract', 'Brand contract must expose priority ordering.');
  requireText('src/features/product/runtime/arelogicBrandContract.ts', /ARELOGIC_BRAND_TOKENS/, 'brand:token-contract', 'Brand contract must expose token definitions.');
  requireText('src/features/product/runtime/arelogicBrandContract.ts', /--are-void/, 'brand:void-token-contract', 'Brand contract must expose ARE void token.');
  requireText('src/features/product/runtime/arelogicBrandContract.ts', /--are-ion/, 'brand:ion-token-contract', 'Brand contract must expose ARE ion token.');
  requireText('src/features/product/runtime/arelogicBrandContract.ts', /--are-matter/, 'brand:matter-token-contract', 'Brand contract must expose ARE matter token.');
  requireText('src/features/product/runtime/arelogicBrandContract.ts', /SOVEREIGN_APP_CLASSES/, 'brand:sovereign-style-link', 'Brand contract must attach to Sovereign style contracts instead of replacing them.');

  requireText('src/styles/arelogic-brand.css', /--are-void/, 'brand-css:void-token', 'Brand CSS must expose ARE void token.');
  requireText('src/styles/arelogic-brand.css', /--are-ion/, 'brand-css:ion-token', 'Brand CSS must expose ARE ion token.');
  requireText('src/styles/arelogic-brand.css', /--are-matter/, 'brand-css:matter-token', 'Brand CSS must expose ARE matter token.');
  requireText('src/styles/arelogic-brand.css', /\.sovereign-app-shell/, 'brand-css:shell-binding', 'Brand CSS must keep shell class support for optional inspection surfaces.');
  requireText('src/styles/arelogic-brand.css', /\.sovereign-tab-active/, 'brand-css:tab-binding', 'Brand CSS must keep tab class support for optional inspection surfaces.');
  requireText('src/styles/arelogic-brand.css', /\.sovereign-status-dot-green/, 'brand-css:status-binding', 'Brand CSS must bind through existing Sovereign status classes.');

  requireText(INDEX_CSS, /:root/, 'css:root-tokens', 'CSS root tokens must exist.');
  requireText(INDEX_CSS, /--surface-1/, 'css:surface-token', 'Surface design token must exist.');
  requireText(INDEX_CSS, /--accent/, 'css:accent-token', 'Accent design token must exist.');
  requireText(INDEX_CSS, /--good/, 'css:good-token', 'Good status token must exist.');
  requireText(INDEX_CSS, /--warn/, 'css:warn-token', 'Warning status token must exist.');
  requireText(INDEX_CSS, /--bad/, 'css:bad-token', 'Bad status token must exist.');
  requireText(INDEX_CSS, /safe-area-inset/, 'css:safe-area', 'Android safe-area support must exist.');
  requireText(INDEX_CSS, /@media \(max-width: 767px\)/, 'css:mobile-media-query', 'Mobile media query must exist.');
  requireText(INDEX_CSS, /border-radius/, 'css:card-rounding', 'Card/pill visual rounding must be defined.');
  requireText(INDEX_CSS, /box-shadow/, 'css:depth', 'Visual depth/shadow must be defined.');
  requireText(INDEX_CSS, /\.sovereign-app-shell/, 'css:app-shell-class', 'Stable app shell class must remain available for optional inspection surfaces.');
  requireText(INDEX_CSS, /\.sovereign-tabbar/, 'css:tabbar-class', 'Stable tabbar class must remain available for optional inspection surfaces.');
  requireText(INDEX_CSS, /\.sovereign-tab\b/, 'css:tab-class', 'Stable tab class must remain available for optional inspection surfaces.');
  requireText(INDEX_CSS, /\.sovereign-tab-active/, 'css:active-tab-class', 'Stable active tab class must remain available for optional inspection surfaces.');
  requireText(INDEX_CSS, /\.sovereign-card/, 'css:card-class', 'Stable card class must exist.');
  requireText(INDEX_CSS, /\.sovereign-select/, 'css:select-class', 'Stable select class must remain available for optional inspection surfaces.');
  requireText(INDEX_CSS, /\.sovereign-status-pill/, 'css:status-pill-class', 'Stable status pill class must exist.');

  if (exists('src/global-runtime-monitor.tsx')) {
    requireText('src/global-runtime-monitor.tsx', /Agenten-Monitor|Sovereign Bot|Next Action|Log anzeigen|Log einklappen/, 'monitor:global-copy', 'Global monitor must provide readable status copy and log controls as optional inspection surface.');
    requireText('src/global-runtime-monitor.tsx', /sovereign:runtime-coach-state/, 'monitor:coach-state-event', 'Global monitor must read coach state events.');
    requireText('src/global-runtime-monitor.tsx', /sovereign:telemetry-event/, 'monitor:telemetry-event', 'Global monitor must read telemetry events.');
    requireText(INDEX_CSS, /sovereign-global-monitor/, 'monitor:css-class', 'Global monitor CSS class must exist.');
    requireText(INDEX_CSS, /sovereign-monitor-log/, 'monitor:log-css-class', 'Global monitor log CSS class must exist.');
    requireText(INDEX_CSS, /sovereign-status-dot/, 'monitor:status-dot-css-class', 'Global monitor status dot CSS class must exist.');
  } else {
    warn('monitor:global-missing', 'Global monitor is absent. Repo-local monitor may still be present, but global one-log UX is preferred.');
    warnText(REPO, /Agenten-Monitor/, 'monitor:repo-local-copy', 'Repo-local monitor copy should exist if no global monitor exists.');
  }

  requireOneOf([APP, 'src/global-runtime-monitor.tsx', REPO, BUILDER], /Next Action|Aktion:|Agent starten|DevChat|Runtime Quelle|Sovereign Chat/, 'ux:next-action-visible', 'A next action must be visible to the user.');
  warnOneOf(['src/global-runtime-monitor.tsx', 'src/features/product/containers/TelemetryContainer.tsx', REPO, BUILDER], /Log|Telemetry|events|monitor|Sovereign Chat Verlauf/i, 'ux:log-visible', 'At least one user-visible log or telemetry surface should exist.');
  requireAtLeast(BUILDER, /button/g, 4, 'builder:minimum-actions', 'Builder should expose multiple clear actions.');

  const repoMonitorCount = countMatches(REPO, /react-coach-monitor/g);
  const globalMonitorExists = exists('src/global-runtime-monitor.tsx');
  if (globalMonitorExists && repoMonitorCount > 0) warn('ux:duplicate-monitor-surface', 'Global monitor exists while repo-local monitor markup still exists. CSS may hide it, but future cleanup is recommended.', { repoMonitorCount });
  else pass('ux:monitor-surface-count', 'Monitor surface count is acceptable.', { repoMonitorCount, globalMonitorExists });

  warnIfText(INDEX_CSS, /#root > div\.min-h-screen/, 'css:no-root-fallback', 'CSS should use contract classes instead of fragile root selectors.');
  warnIfText(INDEX_CSS, /nth-of-type/, 'css:no-nth-of-type', 'CSS should use contract selectors instead of nth-of-type patterns.');
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
