import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { SOVEREIGN_PRODUCT_TEMPLATE } from './features/product/runtime/sovereignProductTemplate';

const MAIN_PATH = 'src/main.tsx';
const APP_PATH = 'src/App.tsx';
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
    expect(existsSync(CSS_PATH)).toBe(true);
  });

  it('boots only the React app and stable Android runtime helpers', () => {
    const main = read(MAIN_PATH);

    expectContainsAll(main, [
      "import App from './App'",
      '<ErrorBoundary>',
      '<App />',
      "import './runtime-adapter'",
      "import './index.css'",
      'installIdleCallbackFallback();',
      'installViewportRuntime();',
      'installCodeWorkspacePersistenceRuntime();',
      'bootApp();',
    ]);

    expectContainsNone(main, DOM_INSTALLER_TOKENS);
  });

  it('keeps the Android recovery fallback JavaScript parse-safe', () => {
    const releaseFix = read('scripts/release-html-runtime-fix.mjs');
    const parseSafeCommand = String.raw`npm run build:web\\nnpx cap sync android`;
    const unsafeCommand = 'npm run build:web' + '\n' + 'npx cap sync android</pre>';

    expect(releaseFix).toContain(parseSafeCommand);
    expect(releaseFix).toContain('[data-testid="app-shell__root"]');
    expect(releaseFix).toContain('.sovereign-login-shell');
    expect(releaseFix).not.toContain(unsafeCommand);
  });

  it('keeps product containers owned by App.tsx instead of post-boot DOM scripts', () => {
    const app = read(APP_PATH);

    expectContainsAll(app, REQUIRED_CONTAINER_TOKENS);
    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE.tabs');
    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE.startTab');
    expect(SOVEREIGN_PRODUCT_TEMPLATE.startTab).toBe('repo');
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


  it('keeps the global runtime monitor as guidance instead of auto-clicking tabs', () => {
    const monitor = read('src/global-runtime-monitor.tsx');

    expect(monitor).toContain('users trigger navigation explicitly via the visible guide buttons');
    expect(monitor).toContain("publishGuideCommand({ type: 'next', targetTab: guide.targetTab })");
    expect(monitor).not.toContain('setTimeout(() => publishGuideCommand');
    expect(monitor).not.toContain('lastAutoCommandKeyRef');
    expect(monitor).not.toContain('Ich leite den nächsten sicheren Schritt automatisch ein');
  });

});
