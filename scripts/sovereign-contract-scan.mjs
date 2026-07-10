#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const REPORT_DIR = '.security-reports';
const REPORT_PATH = path.join(REPORT_DIR, 'sovereign-runtime-contract.json');
const retiredAgentName = ['Open', 'Hands'].join('');
const retiredAppAgentPattern = new RegExp(`create${retiredAgentName}EnterpriseClient|onStart${retiredAgentName}`);
const retiredBuilderAgentPattern = new RegExp(`onStart${retiredAgentName}`);

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
  requireFile('src/App.tsx', 'App shell is required.');
  requireFile('src/index.css', 'Shared design CSS is required.');
  requireFile('src/features/product/containers/RepoSnapshotContainer.tsx', 'Repo snapshot container is required.');
  requireFile('src/features/product/containers/BuilderContainer.tsx', 'Builder container is required.');
  requireFile('src/features/product/runtime/sovereignTelemetry.ts', 'Telemetry runtime is required.');
  requireFile('src/features/product/runtime/runtimeOutcomeGuard.ts', 'Outcome guard runtime is required.');
  requireFile('src/features/product/runtime/sequentialRuntimeGuard.ts', 'Sequential runtime guard is required.');
  requireFile('src/features/product/runtime/sovereignProductTemplate.ts', 'Product template contract is required.');

  const scripts = getPackageScripts();
  requireScriptGroup(scripts, 'script:type-check', ['type-check', 'typecheck', 'check:types'], 'TypeScript check script is available.');
  requireScriptGroup(scripts, 'script:test', ['test:ci', 'test:run', 'test'], 'Unit test script is available.');
  requireScriptGroup(scripts, 'script:build', ['build', 'web:build'], 'Build script is available.');
  warnScriptGroup(scripts, 'script:lint', ['lint'], 'Lint script is available.');

  requireImport('src/main.tsx', /\.\/SovereignAppWrapper$/, 'main:imports-wrapper', 'main.tsx imports the Sovereign runtime wrapper.');
  requireText('src/main.tsx', /<App\s*\/>|<App[\s>]/, 'main:renders-app', 'main.tsx renders App through the wrapper import.');
  requireText('src/main.tsx', /installViewportRuntime/, 'main:viewport-runtime', 'main.tsx installs viewport runtime.');
  requireText('src/main.tsx', /installCodeWorkspacePersistenceRuntime/, 'main:workspace-persistence', 'main.tsx installs workspace persistence runtime.');
  forbidText('src/main.tsx', /installMobileAgentMonitor|installMobileMoreMenu|installMobileSetupDrawer|installMobileWorkspaceOrder|installMobileRuntimeModules/, 'main:no-old-dom-installers', 'main.tsx must not install old DOM/mobile mutation helpers.');

  requireText('src/SovereignAppWrapper.tsx', /<App\s*\/>|<App[\s>]/, 'wrapper:renders-inner-app', 'Sovereign wrapper renders the inner App without owning product truth.');
  requireText('src/SovereignAppWrapper.tsx', /return <App \/>|<App\s*\/>/, 'wrapper:passthrough-only', 'Sovereign wrapper is a passthrough and does not create product truth.');
  forbidText('src/SovereignAppWrapper.tsx', /useState|useEffect|localStorage|sessionStorage|querySelector/, 'wrapper:no-own-runtime-state', 'Sovereign wrapper must not own runtime state or inspect DOM.');
  requireText('src/App.tsx', /BuilderContainer/, 'app:builder-live-path', 'App routes the live surface to BuilderContainer.');
  requireText('src/App.tsx', /LlmAdapterProvider/, 'app:llm-provider', 'App keeps the LLM adapter provider wired.');
  requireText('src/App.tsx', /createSovereignAgentClient/, 'app:sovereign-agent-client', 'App keeps the internal Sovereign Agent client wired.');
  requireText('src/App.tsx', /onStartAgent/, 'app:agent-start-handler', 'App passes the internal Agent start handler into the chat workbench.');
  forbidText('src/App.tsx', retiredAppAgentPattern, 'app:no-retired-agent-wiring', 'App must not restore retired external-agent client or start symbols.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /parseDevChatGithubUrl/, 'builder:repo-url-chat-detection', 'Builder detects GitHub repo URLs in chat.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /fetchDevChatRepoTree/, 'builder:repo-tree-runtime-load', 'Builder loads repo snapshots through the runtime bridge.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /validateGitHubTokenForRepo/, 'builder:github-access-validation', 'Builder validates GitHub access before write execution.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /SovereignActionStreamPanel/, 'builder:action-stream-visible', 'Builder shows route-agnostic action stream state.');

  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /sovereign:setup-state/, 'repo:setup-state-event', 'Repo setup publishes setup-state events.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /onLoadRepo/, 'repo:load-handler-prop', 'Repo container exposes load handler.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /data-mobile-role="github-repo-url-input"|data-role=\{SOVEREIGN_FORM_REPO_URL\.dataRole\}/, 'repo:mobile-repo-input', 'Repo URL input keeps Android/mobile or contract role.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /data-mobile-role="github-token-input"|data-role=\{SOVEREIGN_FORM_PRIVATE_ACCESS\.dataRole\}/, 'repo:mobile-access-input', 'Access input keeps Android/mobile or contract role.');

  requireText('src/features/product/containers/BuilderContainer.tsx', /Sovereign Chat Eingabe|GitHub URL oder Auftrag/, 'builder:chat-input-visible', 'Builder exposes the chat-first input.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /onStartAgent/, 'builder:executor-start-prop', 'Builder keeps the internal Agent start path wired as one route.');
  forbidText('src/features/product/containers/BuilderContainer.tsx', retiredBuilderAgentPattern, 'builder:no-retired-agent-start-prop', 'Builder must not restore the retired external-agent start prop.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /onGenerateIdeas/, 'builder:generation-handler', 'Builder keeps generation handler wired.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /onGenerateErrorWorkflow/, 'builder:repair-handler', 'Builder keeps repair handler wired.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /onPublishDraftPr/, 'builder:publish-handler', 'Builder keeps Draft PR handler wired.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /deriveBuilderContainerState/, 'builder:runtime-state-derived', 'Builder action availability is derived from runtime state.');

  requireText('src/features/product/runtime/sovereignTelemetry.ts', /validateTelemetryEvent/, 'telemetry:event-validation', 'Telemetry event validation exists.');
  requireText('src/features/product/runtime/sovereignTelemetry.ts', /validateTelemetryState/, 'telemetry:state-validation', 'Telemetry state validation exists.');
  requireText('src/features/product/runtime/sovereignTelemetry.ts', /appendTelemetryEvent/, 'telemetry:append-event', 'Telemetry append path exists.');
  warnText('src/features/product/runtime/sovereignTelemetry.ts', /sovereign:telemetry-event/, 'telemetry:global-event-bus', 'Telemetry should publish to one global monitor event bus.');

  requireText('src/features/product/runtime/runtimeOutcomeGuard.ts', /fulfilled|partial|blocked|noise|invalid/, 'outcome:status-contract', 'Outcome guard classifies runtime result states.');
  requireText('src/features/product/runtime/runtimeOutcomeGuard.ts', /learnable/, 'outcome:learnable-contract', 'Outcome guard exposes learnable flag.');
  requireText('src/features/product/runtime/sequentialRuntimeGuard.ts', /startSequentialStep/, 'sequential:start-step', 'Sequential runtime can start guarded steps.');
  requireText('src/features/product/runtime/sequentialRuntimeGuard.ts', /finishSequentialStep/, 'sequential:finish-step', 'Sequential runtime can finish guarded steps.');

  if (exists('src/global-runtime-monitor.tsx')) {
    pass('monitor:file-present', 'Global runtime monitor file exists.');
    requireText('src/global-runtime-monitor.tsx', /sovereign:runtime-coach-state/, 'monitor:coach-state-listener', 'Global monitor listens to runtime coach state.');
    requireText('src/global-runtime-monitor.tsx', /sovereign:telemetry-event/, 'monitor:telemetry-listener', 'Global monitor listens to telemetry events.');
    warnText('src/main.tsx', /installGlobalRuntimeMonitor/, 'monitor:installed', 'main.tsx should install the global monitor.');
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
