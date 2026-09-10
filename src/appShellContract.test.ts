import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const MAIN_PATH = 'src/main.tsx';
const APP_PATH = 'src/App.tsx';
const WRAPPER_PATH = 'src/SovereignAppWrapper.tsx';
const CSS_PATH = 'src/index.css';
const CONTROL_SURFACE_PATH = 'src/features/control-surface-vnext/App.tsx';
const PRODUCTION_ADAPTER_PATH = 'src/features/control-surface-vnext/adapter/production-adapter.ts';
const AGENT_CLIENT_PATH = 'src/features/product/runtime/sovereignAgentClient.ts';

const DOM_INSTALLER_TOKENS = [
  'installMobileAgentMonitor',
  'installMobileMoreMenu',
  'installMobileSetupDrawer',
  'installMobileWorkspaceOrder',
  'installMobileRuntimeModules',
  'installGlobalRuntimeMonitor',
];

const REMOVED_VISIBLE_SHELL_TOKENS = [
  'RepoInsightPanelBridge',
  'RepoSnapshotContainer',
  'WorkflowContainer',
  'TelemetryContainer',
  'PatternMemoryContainer',
  'SettingsModal',
  'Sovereign Canvas Tool',
  'automation__panel',
  'tabbar__root',
  'operator-monitor',
  'Sovereign Arbeitsfläche öffnen',
];

const REMOVED_WRAPPER_NAV_TOKENS = [
  'WorkspaceMenu',
  'publishWorkspaceCommand',
  'SOVEREIGN_WORKSPACE_MENU',
  'SOVEREIGN_WORKSPACE_COMMAND_EVENT',
  'createSovereignWorkspaceCommand',
  'sovereign-wrapper-workspace-menu',
  'sovereign-wrapper-menu__${item.id}',
  'composition-wrapper-around-existing-app',
  'MinimalAppShell',
  'MinimalLampBar',
  'minimal-app-shell',
  'sovereign-minimal-lamp-bar',
  'sovereign-shell-content',
];

function read(path: string): string {
  expect(existsSync(path), `${path} must exist`).toBe(true);
  return readFileSync(path, 'utf8');
}

function expectContainsAll(source: string, tokens: string[]): void {
  for (const token of tokens) expect(source, `expected source to contain: ${token}`).toContain(token);
}

function expectContainsNone(source: string, tokens: string[]): void {
  for (const token of tokens) expect(source, `expected source not to contain: ${token}`).not.toContain(token);
}

describe('current Sovereign app shell contract', () => {
  it('keeps required shell source files present', () => {
    expect(existsSync(MAIN_PATH)).toBe(true);
    expect(existsSync(APP_PATH)).toBe(true);
    expect(existsSync(WRAPPER_PATH)).toBe(true);
    expect(existsSync(CSS_PATH)).toBe(true);
    expect(existsSync(CONTROL_SURFACE_PATH)).toBe(true);
    expect(existsSync(PRODUCTION_ADAPTER_PATH)).toBe(true);
    expect(existsSync(AGENT_CLIENT_PATH)).toBe(true);
  });

  it('boots the React wrapper and stable Android runtime helpers without global coach chrome', () => {
    const main = read(MAIN_PATH);
    const wrapper = read(WRAPPER_PATH);

    expectContainsAll(main, [
      "import App from './SovereignAppWrapper'",
      '<ErrorBoundary>',
      '<App />',
      "import './runtime-adapter'",
      "import './index.css'",
      'installIdleCallbackFallback();',
      'installViewportRuntime();',
      'installCodeWorkspacePersistenceRuntime();',
      'bootApp();',
    ]);
    expectContainsAll(wrapper, ["import App from './App'", '<App />', 'export default function SovereignAppWrapper']);
    expectContainsNone(wrapper, REMOVED_WRAPPER_NAV_TOKENS);
    expectContainsNone(main, DOM_INSTALLER_TOKENS);
  });

  it('makes the vNext control surface primary and keeps runtime truth behind one production adapter', () => {
    const app = read(APP_PATH);
    const controlSurface = read(CONTROL_SURFACE_PATH);
    const productionAdapter = read(PRODUCTION_ADAPTER_PATH);
    const agentClient = read(AGENT_CLIENT_PATH);

    expectContainsAll(app, [
      'SovereignControlSurfaceVNext',
      'data-testid="sovereign-chat-app"',
      'data-layout="sovereign-control-surface-vnext"',
      'data-primary-surface="sovereign-control-surface-vnext"',
      'data-truth-scope="runtime-readback-only"',
      'aria-label="Sovereign Control Surface"',
      'EvidenceObservatoryAtlas',
    ]);
    expectContainsNone(app, [...REMOVED_VISIBLE_SHELL_TOKENS, 'RESTORE_LATEST_JOB', 'BuilderContainer']);

    expectContainsAll(controlSurface, [
      'SovereignAdapterProvider',
      'useSovereignJob',
      'PublicationInspector',
      'RuntimeMonitor',
      'WorkspaceProjection',
    ]);
    expectContainsAll(productionAdapter, [
      "'/api/user/agent/swarm/run'",
      "'/api/user/agent/toolchain/manifest'",
      "'/api/user/agent/swarm/manifest'",
      'this.client.prepareDraftPr(run.jobId)',
      'this.client.createDraftPr(run.jobId)',
      'credentials: \'include\'',
      'createSovereignAgentClient',
    ]);
    expectContainsAll(agentClient, [
      "jobPath(jobId, '/draft-pr/prepare')",
      "jobPath(jobId, '/draft-pr/create')",
      'signal.draftVerified === true',
      "stringValue(signal.prStateVerified) === 'open'",
      'signal.readbackVerified === true',
      'signal.checksReadbackVerified === true',
    ]);
    expectContainsNone(productionAdapter, ['MockSovereignBackendAdapter', '/api/config/', 'sessionToken', 'localStorage']);
  });

  it('keeps the wrapper free of visible chrome and navigation state', () => {
    const wrapper = read(WRAPPER_PATH);

    expectContainsAll(wrapper, ["import App from './App'", 'return <App />']);
    expectContainsNone(wrapper, REMOVED_WRAPPER_NAV_TOKENS);
    expect(wrapper).not.toContain('querySelector');
    expect(wrapper).not.toContain('localStorage');
    expect(wrapper).not.toContain('sessionStorage');
  });
});
