import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

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

const REQUIRED_PRIMARY_TABS = [
  "{ id: 'repo', label: 'Repo' }",
  "{ id: 'builder', label: 'Builder' }",
  "{ id: 'files', label: 'Files' }",
  "{ id: 'diff', label: 'Diff' }",
  "{ id: 'workflow', label: 'Workflow' }",
  "{ id: 'repair', label: 'Repair' }",
  "{ id: 'remote', label: 'Remote Memory' }",
  "{ id: 'memory', label: 'Pattern Memory' }",
  "{ id: 'telemetry', label: 'Telemetry' }",
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

  it('starts in the repo workflow instead of monitor-first or side-channel-first mode', () => {
    const app = read(APP_PATH);

    expect(app).toContain("useState<SovereignTab>('repo')");

    expectContainsNone(app, [
      "useState<SovereignTab>('monitor')",
      "useState<SovereignTab>('telemetry')",
      "useState<SovereignTab>('workflow')",
      "useState<SovereignTab>('remote')",
      "useState<SovereignTab>('memory')",
    ]);
  });

  it('keeps the primary operator tabs present and named consistently', () => {
    const app = read(APP_PATH);

    expectContainsAll(app, REQUIRED_PRIMARY_TABS);
  });

  it('keeps repo and builder before side-channel memory surfaces', () => {
    const app = read(APP_PATH);

    expectOrder(app, [
      "{ id: 'repo', label: 'Repo' }",
      "{ id: 'builder', label: 'Builder' }",
      "{ id: 'remote', label: 'Remote Memory' }",
      "{ id: 'memory', label: 'Pattern Memory' }",
    ]);
  });

  it('keeps files and diff before workflow execution surfaces', () => {
    const app = read(APP_PATH);

    expectOrder(app, [
      "{ id: 'repo', label: 'Repo' }",
      "{ id: 'builder', label: 'Builder' }",
      "{ id: 'files', label: 'Files' }",
      "{ id: 'diff', label: 'Diff' }",
      "{ id: 'workflow', label: 'Workflow' }",
    ]);
  });

  it('keeps telemetry as a side-channel tab instead of a startup gate', () => {
    const app = read(APP_PATH);

    expect(app).toContain("{ id: 'telemetry', label: 'Telemetry' }");
    expect(app).not.toContain("useState<SovereignTab>('telemetry')");
    expect(app).not.toContain('telemetryGate');
    expect(app).not.toContain('TelemetryGate');
  });

  it('keeps repo snapshot surface reachable for real repo handoff', () => {
    const app = read(APP_PATH);

    expect(app).toContain('RepoSnapshotContainer');
    expect(app).toContain("{ id: 'repo', label: 'Repo' }");
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
