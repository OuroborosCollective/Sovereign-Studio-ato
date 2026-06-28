import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { SOVEREIGN_PRODUCT_TEMPLATE } from './features/product/runtime/sovereignProductTemplate';
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
];

const REQUIRED_CONTAINER_TOKENS = [
  'RemoteMemoryContainer',
  'BuilderContainer',
  'WorkflowContainer',
  'RepoSnapshotContainer',
  'TelemetryContainer',
  'PatternMemoryContainer',
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

  it('boots only the React app wrapper and stable Android runtime helpers', () => {
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
      'SovereignRuntimeShell',
      '<App />',
      'composition-wrapper-around-existing-app',
    ]);

    expectContainsNone(main, DOM_INSTALLER_TOKENS);
  });

  it('keeps the wrapper workspace menu as a contract-backed event bridge, not a second state source', () => {
    const wrapper = read(WRAPPER_PATH);
    const command = read(WORKSPACE_COMMAND_PATH);

    expectContainsAll(wrapper, [
      'WorkspaceMenu',
      'SOVEREIGN_WORKSPACE_MENU',
      'SOVEREIGN_WORKSPACE_COMMAND_EVENT',
      'createSovereignWorkspaceCommand',
      'publishWorkspaceCommand',
      'sovereign-wrapper-workspace-menu',
      'sovereign-wrapper-menu__${item.id}',
      'targetTab',
    ]);

    for (const tab of SOVEREIGN_WORKSPACE_TAB_IDS) {
      expect(command).toContain(`'${tab}'`);
    }

    expect(SOVEREIGN_WORKSPACE_MENU.map((item) => item.id)).toEqual([...SOVEREIGN_WORKSPACE_TAB_IDS]);
    expect(wrapper).toContain('window.dispatchEvent(new CustomEvent(SOVEREIGN_WORKSPACE_COMMAND_EVENT');
    expect(wrapper).not.toContain('querySelector');
    expect(wrapper).not.toContain('localStorage');
    expect(wrapper).not.toContain('sessionStorage');
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

    // App.tsx must import and use the shared event constant to prevent drift
    expect(app).toContain(`SOVEREIGN_WORKSPACE_COMMAND_EVENT`);
    expect(app).toContain(`normalizeSovereignWorkspaceCommandDetail`);
    expect(app).toContain(`window.addEventListener(SOVEREIGN_WORKSPACE_COMMAND_EVENT`);
    expect(app).toContain(`window.removeEventListener(SOVEREIGN_WORKSPACE_COMMAND_EVENT`);
    // Must NOT use hardcoded string to avoid future drift
    expect(app).not.toContain(`'sovereign:release-guide-command'`);
  });

  it('keeps the workspace command contract runtime-only and DOM-free', () => {
    const command = read(WORKSPACE_COMMAND_PATH);

    expectContainsAll(command, [
      'SOVEREIGN_WORKSPACE_COMMAND_EVENT',
      'SOVEREIGN_WORKSPACE_TAB_IDS',
      'SOVEREIGN_WORKSPACE_MENU',
      'isSovereignWorkspaceTab',
      'normalizeSovereignWorkspaceCommandDetail',
    ]);

    expect(command).not.toContain('document.');
    expect(command).not.toContain('window.');
    expect(command).not.toContain('querySelector');
    expect(command).not.toContain('localStorage');
    expect(command).not.toContain('sessionStorage');
  });

  it('keeps the Android recovery fallback JavaScript parse-safe', () => {
    const releaseFix = read('scripts/release-html-runtime-fix.mjs');
    const sourceEscapedNewline = String.raw`npm run build:web\\nnpx cap sync android`;
    const unsafeRuntimeNewline = 'npm run build:web' + '\n' + 'npx cap sync android</pre>';

    expect(releaseFix).toContain(sourceEscapedNewline);
    expect(releaseFix).toContain('[data-testid="app-shell__root"]');
    expect(releaseFix).toContain('.sovereign-login-shell');
    expect(releaseFix).not.toContain(unsafeRuntimeNewline);
  });

  it('keeps product containers owned by App.tsx instead of post-boot DOM scripts', () => {
    const app = read(APP_PATH);

    expectContainsAll(app, REQUIRED_CONTAINER_TOKENS);
    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE.tabs');
    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE.startTab');
    expect(SOVEREIGN_PRODUCT_TEMPLATE.startTab).toBe('builder');
  });

  it('keeps the Android shell mobile-only and landscape safe', () => {
    const css = read(CSS_PATH);
    const main = read(MAIN_PATH);

    expectContainsAll(css, [
      'Android phones, foldables and tablets only',
      '@media (orientation: landscape)',
      'grid-template-columns: 1fr',
    ]);

    expect(css).toMatch(/@media\s*\(orientation:\s*landscape\)/);
    expect(main).toMatch(/clamp\(5\.35rem,\s*12vw,\s*8rem\)/);
    expect(css).not.toContain('min-width: 1440px');
  });

  it('keeps the CSS for the more menu and responsive tabbar', () => {
    const css = read(CSS_PATH);

    expect(css).not.toContain('.sovereign-tabbar,\n[data-role="sovereign-automation-panel"]');
    expect(css).toContain('.sovereign-more-menu');
    expect(css).toContain('.sovereign-more-select');
  });

  it('keeps the global runtime monitor as guidance and only auto-focuses safe UI tabs', () => {
    const monitor = read('src/global-runtime-monitor.tsx');

    expect(monitor).toContain('guarded runtime actions, health gates, workflow steps and PR publishing still require visible user intent');
    expect(monitor).toContain("publishGuideCommand({ type: 'next', targetTab: guide.targetTab })");
    expect(monitor).toContain("publishGuideCommand({ type: 'next', targetTab })");
    expect(monitor).toContain('canAutoAdvanceGuide');
    expect(monitor).toContain('hasBlockingToken');
    expect(monitor).not.toContain('onGenerateIdeas');
    expect(monitor).not.toContain('publishDraftPr');
    expect(monitor).not.toContain('Ich leite den nächsten sicheren Schritt automatisch ein');
  });
});
