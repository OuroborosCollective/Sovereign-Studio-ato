import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  SOVEREIGN_WORKSPACE_COMMAND_EVENT,
  SOVEREIGN_WORKSPACE_MENU,
  SOVEREIGN_WORKSPACE_TAB_IDS,
} from './features/product/runtime/sovereignWorkspaceCommand';

const MAIN_PATH = 'src/main.tsx';
const APP_PATH = 'src/App.tsx';
const WRAPPER_PATH = 'src/SovereignAppWrapper.tsx';
const CSS_PATH = 'src/index.css';
const WORKSPACE_COMMAND_PATH = 'src/features/product/runtime/sovereignWorkspaceCommand.ts';

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
  for (const token of tokens) {
    expect(source, `expected source to contain: ${token}`).toContain(token);
  }
}

function expectContainsNone(source: string, tokens: string[]): void {
  for (const token of tokens) {
    expect(source, `expected source not to contain: ${token}`).not.toContain(token);
  }
}

describe('current Sovereign app shell contract', () => {
  it('keeps required shell source files present', () => {
    expect(existsSync(MAIN_PATH)).toBe(true);
    expect(existsSync(APP_PATH)).toBe(true);
    expect(existsSync(WRAPPER_PATH)).toBe(true);
    expect(existsSync(CSS_PATH)).toBe(true);
    expect(existsSync(WORKSPACE_COMMAND_PATH)).toBe(true);
  });

  it('boots the React app wrapper and stable Android runtime helpers without a global coach', () => {
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

    expectContainsAll(wrapper, [
      "import App from './App'",
      '<App />',
      'export default function SovereignAppWrapper',
    ]);

    expectContainsNone(wrapper, REMOVED_WRAPPER_NAV_TOKENS);
    expectContainsNone(main, DOM_INSTALLER_TOKENS);
  });

  it('keeps the wrapper free of visible chrome and navigation state', () => {
    const wrapper = read(WRAPPER_PATH);

    expectContainsAll(wrapper, [
      "import App from './App'",
      'return <App />',
    ]);

    expectContainsNone(wrapper, REMOVED_WRAPPER_NAV_TOKENS);
    expect(wrapper).not.toContain('querySelector');
    expect(wrapper).not.toContain('localStorage');
    expect(wrapper).not.toContain('sessionStorage');
  });

  it('keeps workspace command definitions available without making the wrapper a navigation source', () => {
    const command = read(WORKSPACE_COMMAND_PATH);
    const wrapper = read(WRAPPER_PATH);

    for (const tab of SOVEREIGN_WORKSPACE_TAB_IDS) {
      expect(command).toContain(`'${tab}'`);
    }

    expect(SOVEREIGN_WORKSPACE_MENU.map((item) => item.id)).toEqual([...SOVEREIGN_WORKSPACE_TAB_IDS]);
    expect(command).toContain(SOVEREIGN_WORKSPACE_COMMAND_EVENT);
    expect(wrapper).not.toContain(SOVEREIGN_WORKSPACE_COMMAND_EVENT);
    expect(wrapper).not.toContain('SOVEREIGN_WORKSPACE_MENU');
  });

  it('routes release guide commands through validated workspace commands and the More menu select', () => {
    const main = read(MAIN_PATH);

    expectContainsAll(main, [
      'SOVEREIGN_WORKSPACE_COMMAND_EVENT',
      'normalizeSovereignWorkspaceCommandDetail',
      'isSovereignWorkspaceTab',
      'activateReleaseGuideSelectTarget',
      'select[data-testid="tabbar__more-select"]',
      "select.dispatchEvent(new Event('change'",
      'activateReleaseGuideTarget(button, detail.type);',
      'activateReleaseGuideSelectTarget(targetTab);',
    ]);
  });

  it('keeps App guide command listener aligned with the workspace event contract', () => {
    const app = read(APP_PATH);

    expect(app).toContain('SOVEREIGN_WORKSPACE_COMMAND_EVENT');
    expect(app).toContain('normalizeSovereignWorkspaceCommandDetail');
    expect(app).toContain('window.addEventListener(SOVEREIGN_WORKSPACE_COMMAND_EVENT');
    expect(app).toContain('window.removeEventListener(SOVEREIGN_WORKSPACE_COMMAND_EVENT');
  });
});
