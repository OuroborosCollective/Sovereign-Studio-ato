#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const REPORT_DIR = '.security-reports';
const REPORT_PATH = path.join(REPORT_DIR, 'sovereign-runtime-contract.json');
const retiredAgentName = ['Open', 'Hands'].join('');
const retiredBuilderAgentPattern = new RegExp(`onStart${retiredAgentName}`);

const report = {
  name: 'Sovereign Runtime Contract Scan',
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
function hasAnyScript(scripts, names) { return names.filter((name) => typeof scripts[name] === 'string'); }
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
    const summaryPath = path.resolve(process.env.GITHUB_STEP_SUMMARY);
    const workspaceRoot = path.resolve(process.cwd());
    const relative = path.relative(workspaceRoot, summaryPath);
    if (relative && !relative.startsWith('..') && !path.isAbsolute(relative)) {
      fs.appendFileSync(summaryPath, [
        '## Sovereign Runtime Contract Scan', '',
        `Status: **${report.status}**`,
        `Checks: **${report.checks.length}**`,
        `Errors: **${report.errors.length}**`,
        `Warnings: **${report.warnings.length}**`, '',
        ...(report.errors.length ? report.errors.map((item) => `- ${item.id}: ${item.message}`) : ['- none']),
        '',
      ].join('\n'));
    } else {
      warn('scanner:invalid-summary-path', 'Skipping unsafe GITHUB_STEP_SUMMARY path.');
    }
  }
  console.log(JSON.stringify(report, null, 2));
}

