import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const MAIN_PATH = 'src/main.tsx';
const APP_PATH = 'src/App.tsx';
const RELEASE_CHAT_PATH = 'src/features/release/PlayReleaseChat.tsx';
const LOGIN_PATH = 'src/features/user/components/LoginModal.tsx';
const WRAPPER_PATH = 'src/SovereignAppWrapper.tsx';
const CSS_PATH = 'src/index.css';

const DOM_INSTALLER_TOKENS = [
  'installMobileAgentMonitor',
  'installMobileMoreMenu',
  'installMobileSetupDrawer',
  'installMobileWorkspaceOrder',
  'installMobileRuntimeModules',
  'installGlobalRuntimeMonitor',
];

const REMOVED_WRAPPER_NAV_TOKENS = [
  'WorkspaceMenu',
  'publishWorkspaceCommand',
  'SOVEREIGN_WORKSPACE_MENU',
  'SOVEREIGN_WORKSPACE_COMMAND_EVENT',
  'createSovereignWorkspaceCommand',
  'sovereign-wrapper-workspace-menu',
  'composition-wrapper-around-existing-app',
  'MinimalAppShell',
  'MinimalLampBar',
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

describe('Play release rescue app shell contract', () => {
  it('keeps required shell source files present', () => {
    for (const path of [MAIN_PATH, APP_PATH, RELEASE_CHAT_PATH, LOGIN_PATH, WRAPPER_PATH, CSS_PATH]) {
      expect(existsSync(path), `${path} must exist`).toBe(true);
    }
  });

  it('boots the stable React wrapper and Android runtime helpers without global DOM chrome', () => {
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

  it('makes the focused authenticated chat the primary Play surface and excludes the unfinished monitor transport', () => {
    const app = read(APP_PATH);
    const chat = read(RELEASE_CHAT_PATH);

    expectContainsAll(app, [
      "import { PlayReleaseChat } from './features/release/PlayReleaseChat'",
      '<PlayReleaseChat />',
    ]);
    expectContainsNone(app, [
      'BuilderContainer',
      'sovereign-monitor-app',
      'monitor-first-live-workspace',
      'getDesktopFrame',
      'LiveWorkspaceMonitor',
    ]);

    expectContainsAll(chat, [
      'data-testid="sovereign-release-chat"',
      'data-layout="play-release-chat"',
      'aria-label="Sovereign Chat"',
      'fetchSovereignLlmRouteCatalog',
      'fetchDevChatWorkerReply',
      'DEV_CHAT_WORKER_DEFAULT_MODEL',
      "credentials",
      'evaluateInputPolicy',
      '<LoginModal',
    ]);
    expectContainsNone(chat, [
      'getDesktopFrame',
      'desktopFrame',
      'VncScreen',
      'websockify',
    ]);
  });

  it('exposes only email/password auth in the release login modal', () => {
    const login = read(LOGIN_PATH);
    expectContainsAll(login, [
      "type=\"email\"",
      "type=\"password\"",
      'login(email.trim(), password)',
      'register(email.trim(), password, displayName.trim())',
    ]);
    expectContainsNone(login, [
      'GoogleSignInButton',
      'GithubSignInButton',
      'loginWithGoogle',
      'loginWithGitHub',
      'loginWithPasskey',
      'loginWithAccountKey',
      'Passkey',
      'Account-Key',
    ]);
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
