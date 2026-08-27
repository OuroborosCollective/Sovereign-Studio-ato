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
  requireFile('src/features/release/PlayReleaseChat.tsx', 'Google Play release chat surface is required.');
  requireFile('src/index.css', 'Shared design CSS is required.');
  requireFile('src/features/product/containers/RepoSnapshotContainer.tsx', 'Repo snapshot container is required.');
  requireFile('src/features/product/containers/BuilderContainer.tsx', 'Builder container is required.');
  requireFile('src/features/product/runtime/sovereignTelemetry.ts', 'Telemetry runtime is required.');
  requireFile('src/features/product/runtime/runtimeOutcomeGuard.ts', 'Outcome guard runtime is required.');
  requireFile('src/features/product/runtime/sequentialRuntimeGuard.ts', 'Sequential runtime guard is required.');
  requireFile('src/features/product/runtime/sovereignProductTemplate.ts', 'Product template contract is required.');
  requireFile('scripts/frontend_endpoint_contracts.py', 'Frontend endpoint contract compiler is required.');
  requireFile('scripts/tests/test_frontend_endpoint_contracts.py', 'Frontend endpoint compiler regressions are required.');
  requireFile('scripts/vitest_causal_runner.py', 'Bounded Vitest causal evidence runner is required.');
  requireFile('scripts/tests/test_vitest_causal_runner.py', 'Vitest causal evidence runner regressions are required.');
  requireFile('scripts/frontend_test_gate.py', 'Shell-free frontend test gate orchestrator is required.');
  requireFile('scripts/tests/test_frontend_test_gate.py', 'Frontend test gate orchestrator regressions are required.');
  requireFile('tests/e2e/frontend-endpoint-contract-smoke.spec.ts', 'Built-browser endpoint smoke is required.');
  requireFile('src/features/admin/api/adminApiClient.ownerInput.test.ts', 'Protected owner-input endpoint regression is required.');
  requireFile('src/features/billing/billingSlice.test.ts', 'Billing endpoint regression is required.');
  requireFile('src/features/knowledge/knowledgeApi.test.ts', 'Knowledge endpoint regression is required.');
  requireFile('src/features/rescue/rescueClient.test.ts', 'Rescue endpoint regression is required.');
  requireFile('src/features/toolchain/toolchainApi.test.ts', 'Toolchain endpoint regression is required.');
  requireFile('src/features/toolchain/skillsApi.test.ts', 'Skill endpoint regression is required.');
  requireFile('docs/architecture/FRONTEND_ENDPOINT_CONTRACTS.v1.md', 'Frontend endpoint truth-boundary documentation is required.');

  const scripts = getPackageScripts();
  requireScriptGroup(scripts, 'script:type-check', ['type-check', 'typecheck', 'check:types'], 'TypeScript check script is available.');
  requireScriptGroup(scripts, 'script:test', ['test:ci', 'test:run', 'test'], 'Unit test script is available.');
  requireScriptGroup(scripts, 'script:build', ['build', 'web:build'], 'Build script is available.');
  warnScriptGroup(scripts, 'script:lint', ['lint'], 'Lint script is available.');
  requireScriptGroup(scripts, 'script:frontend-endpoints', ['test:frontend-endpoints'], 'Frontend endpoint compiler and regression script is available.');
  requireScriptGroup(scripts, 'script:frontend-endpoints-e2e', ['test:e2e:frontend-endpoints'], 'Frontend endpoint Playwright smoke script is available.');

  requireText('.github/workflows/sovereign-contract-scan.yml', /run_first_present test:smoke/, 'workflow:frontend-endpoint-contracts', 'Runtime contract workflow executes the canonical smoke gate.');
  requireText('package.json', /"test:smoke"\s*:\s*"python3 scripts\/frontend_test_gate\.py --mode smoke"/, 'workflow:frontend-endpoint-smoke-chain', 'The canonical smoke gate runs the fixed shell-free frontend test orchestrator.');
  requireText('package.json', /"test:frontend-endpoints"\s*:\s*"python3 scripts\/frontend_endpoint_assurance\.py --no-write && python3 scripts\/frontend_test_gate\.py --mode endpoint"/, 'workflow:frontend-endpoint-targeted-chain', 'The targeted endpoint gate preserves the existing endpoint assurance and then runs the fixed shell-free orchestrator in endpoint mode.');
  requireText('.github/workflows/e2e-testing.yml', /pnpm run test:e2e/, 'workflow:frontend-endpoint-e2e', 'Current App E2E workflow executes the endpoint browser smoke through the full Playwright suite.');
  requireText('scripts/frontend_endpoint_contracts.py', /"externalCalls"/, 'frontend-endpoints:external-inventory', 'Endpoint compiler preserves third-party request inventory separately from backend routes.');
  requireText('scripts/frontend_endpoint_contracts.py', /legacyImportViolationCount/, 'frontend-endpoints:legacy-import-gate', 'Endpoint compiler rejects active reactivation of legacy endpoint surfaces.');
  requireText('scripts/frontend_endpoint_contracts.py', /FRONTEND_MUTATION_TEST_EVIDENCE_MISSING/, 'frontend-endpoints:mutation-test-gate', 'Endpoint compiler rejects active mutation requests without test evidence.');
  requireText('scripts/frontend_endpoint_contracts.py', /activeMutationWithoutTestEvidenceCount/, 'frontend-endpoints:mutation-test-count', 'Endpoint report exposes the mutation test-evidence count.');
  requireText('scripts/frontend_test_gate.py', /adminApiClient\.ownerInput\.test\.ts[\s\S]*billingSlice\.test\.ts[\s\S]*knowledgeApi\.test\.ts[\s\S]*rescueClient\.test\.ts[\s\S]*toolchainApi\.test\.ts[\s\S]*skillsApi\.test\.ts/, 'frontend-endpoints:targeted-client-tests', 'Frontend test gate executes all targeted client regression suites.');
  requireText('scripts/frontend_test_gate.py', /frontend-endpoint-clients/, 'frontend-endpoints:targeted-causal-runner', 'Targeted endpoint clients use the bounded causal Vitest runner.');
  requireText('scripts/frontend_test_gate.py', /frontend-smoke/, 'frontend-endpoints:broad-causal-runner', 'The broad frontend smoke uses the bounded causal Vitest runner.');
  requireText('scripts/frontend_test_gate.py', /scripts\/frontend_endpoint_contracts\.py::repository_contract/, 'frontend-endpoints:compiler-stage-fallback', 'The endpoint compiler stage emits a bounded failure identity.');
  requireText('scripts/frontend_test_gate.py', /frontend-endpoint-clients::vitest_runner/, 'frontend-endpoints:client-stage-fallback', 'The targeted client stage emits a bounded fallback identity if its runner aborts.');
  requireText('scripts/frontend_test_gate.py', /frontend-smoke::vitest_runner/, 'frontend-endpoints:smoke-stage-fallback', 'The broad smoke stage emits a bounded fallback identity if its runner aborts.');
  requireText('scripts/frontend_test_gate.py', /stdout=subprocess\.PIPE[\s\S]*stderr=subprocess\.PIPE/, 'frontend-endpoints:bounded-stage-capture', 'The frontend test gate captures stage output instead of replaying raw logs.');
  requireText('scripts/frontend_test_gate.py', /<testsuite tests=\"1\" failures=\"1\"/, 'frontend-endpoints:junit-failure-fallback', 'Every failed frontend gate stage emits a bounded single-test JUnit fallback.');
  requireText('scripts/frontend_test_gate.py', /<testcase name=\"\{token\}\"><failure message=\"bounded-stage-failure\"\/>/, 'frontend-endpoints:junit-causal-identity', 'The JUnit fallback binds only the redacted causal or stage identity.');
  requireText('scripts/frontend_test_gate.py', /match = re\.match\(r"\^\(\?:FAILED\|ERROR\)\\s\+\(\[\^\\s\]\+\)"/, 'frontend-endpoints:pytest-causal-token', 'The gate extracts only the first whitespace-free Pytest FAILED or ERROR identity.');
  requireText('scripts/frontend_test_gate.py', /name="endpoint-python-regressions"[\s\S]*failure_identity="scripts\/tests::frontend_endpoint_python"[\s\S]*forward_causal_output=True/, 'frontend-endpoints:pytest-causal-forwarding', 'The Python regression stage forwards bounded causal test identities.');
  forbidText('scripts/frontend_test_gate.py', /shell\s*=\s*True/, 'frontend-endpoints:no-shell-gate', 'The frontend test gate must never execute through a shell.');
  requireText('scripts/vitest_causal_runner.py', /print\(f"FAILED \{causal\}"\)/, 'frontend-endpoints:causal-failure-identity', 'The causal runner emits a Pytest-compatible file and test identity.');
  requireText('scripts/vitest_causal_runner.py', /stdout=subprocess\.DEVNULL[\s\S]*stderr=subprocess\.DEVNULL/, 'frontend-endpoints:no-raw-vitest-output', 'The causal runner does not project raw Vitest stdout or stderr.');
  requireText('scripts/vitest_causal_runner.py', /tempfile\.TemporaryDirectory/, 'frontend-endpoints:ephemeral-raw-vitest-report', 'Raw Vitest JSON exists only in an automatically deleted temporary directory.');
  requireText('scripts/vitest_causal_runner.py', /"rawReportPersisted": False/, 'frontend-endpoints:redacted-summary-only', 'Persisted Vitest evidence explicitly records that the raw report was not retained.');
  requireText('scripts/vitest_causal_runner.py', /vitest-\{label\}-summary\.json/, 'frontend-endpoints:bounded-summary-path', 'Only a bounded redacted Vitest summary is written to the security report directory.');
  forbidText('scripts/vitest_causal_runner.py', /shell\s*=\s*True/, 'frontend-endpoints:no-shell-runner', 'The causal runner must never invoke Vitest through a shell.');
  requireText('tests/e2e/frontend-endpoint-contract-smoke.spec.ts', /legacyImportViolationCount\)\.toBe\(0\)/, 'frontend-endpoints:e2e-import-readback', 'Browser smoke reads the import-boundary verdict from the exact report.');
  requireText('tests/e2e/frontend-endpoint-contract-smoke.spec.ts', /activeMutationWithoutTestEvidenceCount\)\.toBe\(0\)/, 'frontend-endpoints:e2e-mutation-test-readback', 'Browser smoke reads the mutation test-evidence verdict from the exact report.');
  requireText('tests/e2e/frontend-endpoint-contract-smoke.spec.ts', /unexpectedApiRequests\)\.toEqual\(\[\]\)/, 'frontend-endpoints:e2e-unexpected-api-denial', 'Browser smoke fails when the tested journey emits an unexpected first-party API request.');
  requireText('tests/e2e/frontend-endpoint-contract-smoke.spec.ts', /pageErrors\)\.toEqual\(\[\]\)/, 'frontend-endpoints:e2e-pageerror-denial', 'Browser smoke fails on uncaught page errors.');
  requireText('tests/e2e/frontend-endpoint-contract-smoke.spec.ts', /externalTargetReachabilityProven:\s*false/, 'frontend-endpoints:e2e-truth-boundary', 'Browser smoke does not promote adapter observations to external runtime truth.');
  requireText('src/features/ai/providerManager.ts', /sovereign-endpoint-surface:\s*legacy-unreferenced/, 'providers:legacy-direct-manager-classified', 'Historical direct provider manager is explicitly outside the current production graph.');
  requireText('src/features/product/llm/sovereignLlmAdapters.ts', /createPrimaryBridgeAdapter/, 'providers:backend-bridge-active', 'Current product LLM adapters retain the backend-owned online bridge.');
  requireText('src/features/product/llm/sovereignLlmAdapters.ts', /createLocalSafeAdapter/, 'providers:local-safe-active', 'Current product LLM adapters retain the local non-network fallback.');
  forbidText('src/features/product/llm/sovereignLlmAdapters.ts', /create(?:Groq|HuggingFace|Mlvoca|OpenRouter|Pollinations|Together)Adapter/, 'providers:no-direct-browser-adapters', 'Current product LLM assembly must not reactivate direct browser provider adapters.');
  forbidText('src/features/billing/billingSlice.ts', /\/api\/billing\/(?:cancel|restore)/, 'billing:no-phantom-endpoints', 'Billing frontend must not call unimplemented cancel or restore routes.');

  requireImport('src/main.tsx', /\.\/SovereignAppWrapper$/, 'main:imports-wrapper', 'main.tsx imports the Sovereign runtime wrapper.');
  requireText('src/main.tsx', /<App\s*\/>|<App[\s>]/, 'main:renders-app', 'main.tsx renders App through the wrapper import.');
  requireText('src/main.tsx', /installViewportRuntime/, 'main:viewport-runtime', 'main.tsx installs viewport runtime.');
  requireText('src/main.tsx', /installCodeWorkspacePersistenceRuntime/, 'main:workspace-persistence', 'main.tsx installs workspace persistence runtime.');
  forbidText('src/main.tsx', /installMobileAgentMonitor|installMobileMoreMenu|installMobileSetupDrawer|installMobileWorkspaceOrder|installMobileRuntimeModules/, 'main:no-old-dom-installers', 'main.tsx must not install old DOM/mobile mutation helpers.');

  requireText('src/SovereignAppWrapper.tsx', /<App\s*\/>|<App[\s>]/, 'wrapper:renders-inner-app', 'Sovereign wrapper renders the inner App without owning product truth.');
  requireText('src/SovereignAppWrapper.tsx', /return <App \/>|<App\s*\/>/, 'wrapper:passthrough-only', 'Sovereign wrapper is a passthrough and does not create product truth.');
  forbidText('src/SovereignAppWrapper.tsx', /useState|useEffect|localStorage|sessionStorage|querySelector/, 'wrapper:no-own-runtime-state', 'Sovereign wrapper must not own runtime state or inspect DOM.');
  requireText('src/App.tsx', /PlayReleaseChat/, 'app:play-release-chat-root', 'App routes the Google Play release root to the focused chat surface.');
  forbidText('src/App.tsx', /BuilderContainer|LiveWorkspaceMonitor|LlmAdapterProvider|createSovereignAgentClient|onStartAgent/, 'app:no-deferred-monitor-root-wiring', 'Google Play release root must not remount deferred monitor or direct agent wiring.');
  requireText('src/features/release/PlayReleaseChat.tsx', /fetchSovereignLlmRouteCatalog/, 'play-chat:route-catalog', 'Play release chat uses the server-owned LLM route catalog.');
  requireText('src/features/release/PlayReleaseChat.tsx', /fetchDevChatWorkerReply/, 'play-chat:backend-worker', 'Play release chat sends ordinary conversation through the backend-owned worker bridge.');
  requireText('src/features/release/PlayReleaseChat.tsx', /parseDevChatGithubUrl/, 'play-chat:github-target-binding', 'Play release chat binds an exact GitHub repository URL before repository execution.');
  requireText('src/features/release/PlayReleaseChat.tsx', /fetchSovereignDirectLlmInterpretation/, 'play-chat:llm-action-boundary', 'Play release chat uses the LLM intent schema rather than browser keyword heuristics for repository actions.');
  requireText('src/features/release/PlayReleaseChat.tsx', /startRepositoryExecution/, 'play-chat:repository-execution', 'Play release chat reaches the canonical repository Agent runtime.');
  requireText('src/features/release/PlayReleaseChat.tsx', /interpretation\.intent === 'draft_pr'[\s\S]{0,1400}setPendingRepositoryAction\(/, 'play-chat:draft-pr-explicit-consent', 'A Draft-PR LLM intent only creates a visible pending action and never publishes immediately.');
  requireText('src/features/release/PlayReleaseChat.tsx', /pending\.kind === 'draft-pr'[\s\S]{0,600}publishDraftForJob\(pending\.job\)/, 'play-chat:draft-pr-visible-confirmation', 'Draft-PR publication remains reachable only from the explicit pending-action confirmation path.');
  requireText('src/features/release/PlayReleaseChat.tsx', /prepareDraftPr[\s\S]*createDraftPr/, 'play-chat:draft-pr-readback-chain', 'Play release chat preserves prepare-before-create Draft PR verification.');
  requireText('src/features/release/PlayReleaseChat.tsx', /Kein externer GitHub-Write wurde ausgeführt/, 'play-chat:no-implicit-publish', 'A direct patch does not silently become an external GitHub write.');
  requireText('src/features/release/PlayReleaseChat.tsx', /evaluateInputPolicy\(text\)/, 'play-chat:secret-input-guard', 'Play release chat evaluates secret-shaped input before sending it to the LLM bridge.');
  forbidText('src/features/release/PlayReleaseChat.tsx', /getDesktopFrame|VncScreen|LiveWorkspaceMonitor/, 'play-chat:no-monitor-runtime', 'Google Play release chat must stay free of deferred desktop-monitor runtime dependencies.');
  forbidText('src/App.tsx', retiredAppAgentPattern, 'app:no-retired-agent-wiring', 'App must not restore retired external-agent client or start symbols.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /parseDevChatGithubUrl/, 'builder:repo-url-monitor-detection', 'Builder detects exact GitHub repo URLs from the monitor communication dock.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /fetchDevChatRepoTree/, 'builder:repo-tree-runtime-load', 'Builder loads repo snapshots through the runtime bridge.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /validateGitHubTokenForRepo/, 'builder:github-access-validation', 'Builder validates GitHub access before write execution.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /SovereignActionStreamPanel/, 'builder:action-stream-visible', 'Builder shows route-agnostic action stream state.');

  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /sovereign:setup-state/, 'repo:setup-state-event', 'Repo setup publishes setup-state events.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /onLoadRepo/, 'repo:load-handler-prop', 'Repo container exposes load handler.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /data-mobile-role="github-repo-url-input"|data-role=\{SOVEREIGN_FORM_REPO_URL\.dataRole\}/, 'repo:mobile-repo-input', 'Repo URL input keeps Android/mobile or contract role.');
  requireText('src/features/product/containers/RepoSnapshotContainer.tsx', /data-mobile-role="github-token-input"|data-role=\{SOVEREIGN_FORM_PRIVATE_ACCESS\.dataRole\}/, 'repo:mobile-access-input', 'Access input keeps Android/mobile or contract role.');

  requireText('src/features/product/containers/BuilderContainer.tsx', /MonitorCommunicationDock/, 'builder:monitor-input-visible', 'Builder exposes LLM communication inside the monitor instead of a chat-first surface.');
  requireText('src/features/product/containers/BuilderContainer.tsx', /live-desktop-monitor-primary/, 'builder:monitor-primary-layout', 'Builder declares the permanent monitor-first primary layout.');
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
