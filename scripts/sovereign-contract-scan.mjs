#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const REPORT_DIR = '.security-reports';
const REPORT_PATH = path.join(REPORT_DIR, 'sovereign-runtime-contract.json');

const report = {
  name: 'Sovereign Runtime Contract Scan',
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

function forbidText(filePath, pattern, id, message) {
  const source = read(filePath);
  if (!pattern.test(source)) pass(id, message, { filePath });
  else fail(id, message, { filePath, pattern: String(pattern) });
}

function getPackageScripts() {
  try {
    const packageJson = JSON.parse(read('package.json') || '{}');
    return packageJson.scripts && typeof packageJson.scripts === 'object' ? packageJson.scripts : {};
  } catch (error) {
    fail('package:parse', 'package.json could not be parsed.', { error: String(error) });
    return {};
  }
}

function hasAnyScript(scripts, names) {
  return names.filter((name) => typeof scripts[name] === 'string');
}

function requireScriptGroup(scripts, id, names, message) {
  const found = hasAnyScript(scripts, names);
  if (found.length) pass(id, message, { found });
  else fail(id, `No script found for: ${names.join(', ')}`, { expected: names });
}

function warnScriptGroup(scripts, id, names, message) {
  const found = hasAnyScript(scripts, names);
  if (found.length) pass(id, message, { found });
  else warn(id, `No optional script found for: ${names.join(', ')}`, { expected: names });
}

function extractImports(source) {
  const imports = [];
  const importRegex = /import\s+(?:[^'";]+\s+from\s+)?['"]([^'"]+)['"]/g;
  let match;
  while ((match = importRegex.exec(source)) !== null) imports.push(match[1]);
  return imports;
}

function requireImport(filePath, importPattern, id, message) {
  const imports = extractImports(read(filePath));
  if (imports.some((item) => importPattern.test(item))) pass(id, message, { filePath, imports });
  else fail(id, message, { filePath, imports, importPattern: String(importPattern) });
}

function writeReport() {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  report.status = report.errors.length === 0 ? 'pass' : 'fail';
  fs.writeFileSync(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`);

  if (process.env.GITHUB_STEP_SUMMARY) {
    const lines = [
      '## Sovereign Runtime Contract Scan',
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
    const summaryPath = path.resolve(process.env.GITHUB_STEP_SUMMARY);
    const workspaceRoot = path.resolve(process.cwd());
    const relative = path.relative(workspaceRoot, summaryPath);
    if (relative && !relative.startsWith('..') && !path.isAbsolute(relative)) {
      fs.appendFileSync(summaryPath, `${lines.join('\n')}\n`);
    } else {
      warn('scanner:invalid-summary-path', 'Skipping unsafe GITHUB_STEP_SUMMARY path.', {
        summaryPath,
        workspaceRoot,
      });
    }
  }

  console.log(JSON.stringify(report, null, 2));
}

function run() {
  requireFile('package.json', 'Root package manifest is required.');
  requireFile('pnpm-lock.yaml', 'Frozen pnpm lockfile is required.');
  requireFile('src/main.tsx', 'React entrypoint is required.');
  requireFile('src/App.tsx', 'Chat-only app entry is required.');
  requireFile('src/index.css', 'Shared design CSS is required.');
  requireFile('src/features/github/hooks/useGithubRepo.ts', 'GitHub repo runtime hook is required behind the chat.');
  requireFile('src/features/github/githubPackagePublisher.ts', 'Draft PR publisher runtime is required behind the chat.');
  requireFile('src/features/product/hooks/useCoachRuntimeBridge.ts', 'Coach runtime bridge is required behind the chat.');
  requireFile('src/features/product/containers/RepoSnapshotContainer.tsx', 'Repo snapshot container is required as optional inspection surface.');
  requireFile('src/features/product/containers/BuilderContainer.tsx', 'Builder chat container is required.');
  requireFile('src/features/product/runtime/devChatWorkerBridge.ts', 'DevChat repo bridge runtime is required.');
  requireFile('src/features/product/runtime/sovereignPackageFromRepoFiles.ts', 'Real package builder runtime is required.');
  requireFile('src/features/product/runtime/sovereignTelemetry.ts', 'Telemetry runtime is required.');
  requireFile('src/features/product/runtime/runtimeOutcomeGuard.ts', 'Outcome guard runtime is required.');
  requireFile('src/features/product/runtime/sequentialRuntimeGuard.ts', 'Sequential runtime guard is required.');
  requireFile('src/features/product/runtime/sovereignProductTemplate.ts', 'Product template contract is required.');

  const scripts = getPackageScripts();
  requireScriptGroup(scripts, 'script:type-check', ['type-check', 'typecheck', 'check:types'], 'TypeScript check script is available.');
  requireScriptGroup(scripts, 'script:test', ['test:ci', 'test:run', 'test'], 'Unit test script is available.');
  requireScriptGroup(scripts, 'script:build', ['build', 'web:build'], 'Build script is available.');
  warnScriptGroup(scripts, 'script:lint', ['lint'], 'Lint script is available.');

  requireImport('src/main.tsx', /\.\/App$|\.\/SovereignAppWrapper$/, 'main:imports-app', 'main.tsx imports the app shell.');
  requireText('src/main.tsx', /<App\s*\/ >|<App\s*\/>|<App[\s>]/, 'main:renders-app', 'main.tsx renders App.');
  requireText('src/main.tsx', /installViewportRuntime/, 'main:viewport-runtime', 'main.tsx installs viewport runtime.');
  requireText('src/main.tsx', /installCodeWorkspacePersistenceRuntime/, 'main:workspace-persistence', 'main.tsx installs workspace persistence runtime.');
  forbidText('src/main.tsx', /installMobileAgentMonitor|installMobileMoreMenu|installMobileSetupDrawer|installMobileWorkspaceOrder|installMobileRuntimeModules/, 'main:no-old-dom-installers', 'main.tsx must not install old DOM/mobile mutation helpers.');

  requireText('src/App.tsx', /data-layout="chat-only-live-entry"/, 'app:chat-only-entry', 'App hosts the chat-only live surface.');
  requireText('src/App.tsx', /BuilderContainer/, 'app:builder-chat-host', 'App renders BuilderContainer as the only live product surface.');
  requireText('src/App.tsx', /onStartOpenHands=\{startChatOnlyTask\}/, 'app:chat-submit-handler', 'App keeps chat submit wired without opening a second control shell.');
  forbidText('src/App.tsx', /Sovereign Canvas Tool|RepoSnapshotContainer|RepoInsightPanelBridge|automation__panel|tabbar__root|operator-monitor|decideSovereignAutoView/, 'app:no-visible-dashboard-shell', 'App must not render old dashboard, tabbar, automation panel, monitor, or repo setup surfaces.');

  requireText('src/features/product/runtime/devChatWorkerBridge.ts', /parseDevChatGithubUrl/, 'chat:repo-url-parser', 'Chat bridge parses GitHub URLs from chat input.');
  requireText('src/features/product/runtime/devChatWorkerBridge.ts', /fetchDevChatRepoTree/, 'chat:repo-tree-loader', 'Chat bridge loads real GitHub repo trees.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /fetchDevChatRepoTree/, 'builder:chat-repo-loads-real-tree', 'Builder chat wires repo loading to real repo tree runtime.');
  requireText('src/features/github/hooks/useGithubRepo.ts', /parseGithubRepoUrl/, 'repo:github-runtime-parser', 'GitHub repo hook keeps real repo URL parsing available behind the chat.');
  requireText('src/features/github/hooks/useGithubRepo.ts', /fetch\(/, 'repo:github-runtime-fetch', 'GitHub repo hook keeps real fetch path available behind the chat.');

  requireText('src/features/product/runtime/sequentialRuntimeGuard.ts', /startSequentialStep/, 'sequential:start-step', 'Sequential runtime can start guarded steps.');
  requireText('src/features/product/runtime/sequentialRuntimeGuard.ts', /finishSequentialStep/, 'sequential:finish-step', 'Sequential runtime can finish guarded steps.');
  requireText('src/features/product/runtime/sequentialRuntimeGuard.ts', /validateSequentialRuntimeStepRequest/, 'sequential:step-validation', 'Sequential runtime validates step requests before state changes.');

  requireText('src/features/product/runtime/sovereignTelemetry.ts', /validateTelemetryEvent/, 'telemetry:event-validation', 'Telemetry event validation exists.');
  requireText('src/features/product/runtime/sovereignTelemetry.ts', /validateTelemetryState/, 'telemetry:state-validation', 'Telemetry state validation exists.');
  requireText('src/features/product/runtime/sovereignTelemetry.ts', /appendTelemetryEvent/, 'telemetry:append-event', 'Telemetry append path exists.');
  warnText('src/features/product/runtime/sovereignTelemetry.ts', /sovereign:telemetry-event/, 'telemetry:global-event-bus', 'Telemetry should publish to one global monitor event bus.');

  requireText('src/features/product/hooks/useCoachRuntimeBridge.ts', /deriveCoachStateFromRuntime/, 'coach:derived-from-runtime', 'Coach state derivation remains available behind the chat.');
  requireText('src/features/product/hooks/useCoachRuntimeBridge.ts', /useCoachRuntimeBridge/, 'coach:bridge-hook', 'Coach bridge hook remains available behind the chat.');

  requireText('src/features/product/runtime/sovereignPackageFromRepoFiles.ts', /buildSovereignPackageFromRepoFiles/, 'runtime:real-package-builder', 'Real package builder from repo files remains available behind the chat.');
  requireText('src/features/github/githubPackagePublisher.ts', /publishPackageAsDraftPr/, 'runtime:draft-pr-publisher', 'Draft PR publishing runtime remains available behind the chat.');

  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /sovereign:setup-state/, 'repo:setup-state-event', 'Repo setup publishes setup-state events.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /onLoadRepo/, 'repo:load-handler-prop', 'Repo container exposes load handler for optional inspection paths.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /data-mobile-role="github-repo-url-input"|data-role=\{SOVEREIGN_FORM_REPO_URL\.dataRole\}/, 'repo:mobile-repo-input', 'Repo URL input keeps Android/mobile or contract role.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /data-mobile-role="github-token-input"|data-role=\{SOVEREIGN_FORM_PRIVATE_ACCESS\.dataRole\}/, 'repo:mobile-access-input', 'Access input keeps Android/mobile or contract role.');

  requireText('src/features/product/containers/BuilderContainer.tsx', /Auftrag analysieren|Auftrag vorbereiten|Interne Prüfung/, 'builder:analyze-visible', 'Builder exposes a visible mission analysis/preparation action.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /Auftrag starten|Agent starten|startAgentFromText|onStartOpenHands/, 'builder:start-visible', 'Builder exposes a real task start action.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /onGenerateIdeas/, 'builder:generation-handler', 'Builder keeps generation handler wired.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /onGenerateErrorWorkflow/, 'builder:repair-handler', 'Builder keeps repair handler wired.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /onPublishDraftPr/, 'builder:publish-handler', 'Builder keeps Draft PR handler wired.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /deriveBuilderContainerState/, 'builder:runtime-state-derived', 'Builder action availability is derived from runtime state.');

  requireText('src/features/product/runtime/runtimeOutcomeGuard.ts', /fulfilled|partial|blocked|noise|invalid/, 'outcome:status-contract', 'Outcome guard classifies runtime result states.');
  requireText('src/features/product/runtime/runtimeOutcomeGuard.ts', /learnable/, 'outcome:learnable-contract', 'Outcome guard exposes learnable flag.');

  if (exists('src/global-runtime-monitor.tsx')) {
    pass('monitor:file-present', 'Global runtime monitor file exists.');
    requireText('src/global-runtime-monitor.tsx', /sovereign:runtime-coach-state/, 'monitor:coach-state-listener', 'Global monitor listens to runtime coach state.');
    requireText('src/global-runtime-monitor.tsx', /sovereign:telemetry-event/, 'monitor:telemetry-listener', 'Global monitor listens to telemetry events.');
    warnText('src/main.tsx', /installGlobalRuntimeMonitor/, 'monitor:installed', 'Global monitor exists as optional inspection surface and should not boot over chat by default.');
  } else {
    warn('monitor:file-missing', 'Global monitor file is absent. The repo flow monitor may still be used, but one global monitor is preferred.');
  }

  if (exists('android')) pass('android:directory', 'Android project directory exists.');
  else warn('android:directory', 'Android directory is absent. Android handoff workflow will skip or fail depending on policy.');

  if (exists('scripts/sovereign-static-audit.mjs')) pass('audit:static-audit-present', 'Existing static audit is present.');
  else warn('audit:static-audit-present', 'Existing static audit script is absent.');
}

try {
  run();
} catch (error) {
  fail('scanner:unexpected-error', 'Runtime contract scanner crashed.', { error: String(error) });
} finally {
  writeReport();
}

if (report.errors.length > 0) process.exit(1);
