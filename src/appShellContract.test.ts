import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { SOVEREIGN_PRODUCT_TEMPLATE } from './features/product/runtime/sovereignProductTemplate';

const MAIN_PATH = 'src/main.tsx';
const APP_PATH = 'src/App.tsx';
const WRAPPER_PATH = 'src/SovereignAppWrapper.tsx';
const CSS_PATH = 'src/index.css';

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

const WORKSPACE_MENU_TABS = [
  'builder',
  'repo',
  'files',
  'diff',
  'workflow',
  'repair',
  'remote',
  'memory',
  'telemetry',
  'monitor',
  'health',
  'runtime',
  'coverage',
  'findings',
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

  it('keeps the wrapper workspace menu as a command bridge, not a second state source', () => {
    const wrapper = read(WRAPPER_PATH);

    expectContainsAll(wrapper, [
      'WorkspaceMenu',
      'WORKSPACE_MENU',
      'publishWorkspaceCommand',
      'sovereign-wrapper-workspace-menu',
      'sovereign-wrapper-menu__${item.id}',
      "targetTab",
    ]);

    for (const tab of WORKSPACE_MENU_TABS) {
      expect(wrapper).toContain(`'${tab}'`);
    }

    expect(wrapper).toContain("window.dispatchEvent(new CustomEvent('sovereign:release-guide-command'");
    expect(wrapper).not.toContain('querySelector');
    expect(wrapper).not.toContain('localStorage');
    expect(wrapper).not.toContain('sessionStorage');
  });

  it('routes release guide commands through primary buttons or the More menu select', () => {
    const main = read(MAIN_PATH);

    expectContainsAll(main, [
      'activateReleaseGuideSelectTarget',
      'select[data-testid="tabbar__more-select"]',
      "select.dispatchEvent(new Event('change'",
      'activateReleaseGuideTarget(button, detail?.type);',
      'activateReleaseGuideSelectTarget(targetTab);',
    ]);
  });

  it('keeps the Android recovery fallback JavaScript parse-safe', () => {
    const releaseFix = read('scripts/release-html-runtime-fix.mjs');
    // File contains: 'npm run build:web\n' (2 backslashes = \n in source)
    // When JS parses this, \n becomes literal newline in HTML output
    // But in file it's stored as \n in HTML source (displayed as actual newline)
    // We check that file contains the escaped form (2 backslashes)
    const escapedNewline = 'npm run build:web' + '\\\\n' + 'npx cap sync android';
    const unsafeCommand = 'npm run build:web' + '\n' + 'npx cap sync android</pre>';

    expect(releaseFix).toContain(escapedNewline);
    expect(releaseFix).toContain('[data-testid="app-shell__root"]');
    expect(releaseFix).toContain('.sovereign-login-shell');
    expect(releaseFix).not.toContain(unsafeCommand);
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
