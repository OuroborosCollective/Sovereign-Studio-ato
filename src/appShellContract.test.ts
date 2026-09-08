import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const MAIN_PATH = 'src/main.tsx';
const APP_PATH = 'src/App.tsx';
const WRAPPER_PATH = 'src/SovereignAppWrapper.tsx';
const CSS_PATH = 'src/index.css';
const RELEASE_PATH = 'src/features/release/PlayReleaseChat.tsx';

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
    expect(existsSync(RELEASE_PATH)).toBe(true);
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

  it('makes PlayReleaseChat the current-session primary surface and keeps observatory truth separate', () => {
    const app = read(APP_PATH);
    const release = read(RELEASE_PATH);

    expectContainsAll(app, [
      'PlayReleaseChat',
      'data-testid="sovereign-chat-app"',
      'data-layout="chat-first-agent-zero-background"',
      'data-primary-surface="play-release-chat"',
      'data-truth-scope="current-chat-session-only"',
      'aria-label="Sovereign Chat"',
      'EvidenceObservatoryAtlas',
    ]);
    expectContainsNone(app, [...REMOVED_VISIBLE_SHELL_TOKENS, 'RESTORE_LATEST_JOB', 'BuilderContainer']);

    expectContainsAll(release, [
      'startRepositoryExecution',
      'prepareDraftPr',
      'createDraftPr',
      'Draft PR erstellen',
      'readbackHeadSha',
      'GitHub-Änderungsentwurf erkannt',
    ]);
    expect(release).not.toContain('listJobs(');
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
