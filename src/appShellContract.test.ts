import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { SOVEREIGN_PRODUCT_TEMPLATE } from './features/product/runtime/sovereignProductTemplate';

const MAIN_PATH = 'src/main.tsx';
const APP_PATH = 'src/App.tsx';
const CSS_PATH = 'src/index.css';

const FORBIDDEN_LEGACY_SHELL_TOKENS = [
  'ProductMagicApp',
  'ProductMagic',
  'MonitorApp',
  'OperatorMonitorApp',
  'LegacyProductShell',
  'MockProductMagic',
  'FakeSnapshot',
  'fake snapshot',
  'desktop-like',
  'desktopShell',
];

const REQUIRED_CONTAINER_TOKENS = [
  'RemoteMemoryContainer',
  'BuilderContainer',
  'WorkflowContainer',
  'RepoSnapshotContainer',
  'TelemetryContainer',
  'PatternMemoryContainer',
];

const REQUIRED_MOBILE_INSTALLERS = [
  'installMobileOperatorCoach',
  'installMobileMoreMenu',
  'installMobileSetupDrawer',
  'installMobileWorkbenchConsole',
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

function expectOrder(source: string, tokens: string[]): void {
  let previousIndex = -1;

  for (const token of tokens) {
    const index = source.indexOf(token);

    expect(index, `expected token to exist: ${token}`).toBeGreaterThanOrEqual(0);
    expect(index, `expected token to appear after previous token: ${token}`).toBeGreaterThan(
      previousIndex,
    );

    previousIndex = index;
  }
}

function expectRegex(source: string, pattern: RegExp, label: string): void {
  expect(source, `expected source to match ${label}`).toMatch(pattern);
}

describe('current Sovereign app shell contract', () => {
  it('keeps required shell source files present', () => {
    expect(existsSync(MAIN_PATH)).toBe(true);
    expect(existsSync(APP_PATH)).toBe(true);
    expect(existsSync(CSS_PATH)).toBe(true);
  });

  it('renders the real container App instead of legacy or removed shells', () => {
    const main = read(MAIN_PATH);

    expect(main).toContain("import App from './App'");
    expect(main).toContain('<App />');

    expectContainsNone(main, FORBIDDEN_LEGACY_SHELL_TOKENS);
  });

  it('keeps the React root guarded by the real app boundary', () => {
    const main = read(MAIN_PATH);

    expectContainsAll(main, [
      'createRoot',
      "document.getElementById('root')",
      'ErrorBoundary',
      '<ErrorBoundary>',
      '<App />',
    ]);

    expectOrder(main, ['<ErrorBoundary>', '<App />']);
  });

  it('keeps runtime adapter and index stylesheet wired into main.tsx', () => {
    const main = read(MAIN_PATH);

    expectContainsAll(main, ["import './runtime-adapter'", "import './index.css'"]);
  });

  it('keeps mobile runtime installers imported and executed from main.tsx', () => {
    const main = read(MAIN_PATH);

    expectContainsAll(main, REQUIRED_MOBILE_INSTALLERS);

    for (const installer of REQUIRED_MOBILE_INSTALLERS) {
      expectRegex(main, new RegExp(`${installer}\\s*\\(`), `${installer} invocation`);
    }
  });

  it('keeps the core container imports reachable from App.tsx', () => {
    const app = read(APP_PATH);

    expectContainsAll(app, REQUIRED_CONTAINER_TOKENS);
    expectContainsNone(app, FORBIDDEN_LEGACY_SHELL_TOKENS);
  });

  it('starts in the repo workflow via Product Template instead of monitor-first or side-channel-first mode', () => {
    const app = read(APP_PATH);

    // App should derive startTab from the Product Template
    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE.startTab');
    // startTab must be 'repo'
    expect(SOVEREIGN_PRODUCT_TEMPLATE.startTab).toBe('repo');

    expectContainsNone(app, [
      "useState<SovereignTab>('monitor')",
      "useState<SovereignTab>('telemetry')",
      "useState<SovereignTab>('workflow')",
      "useState<SovereignTab>('remote')",
      "useState<SovereignTab>('memory')",
    ]);
  });

  it('derives tabs from Product Template as single source of truth', () => {
    const app = read(APP_PATH);

    // App should use Product Template to derive tabs
    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE.tabs');
    // All primary flow tab IDs should be referenced
    const primaryTabs = SOVEREIGN_PRODUCT_TEMPLATE.tabs.filter((t) => t.group === 'primary');
    for (const tab of primaryTabs) {
      expect(app).toContain(`'${tab.id}'`);
    }
  });

  it('keeps repo and builder before side-channel memory surfaces in Product Template', () => {
    const app = read(APP_PATH);

    // Verify the template structure
    const repoTab = SOVEREIGN_PRODUCT_TEMPLATE.tabs.find((t) => t.id === 'repo');
    const builderTab = SOVEREIGN_PRODUCT_TEMPLATE.tabs.find((t) => t.id === 'builder');
    const remoteTab = SOVEREIGN_PRODUCT_TEMPLATE.tabs.find((t) => t.id === 'remote');
    const memoryTab = SOVEREIGN_PRODUCT_TEMPLATE.tabs.find((t) => t.id === 'memory');

    expect(repoTab?.mainFlowIndex).toBeLessThan(builderTab?.mainFlowIndex ?? 999);
    expect(builderTab?.mainFlowIndex).toBeLessThan(remoteTab?.mainFlowIndex ?? 999);
    expect(builderTab?.mainFlowIndex).toBeLessThan(memoryTab?.mainFlowIndex ?? 999);

    // Verify app uses template
    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE');
  });

  it('keeps files and diff before workflow execution surfaces in Product Template', () => {
    const app = read(APP_PATH);

    const filesTab = SOVEREIGN_PRODUCT_TEMPLATE.tabs.find((t) => t.id === 'files');
    const diffTab = SOVEREIGN_PRODUCT_TEMPLATE.tabs.find((t) => t.id === 'diff');
    const workflowTab = SOVEREIGN_PRODUCT_TEMPLATE.tabs.find((t) => t.id === 'workflow');

    expect(filesTab?.mainFlowIndex).toBeLessThan(diffTab?.mainFlowIndex ?? 999);
    expect(diffTab?.mainFlowIndex).toBeLessThan(workflowTab?.mainFlowIndex ?? 999);

    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE');
  });

  it('keeps telemetry as a side-channel tab via Product Template instead of a startup gate', () => {
    const app = read(APP_PATH);

    const telemetryTab = SOVEREIGN_PRODUCT_TEMPLATE.tabs.find((t) => t.id === 'telemetry');
    expect(telemetryTab?.group).toBe('side');
    expect(telemetryTab?.label).toBe('Telemetry');

    // App should derive tabs from template
    expect(app).toContain('SOVEREIGN_PRODUCT_TEMPLATE.tabs');
    expect(app).not.toContain('telemetryGate');
    expect(app).not.toContain('TelemetryGate');
  });

  it('keeps repo snapshot surface reachable for real repo handoff', () => {
    const app = read(APP_PATH);

    expect(app).toContain('RepoSnapshotContainer');
    expect(app).not.toContain('FakeSnapshot');
    expect(app).not.toContain('mockSnapshot');
    expect(app).not.toContain('MockSnapshot');
  });

  it('keeps the Android shell mobile-only and landscape safe', () => {
    const css = read(CSS_PATH);
    const main = read(MAIN_PATH);

    expectContainsAll(css, [
      'Android phones, foldables and tablets only',
      '@media (orientation: landscape)',
      'grid-template-columns: 1fr',
    ]);

    expectRegex(css, /@media\s*\(orientation:\s*landscape\)/, 'landscape media query');
    expectRegex(main, /clamp\(5\.35rem,\s*12vw,\s*8rem\)/, 'mobile safe clamp');

    expectContainsNone(css, ['desktop-like', 'desktop shell', 'desktopShell']);
  });

  it('does not reintroduce desktop-first shell breakpoints', () => {
    const css = read(CSS_PATH);

    expect(css).not.toMatch(
      /@media\s*\(\s*min-width:\s*1024px\s*\)[^{]*{[^}]*grid-template-columns:\s*repeat/i,
    );

    expect(css).not.toMatch(
      /@media\s*\(\s*min-width:\s*1280px\s*\)[^{]*{[^}]*grid-template-columns:\s*repeat/i,
    );

    expect(css).not.toContain('min-width: 1440px');
  });

  it('keeps app-shell CSS single-column safe for constrained Android viewports', () => {
    const css = read(CSS_PATH);

    expect(css).toContain('grid-template-columns: 1fr');
    expect(css).not.toMatch(/grid-template-columns:\s*[^;]*\b2fr\b/i);
    expect(css).not.toMatch(/grid-template-columns:\s*[^;]*\b3fr\b/i);
  });

  it('keeps source contract free from legacy shell tokens across main app and css', () => {
    const combined = [read(MAIN_PATH), read(APP_PATH), read(CSS_PATH)].join('\n');

    expectContainsNone(combined, FORBIDDEN_LEGACY_SHELL_TOKENS);
  });

  it('keeps runtime handoff wording reachable without fake truth-path language', () => {
    const app = read(APP_PATH);

    expectContainsAll(app, ['Sovereign', 'Repo', 'Builder']);

    expectContainsNone(app, [
      'fake snapshot',
      'FakeSnapshot',
      'mockSnapshot',
      'MockSnapshot',
      'plan-only truth',
      'planOnlyTruth',
    ]);
  });
});