function run() {
  const surface = 'src/features/control-surface-vnext/App.tsx';
  const adapter = 'src/features/control-surface-vnext/adapter/production-adapter.ts';
  const repositoryAdapter = 'src/features/control-surface-vnext/adapter/repository-bound-adapter.ts';
  const adapterContext = 'src/features/control-surface-vnext/adapter/context.tsx';
  const publication = 'src/features/control-surface-vnext/components/PublicationInspector/PublicationInspector.tsx';
  const agentClient = 'src/features/product/runtime/sovereignAgentClient.ts';
  const builder = 'src/features/product/containers/BuilderContainer.tsx';

  for (const [file, message] of [
    ['package.json', 'Root package manifest is required.'],
    ['pnpm-lock.yaml', 'Frozen pnpm lockfile is required.'],
    ['src/main.tsx', 'React entrypoint is required.'],
    ['src/App.tsx', 'App shell is required.'],
    ['src/SovereignAppWrapper.tsx', 'Passthrough wrapper is required.'],
    [surface, 'Sovereign Control Surface vNext is required.'],
    [adapter, 'Sovereign vNext production adapter is required.'],
    [repositoryAdapter, 'Sovereign vNext repository-bound adapter is required.'],
    [adapterContext, 'Sovereign vNext adapter context is required.'],
    [publication, 'Sovereign vNext publication inspector is required.'],
    [agentClient, 'Canonical Agent client is required.'],
    ['src/features/product/components/LiveWorkspaceMonitor.tsx', 'Live workspace monitor diagnostic surface is required.'],
    ['src/features/product/components/MonitorCommunicationDock.tsx', 'Compact monitor communication dock is required.'],
    ['src/index.css', 'Shared design CSS is required.'],
    ['src/features/product/containers/RepoSnapshotContainer.tsx', 'Repo snapshot container is required.'],
    [builder, 'Builder secondary diagnostic container is required.'],
    ['src/features/product/runtime/sovereignTelemetry.ts', 'Telemetry runtime is required.'],
    ['src/features/product/runtime/runtimeOutcomeGuard.ts', 'Outcome guard runtime is required.'],
    ['src/features/product/runtime/sequentialRuntimeGuard.ts', 'Sequential runtime guard is required.'],
    ['scripts/frontend_endpoint_contracts.py', 'Frontend endpoint contract compiler is required.'],
    ['scripts/tests/test_frontend_endpoint_contracts.py', 'Frontend endpoint compiler regressions are required.'],
    ['scripts/vitest_causal_runner.py', 'Bounded Vitest causal evidence runner is required.'],
    ['scripts/tests/test_vitest_causal_runner.py', 'Vitest causal evidence runner regressions are required.'],
    ['scripts/frontend_test_gate.py', 'Shell-free frontend test gate orchestrator is required.'],
    ['scripts/tests/test_frontend_test_gate.py', 'Frontend test gate orchestrator regressions are required.'],
    ['tests/e2e/frontend-endpoint-contract-smoke.spec.ts', 'Built-browser endpoint smoke is required.'],
    ['src/features/admin/api/adminApiClient.ownerInput.test.ts', 'Protected owner-input endpoint regression is required.'],
    ['src/features/billing/billingSlice.test.ts', 'Billing endpoint regression is required.'],
    ['src/features/knowledge/knowledgeApi.test.ts', 'Knowledge endpoint regression is required.'],
    ['src/features/rescue/rescueClient.test.ts', 'Rescue endpoint regression is required.'],
    ['src/features/toolchain/toolchainApi.test.ts', 'Toolchain endpoint regression is required.'],
    ['src/features/toolchain/skillsApi.test.ts', 'Skill endpoint regression is required.'],
    ['docs/architecture/FRONTEND_ENDPOINT_CONTRACTS.v1.md', 'Frontend endpoint truth-boundary documentation is required.'],
  ]) requireFile(file, message);

  const scripts = getPackageScripts();
  requireScriptGroup(scripts, 'script:type-check', ['type-check', 'typecheck', 'check:types'], 'TypeScript check script is available.');
  requireScriptGroup(scripts, 'script:test', ['test:ci', 'test:run', 'test'], 'Unit test script is available.');
  requireScriptGroup(scripts, 'script:build', ['build', 'web:build'], 'Build script is available.');
  warnScriptGroup(scripts, 'script:lint', ['lint'], 'Lint script is available.');
  requireScriptGroup(scripts, 'script:frontend-endpoints', ['test:frontend-endpoints'], 'Frontend endpoint compiler and regression script is available.');
  requireScriptGroup(scripts, 'script:frontend-endpoints-e2e', ['test:e2e:frontend-endpoints'], 'Frontend endpoint Playwright smoke script is available.');

  requireText('.github/workflows/sovereign-contract-scan.yml', /run_first_present test:smoke/, 'workflow:frontend-endpoint-contracts', 'Runtime contract workflow executes the canonical smoke gate.');
  requireText('package.json', /"test:smoke"\s*:\s*"python3 scripts\/frontend_test_gate\.py --mode smoke"/, 'workflow:frontend-endpoint-smoke-chain', 'Canonical smoke gate uses the shell-free frontend test orchestrator.');
  requireText('package.json', /"test:frontend-endpoints"\s*:\s*"python3 scripts\/frontend_endpoint_assurance\.py --no-write && python3 scripts\/frontend_test_gate\.py --mode endpoint"/, 'workflow:frontend-endpoint-targeted-chain', 'Targeted endpoint gate preserves endpoint assurance.');
  requireText('.github/workflows/e2e-testing.yml', /pnpm run test:e2e/, 'workflow:frontend-endpoint-e2e', 'Current App E2E workflow executes the Playwright suite.');

  requireText('scripts/frontend_endpoint_contracts.py', /"externalCalls"/, 'frontend-endpoints:external-inventory', 'Endpoint compiler separates third-party requests from backend routes.');
  requireText('scripts/frontend_endpoint_contracts.py', /legacyImportViolationCount/, 'frontend-endpoints:legacy-import-gate', 'Endpoint compiler rejects reactivation of legacy endpoint surfaces.');
  requireText('scripts/frontend_endpoint_contracts.py', /FRONTEND_MUTATION_TEST_EVIDENCE_MISSING/, 'frontend-endpoints:mutation-test-gate', 'Active mutation requests require test evidence.');
  requireText('scripts/frontend_endpoint_contracts.py', /activeMutationWithoutTestEvidenceCount/, 'frontend-endpoints:mutation-test-count', 'Endpoint report exposes mutation-test evidence count.');
  requireText('scripts/frontend_test_gate.py', /adminApiClient\.ownerInput\.test\.ts[\s\S]*billingSlice\.test\.ts[\s\S]*knowledgeApi\.test\.ts[\s\S]*rescueClient\.test\.ts[\s\S]*toolchainApi\.test\.ts[\s\S]*skillsApi\.test\.ts/, 'frontend-endpoints:targeted-client-tests', 'Frontend gate executes all targeted client regressions.');
  requireText('scripts/frontend_test_gate.py', /stdout=subprocess\.PIPE[\s\S]*stderr=subprocess\.PIPE/, 'frontend-endpoints:bounded-stage-capture', 'Frontend gate captures bounded stage output.');
  forbidText('scripts/frontend_test_gate.py', /shell\s*=\s*True/, 'frontend-endpoints:no-shell-gate', 'Frontend test gate never executes through a shell.');
  requireText('scripts/vitest_causal_runner.py', /stdout=subprocess\.DEVNULL[\s\S]*stderr=subprocess\.DEVNULL/, 'frontend-endpoints:no-raw-vitest-output', 'Causal runner never projects raw Vitest logs.');
  requireText('scripts/vitest_causal_runner.py', /tempfile\.TemporaryDirectory/, 'frontend-endpoints:ephemeral-raw-vitest-report', 'Raw Vitest report is ephemeral.');
  forbidText('scripts/vitest_causal_runner.py', /shell\s*=\s*True/, 'frontend-endpoints:no-shell-runner', 'Causal runner never invokes Vitest through a shell.');

  requireText('tests/e2e/frontend-endpoint-contract-smoke.spec.ts', /legacyImportViolationCount\)\.toBe\(0\)/, 'frontend-endpoints:e2e-import-readback', 'Browser smoke reads import-boundary verdict.');
  requireText('tests/e2e/frontend-endpoint-contract-smoke.spec.ts', /activeMutationWithoutTestEvidenceCount\)\.toBe\(0\)/, 'frontend-endpoints:e2e-mutation-test-readback', 'Browser smoke reads mutation test-evidence verdict.');
  requireText('tests/e2e/frontend-endpoint-contract-smoke.spec.ts', /unexpectedApiRequests\)\.toEqual\(\[\]\)/, 'frontend-endpoints:e2e-unexpected-api-denial', 'Browser smoke rejects unexpected first-party API requests.');
  requireText('tests/e2e/frontend-endpoint-contract-smoke.spec.ts', /pageErrors\)\.toEqual\(\[\]\)/, 'frontend-endpoints:e2e-pageerror-denial', 'Browser smoke fails on uncaught page errors.');
  requireText('tests/e2e/frontend-endpoint-contract-smoke.spec.ts', /externalTargetReachabilityProven:\s*false/, 'frontend-endpoints:e2e-truth-boundary', 'Browser smoke does not promote adapter observations to external truth.');

  requireText('src/features/ai/providerManager.ts', /sovereign-endpoint-surface:\s*legacy-unreferenced/, 'providers:legacy-direct-manager-classified', 'Historical direct provider manager remains outside the production graph.');
  requireText('src/features/product/llm/sovereignLlmAdapters.ts', /createPrimaryBridgeAdapter/, 'providers:backend-bridge-active', 'Current LLM adapters retain the backend-owned bridge.');
  requireText('src/features/product/llm/sovereignLlmAdapters.ts', /createLocalSafeAdapter/, 'providers:local-safe-active', 'Current LLM adapters retain local safe fallback.');
  forbidText('src/features/product/llm/sovereignLlmAdapters.ts', /create(?:Groq|HuggingFace|Mlvoca|OpenRouter|Pollinations|Together)Adapter/, 'providers:no-direct-browser-adapters', 'Current product assembly must not reactivate direct browser provider adapters.');

  requireImport('src/main.tsx', /\.\/SovereignAppWrapper$/, 'main:imports-wrapper', 'main.tsx imports Sovereign wrapper.');
  requireText('src/main.tsx', /installViewportRuntime/, 'main:viewport-runtime', 'main.tsx installs viewport runtime.');
  requireText('src/main.tsx', /installCodeWorkspacePersistenceRuntime/, 'main:workspace-persistence', 'main.tsx installs workspace persistence runtime.');
  forbidText('src/main.tsx', /installMobileAgentMonitor|installMobileMoreMenu|installMobileSetupDrawer|installMobileWorkspaceOrder|installMobileRuntimeModules/, 'main:no-old-dom-installers', 'main.tsx must not install old DOM/mobile mutation helpers.');

  requireText('src/SovereignAppWrapper.tsx', /return <App \/>|<App\s*\/\>/, 'wrapper:passthrough-only', 'Wrapper is a passthrough and does not create product truth.');
  forbidText('src/SovereignAppWrapper.tsx', /useState|useEffect|localStorage|sessionStorage|querySelector/, 'wrapper:no-own-runtime-state', 'Wrapper must not own runtime state or inspect DOM.');

  requireText('src/App.tsx', /SovereignControlSurfaceVNext/, 'app:vnext-root', 'App routes the authenticated root to Sovereign Control Surface vNext.');
  requireText('src/App.tsx', /data-testid="sovereign-chat-app"/, 'app:vnext-root-test-id', 'vNext App exposes a stable root test id.');
  requireText('src/App.tsx', /data-layout="sovereign-control-surface-vnext"/, 'app:vnext-root-layout', 'vNext App exposes its canonical control-surface layout.');
  requireText('src/App.tsx', /data-primary-surface="sovereign-control-surface-vnext"/, 'app:primary-surface', 'vNext primary surface identity is explicit.');
  requireText('src/App.tsx', /data-truth-scope="runtime-readback-only"/, 'app:truth-scope', 'Runtime-readback-only truth scope is explicit.');
  requireText('src/App.tsx', /EvidenceObservatoryAtlas/, 'app:observatory-preserved', 'Evidence Observatory remains an explicit secondary route.');
  requireText('src/App.tsx', /window\.location\.pathname === '\/observatory'[\s\S]*window\.location\.pathname === '\/evidence-observatory'[\s\S]*get\('observatory'\) === '1'/, 'app:observatory-route-contract', 'Both observatory paths and query compatibility remain reachable.');
  forbidText('src/App.tsx', /PlayReleaseChat|RESTORE_LATEST_JOB|BuilderContainer/, 'app:no-implicit-historical-truth', 'Default App must not mount the retired release chat, auto-adopt historical jobs, or mount Builder as current truth.');

  requireText(surface, /ensureGuestSession\(\)[\s\S]*user\.isGuest[\s\S]*setAuthOpen\(true\)/, 'vnext:session-before-agent', 'vNext resolves backend session and fails guest execution closed into authentication.');
  requireText(surface, /useSwarmRun[\s\S]*setActiveRunId\(accepted\.jobId\)/, 'vnext:accepted-run', 'Only a backend-accepted persisted run id becomes current.');
  forbidText(surface, /listJobs\(|RESTORE_LATEST_JOB/, 'vnext:no-history-auto-adopt', 'vNext must not auto-adopt historical Agent runs.');
  requireText(adapterContext, /from ['"]\.\/repository-bound-adapter['"]/, 'vnext:repository-adapter-active', 'vNext context instantiates the repository-bound production adapter.');
  requireText(repositoryAdapter, /extends SovereignProductionAdapterBase/, 'vnext:repository-adapter-inherits-publication', 'Repository-bound vNext preserves the production Draft-PR publication contract by inheritance.');
  requireText(repositoryAdapter, /credentials:\s*'include'/, 'vnext:http-only-session', 'vNext repository requests use the backend HTTP-only session.');
  requireText(repositoryAdapter, /'\/api\/user\/agent\/repository\/run'/, 'vnext:agent-execution', 'vNext mission dispatch uses the dedicated persisted repository-run endpoint.');
  forbidText(repositoryAdapter, /\/api\/user\/agent\/swarm\//, 'vnext:no-repository-swarm-route', 'Repository-bound vNext must not route repository execution through Swarm endpoints.');
  requireText(adapter, /this\.client\.getJob\(run\.jobId\)[\s\S]*this\.client\.getEvidenceAnchors\(run\.jobId\)/, 'vnext:linked-job-evidence', 'Generic persisted runs retain linked implementation-job and evidence readback.');
  requireText(adapter, /const jobId = isDirectRepositoryJobId\(runId\)[\s\S]*this\.client\.prepareDraftPr\(jobId\)[\s\S]*this\.client\.createDraftPr\(jobId\)/, 'vnext:draft-pr-gate', 'Draft PR normalizes direct agent jobs or linked implementation jobs before prepare/create publication calls.');
  forbidText(adapter, /MockSovereignBackendAdapter|fallbackMock|\/api\/config\/|sessionToken|Authorization:\s*`Bearer|localStorage/, 'vnext:no-simulator-truth', 'Production adapter must not contain simulator fallback, guessed config routes, or browser-owned bearer state.');
  forbidText(repositoryAdapter, /MockSovereignBackendAdapter|fallbackMock|\/api\/config\/|sessionToken|Authorization:\s*`Bearer|localStorage/, 'vnext:no-repository-simulator-truth', 'Repository-bound adapter must not introduce simulator fallback, guessed config routes, or browser-owned bearer state.');
  requireText(agentClient, /jobPath\(jobId, '\/draft-pr\/prepare'\)[\s\S]*jobPath\(jobId, '\/draft-pr\/create'\)/, 'vnext:draft-pr-endpoints', 'Canonical Agent client owns the Draft PR prepare/create endpoints.');
  requireText(agentClient, /signal\.draftVerified === true[\s\S]*prStateVerified[\s\S]*signal\.readbackVerified === true[\s\S]*signal\.checksReadbackVerified === true/, 'vnext:draft-pr-readback', 'Draft PR success requires complete GitHub draft/open/head/check readback.');
  requireText(publication, /READ DRAFT-PR GATE[\s\S]*EXTERNAL WRITE CONSENT[\s\S]*CREATE DRAFT PR/, 'vnext:draft-pr-visible', 'Draft PR gate and external-write consent are visible.');
  requireText(publication, /No merge\. No push to main\.[\s\S]*independent GitHub readback/, 'vnext:draft-pr-consent', 'Publication explicitly excludes merge/main push and requires independent GitHub readback.');

  requireText(builder, /MonitorCommunicationDock|SovereignActionStreamPanel/, 'builder:secondary-diagnostics', 'Builder remains maintained as a secondary diagnostics surface.');
  forbidText(builder, retiredBuilderAgentPattern, 'builder:no-retired-agent-start-prop', 'Builder must not restore retired external-agent start prop.');
  requireText('src/features/product/components/LiveWorkspaceMonitor.tsx', /live-workspace-monitor-desktop|DESKTOP · LIVE READBACK/, 'monitor:desktop-readback', 'Real desktop readback remains available.');

  requireText('src/features/product/runtime/sovereignTelemetry.ts', /validateTelemetryEvent/, 'telemetry:event-validation', 'Telemetry event validation exists.');
  requireText('src/features/product/runtime/sovereignTelemetry.ts', /validateTelemetryState/, 'telemetry:state-validation', 'Telemetry state validation exists.');
  requireText('src/features/product/runtime/sovereignTelemetry.ts', /appendTelemetryEvent/, 'telemetry:append-event', 'Telemetry append path exists.');
  warnText('src/features/product/runtime/sovereignTelemetry.ts', /sovereign:telemetry-event/, 'telemetry:global-event-bus', 'Telemetry should publish to one global monitor bus.');
  requireText('src/features/product/runtime/runtimeOutcomeGuard.ts', /fulfilled|partial|blocked|noise|invalid/, 'outcome:status-contract', 'Outcome guard classifies runtime result states.');
  requireText('src/features/product/runtime/runtimeOutcomeGuard.ts', /learnable/, 'outcome:learnable-contract', 'Outcome guard exposes learnable flag.');
  requireText('src/features/product/runtime/sequentialRuntimeGuard.ts', /startSequentialStep/, 'sequential:start-step', 'Sequential runtime can start guarded steps.');
  requireText('src/features/product/runtime/sequentialRuntimeGuard.ts', /finishSequentialStep/, 'sequential:finish-step', 'Sequential runtime can finish guarded steps.');

  if (exists('src/global-runtime-monitor.tsx')) {
    pass('monitor:file-present', 'Global runtime monitor file exists.');
    requireText('src/global-runtime-monitor.tsx', /sovereign:runtime-coach-state/, 'monitor:coach-state-listener', 'Global monitor listens to runtime coach state.');
    requireText('src/global-runtime-monitor.tsx', /sovereign:telemetry-event/, 'monitor:telemetry-listener', 'Global monitor listens to telemetry events.');
  } else warn('monitor:file-missing', 'Global monitor is absent; secondary monitor remains available.');

  if (exists('android')) pass('android:directory', 'Android project directory exists.');
  else warn('android:directory', 'Android directory is absent.');
  if (exists('scripts/sovereign-static-audit.mjs')) pass('audit:static-audit-present', 'Existing static audit is present.');
  else warn('audit:static-audit-present', 'Existing static audit script is absent.');
}

try { run(); }
catch (error) { fail('scanner:unexpected-error', 'Runtime contract scanner crashed.', { error: String(error) }); }
finally { writeReport(); }

if (report.errors.length > 0) process.exit(1);
