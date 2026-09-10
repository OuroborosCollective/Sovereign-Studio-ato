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
  const surface = 'src/features/control-surface-vnext/App.tsx';
  const adapter = 'src/features/control-surface-vnext/adapter/production-adapter.ts';
  const adapterContext = 'src/features/control-surface-vnext/adapter/context.tsx';
  const chat = 'src/features/control-surface-vnext/components/ChatSurface/ChatSurface.tsx';
  const publication = 'src/features/control-surface-vnext/components/PublicationInspector/PublicationInspector.tsx';
  const operatorAuth = 'src/features/control-surface-vnext/components/Auth/OperatorAuthModal.tsx';
  const runtimeMonitor = 'src/features/control-surface-vnext/components/RuntimeMonitor/RuntimeMonitor.tsx';
  const workspaceProjection = 'src/features/control-surface-vnext/components/WorkspaceProjection/WorkspaceProjection.tsx';
  const integrationProjection = 'src/features/control-surface-vnext/components/IntegrationPlus/IntegrationModal.tsx';
  const agentClient = 'src/features/product/runtime/sovereignAgentClient.ts';
  const builder = 'src/features/product/containers/BuilderContainer.tsx';
  const monitor = 'src/features/product/components/LiveWorkspaceMonitor.tsx';
  const forms = 'src/features/product/runtime/sovereignFormContracts.ts';
  const actions = 'src/features/product/runtime/sovereignActionContracts.ts';

  for (const [file, message] of [
    ['src/index.css', 'Shared CSS and design tokens are required.'],
    ['src/main.tsx', 'App entry is required.'],
    [app, 'Canonical App route is required.'],
    [wrapper, 'Passthrough app wrapper is required.'],
    [surface, 'Sovereign Control Surface vNext is required.'],
    [adapter, 'The single live production adapter is required.'],
    [adapterContext, 'Adapter dependency injection boundary is required.'],
    [chat, 'Mission command surface is required.'],
    [publication, 'Evidence-gated Draft PR publication surface is required.'],
    [operatorAuth, 'Backend-session operator authentication surface is required.'],
    [runtimeMonitor, 'Runtime readback projection is required.'],
    [workspaceProjection, 'Workspace evidence projection is required.'],
    [integrationProjection, 'Read-only integration projection is required.'],
    [agentClient, 'Existing strict Agent/Draft-PR client remains canonical.'],
    [builder, 'Builder diagnostics remain a maintained secondary surface.'],
    [monitor, 'Real workspace monitor remains available as a diagnostic surface.'],
    [forms, 'Form contracts remain available.'],
    [actions, 'Action contracts remain available.'],
    ['src/styles/arelogic-brand.css', 'ARELogic visual tokens remain required.'],
  ]) requireFile(file, message);

  requireText('src/main.tsx', /\.\/styles\/arelogic-brand\.css/, 'main:brand-css', 'App entry imports ARELogic brand CSS.');
  requireText(wrapper, /return <App \/>|<App\s*\/\>/, 'wrapper:passthrough', 'Wrapper remains truth-neutral passthrough.');
  forbidText(wrapper, /useState|useEffect|localStorage|sessionStorage|data-testid="sovereign-app-wrapper"/, 'wrapper:no-shadow-state', 'Wrapper must not own product truth or persistence.');

  requireText(app, /SovereignControlSurfaceVNext/, 'app:vnext-primary', 'App renders Sovereign Control Surface vNext as the primary product surface.');
  requireText(app, /data-testid="sovereign-chat-app"/, 'app:root-test-id', 'Primary app has a stable root test id.');
  requireText(app, /data-layout="sovereign-control-surface-vnext"/, 'app:layout', 'Primary app identifies the vNext layout.');
  requireText(app, /data-primary-surface="sovereign-control-surface-vnext"/, 'app:primary-marker', 'Primary surface identity is explicit.');
  requireText(app, /data-truth-scope="runtime-readback-only"/, 'app:truth-scope', 'Runtime-readback-only truth scope is explicit.');
  requireText(app, /EvidenceObservatoryAtlas[\s\S]*\/observatory[\s\S]*\/evidence-observatory/, 'app:observatory-separated', 'Evidence Observatory remains an explicit non-default route.');
  forbidText(app, /PlayReleaseChat|RESTORE_LATEST_JOB|BuilderContainer/, 'app:no-retired-primary', 'Default App must not mount the retired release chat, auto-adopt historical jobs, or mount Builder as current truth.');

  requireText(adapterContext, /new SovereignProductionAdapter\(\)/, 'adapter:production-default', 'The default injected adapter is the live production adapter.');
  requireText(adapter, /credentials:\s*'include'/, 'adapter:http-only-session', 'Production requests rely on the backend HTTP-only session.');
  requireText(adapter, /'\/api\/user\/agent\/swarm\/run'/, 'adapter:swarm-run', 'Mission dispatch uses the persisted Agents SDK run endpoint.');
  requireText(adapter, /\/api\/user\/agent\/swarm\/runs\/\$\{encodeURIComponent\(requested\)\}/, 'adapter:run-readback', 'Persisted run identity is read back by exact run id.');
  requireText(adapter, /this\.client\.getJob\(run\.jobId\)/, 'adapter:linked-job', 'Implementation work is read through the linked backend job id.');
  requireText(adapter, /this\.client\.getEvidenceAnchors\(run\.jobId\)/, 'adapter:evidence-anchors', 'Workspace revision comes from evidence anchors.');
  requireText(adapter, /this\.client\.prepareDraftPr\(run\.jobId\)/, 'adapter:draft-prepare', 'Draft PR preparation uses the existing server gate.');
  requireText(adapter, /this\.client\.createDraftPr\(run\.jobId\)/, 'adapter:draft-create', 'Draft PR creation delegates to the existing strict client.');
  forbidText(adapter, /MockSovereignBackendAdapter|fallbackMock|\/api\/config\/|sessionToken|Authorization:\s*`Bearer|localStorage/, 'adapter:no-simulated-truth', 'Production adapter must not contain simulator fallback, guessed config APIs, bearer-session state, or local persistence.');

  requireText(agentClient, /jobPath\(jobId, '\/draft-pr\/prepare'\)/, 'client:draft-prepare-path', 'Canonical client owns the Draft PR prepare path.');
  requireText(agentClient, /jobPath\(jobId, '\/draft-pr\/create'\)/, 'client:draft-create-path', 'Canonical client owns the Draft PR create path.');
  requireText(agentClient, /signal\.draftVerified === true[\s\S]*prStateVerified[\s\S]*signal\.readbackVerified === true[\s\S]*signal\.checksReadbackVerified === true/, 'client:github-readback', 'Draft PR success requires draft/open/head/check readback evidence.');

  requireText(chat, /value=\{text\}[\s\S]*setText\(event\.target\.value\)/, 'surface:composer-bound', 'Visible mission composer is bound to local command draft state only.');
  requireText(chat, /data-testid="builder__start-task"[\s\S]*onClick=\{submit\}/, 'surface:send-visible', 'Visible dispatch button invokes the guarded submit handler.');
  requireText(chat, /event\.key === 'Enter'[\s\S]*submit\(\)/, 'surface:enter-send-bound', 'Enter uses the same guarded submit handler.');
  requireText(surface, /ensureGuestSession\(\)/, 'surface:session-readback', 'Control surface resolves backend session before protected dispatch.');
  requireText(surface, /user\.isGuest[\s\S]*setAuthOpen\(true\)/, 'surface:guest-fail-closed', 'Guest execution fails closed into explicit authentication.');
  requireText(surface, /setActiveRunId\(accepted\.jobId\)/, 'surface:accepted-run-id', 'Only the backend-accepted persisted run id becomes current.');
  forbidText(surface, /listJobs\(|RESTORE_LATEST_JOB/, 'surface:no-history-auto-adopt', 'vNext must not auto-adopt historic Agent jobs.');

  requireText(publication, /READ DRAFT-PR GATE/, 'publication:prepare-visible', 'Draft PR prepare is a separate visible action.');
  requireText(publication, /EXTERNAL WRITE CONSENT/, 'publication:consent-visible', 'External GitHub write consent is visible.');
  requireText(publication, /No merge\. No push to main\./, 'publication:no-merge', 'Publication explicitly excludes merge and main push.');
  requireText(publication, /Success is shown only after independent GitHub readback\./, 'publication:readback-claim', 'Publication success is explicitly bound to GitHub readback.');
  requireText(publication, /data-testid="vnext-create-draft-pr"/, 'publication:create-visible', 'Confirmed Draft PR action has a stable visible control.');

  requireText(operatorAuth, /useUserStore/, 'auth:backend-store', 'Operator auth uses the canonical backend session store.');
  requireText(operatorAuth, /loginWithAccountKey/, 'auth:account-key', 'Account-key authentication is sent through the backend session boundary.');
  forbidText(operatorAuth, /sessionToken|localStorage|Authorization:\s*`Bearer/, 'auth:no-browser-token', 'Operator auth must not persist or construct a browser bearer session token.');

  requireText(runtimeMonitor, /No runtime readback yet\./, 'monitor:empty-honest', 'Runtime monitor has an explicit no-readback empty state.');
  requireText(runtimeMonitor, /Nothing is synthesized to fill this panel\./, 'monitor:no-synthesis', 'Runtime monitor explicitly refuses synthesized evidence.');
  requireText(workspaceProjection, /REVISION UNVERIFIED/, 'workspace:revision-unverified', 'Workspace shows unverified revision until evidence supplies it.');
  requireText(workspaceProjection, /This does not claim the repository is globally clean\./, 'workspace:no-global-clean-claim', 'Empty changed-file projection does not claim global clean state.');
  requireText(integrationProjection, /read-only[\s\S]*does not invent attachment state/, 'integration:read-only', 'Integration projection remains read-only until a real server contract exists.');

  requireText(forms, /SOVEREIGN_FORM_REPO_URL/, 'form:repo-url', 'Repo URL contract remains defined.');
  requireText(forms, /SOVEREIGN_FORM_PRIVATE_ACCESS/, 'form:private-access', 'Private-access contract remains defined.');
  requireText(forms, /sensitive:\s*true/, 'form:sensitive', 'Sensitive form fields remain marked.');
  requireText(forms, /inputType:\s*['"]password['"]/, 'form:password', 'Private access remains password-typed.');
  requireText(actions, /SOVEREIGN_ACTION_DRAFT_PR/, 'action:draft-pr', 'Draft PR action contract remains defined.');
  requireText(actions, /SOVEREIGN_ACTION_LOAD_REPO/, 'action:load-repo', 'Repository load action contract remains defined.');

  requireText(builder, /MonitorCommunicationDock|SovereignActionStreamPanel/, 'builder:secondary-diagnostics', 'Builder retains diagnostic/action-stream capability as a secondary surface.');
  requireText(monitor, /live-workspace-monitor-desktop|DESKTOP · LIVE READBACK/, 'monitor:desktop-readback', 'Legacy real desktop readback remains available only as a diagnostic surface.');

  requireText('src/index.css', /@media[\s\S]*max-width/, 'css:responsive', 'Responsive CSS remains present.');
  forbidText(app, /ProductMagicApp|tabbar__root|automation__panel|operator-monitor/, 'app:no-retired-shell', 'Retired product/dashboard shells must stay out of the live App route.');
}

try { run(); }
catch (error) { fail('ux:unexpected-error', 'UX contract scan crashed.', { error: String(error) }); }
finally { writeReport(); }

if (report.errors.length > 0) process.exit(1);
