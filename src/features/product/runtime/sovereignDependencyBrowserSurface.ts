import type { SovereignDependencyCoachSignal } from './sovereignDependencyCoachBridge';

const STYLE_ID = 'sovereign-dependency-surface-style';
const PANEL_ID = 'sovereign-dependency-surface';
const MAX_SIGNALS = 8;
const MAX_TELEMETRY = 25;
const SIGNALS_STORAGE_KEY = 'sovereign-dependency-signals';
const TELEMETRY_STORAGE_KEY = 'sovereign-dependency-telemetry';

type BrowserWindow = Window & typeof globalThis & {
  __sovereignDependencySignals?: SovereignDependencyCoachSignal[];
  __sovereignDependencyTelemetry?: Array<Record<string, unknown>>;
  __sovereignDependencySurfaceInstalled?: boolean;
};

function canUseDom(): boolean {
  return typeof window !== 'undefined' && typeof document !== 'undefined';
}

function asBrowserWindow(): BrowserWindow | null {
  return canUseDom() ? window as BrowserWindow : null;
}

function readSessionJson(key: string): unknown {
  if (!canUseDom()) return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeSessionJson(key: string, value: unknown): void {
  if (!canUseDom()) return;
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage is best-effort only. The window snapshot still remains active.
  }
}

function isSignal(value: unknown): value is SovereignDependencyCoachSignal {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<SovereignDependencyCoachSignal>;
  return (
    (item.lamp === 'green' || item.lamp === 'yellow' || item.lamp === 'red') &&
    typeof item.title === 'string' &&
    typeof item.message === 'string' &&
    typeof item.action === 'string' &&
    typeof item.source === 'string' &&
    typeof item.dependencyKey === 'string' &&
    typeof item.dependencyPhase === 'string' &&
    typeof item.telemetryLevel === 'string' &&
    typeof item.telemetryLabel === 'string' &&
    typeof item.telemetryMessage === 'string'
  );
}

function normalizeSignals(value: unknown): SovereignDependencyCoachSignal[] {
  return Array.isArray(value) ? value.filter(isSignal).slice(0, MAX_SIGNALS) : [];
}

function installStyle(): void {
  if (!canUseDom()) return;
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    #${PANEL_ID} {
      margin-top: 1rem;
      border: 1px solid rgba(148, 163, 184, 0.28);
      border-radius: 0.75rem;
      padding: 0.75rem;
      background: rgba(15, 23, 42, 0.72);
      color: rgb(226, 232, 240);
      font-size: 12px;
    }
    #${PANEL_ID} .dependency-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 0.5rem;
      margin-top: 0.5rem;
    }
    #${PANEL_ID} .dependency-card {
      border: 1px solid rgba(71, 85, 105, 0.8);
      border-radius: 0.5rem;
      padding: 0.5rem;
      background: rgba(30, 41, 59, 0.72);
    }
    #${PANEL_ID} .dependency-card strong {
      display: block;
      color: white;
      margin-bottom: 0.25rem;
    }
  `;
  document.head.appendChild(style);
}

export function readSovereignDependencySignals(): SovereignDependencyCoachSignal[] {
  const win = asBrowserWindow();
  if (!win) return [];

  const memorySignals = normalizeSignals(win.__sovereignDependencySignals);
  if (memorySignals.length > 0) return memorySignals;

  const storedSignals = normalizeSignals(readSessionJson(SIGNALS_STORAGE_KEY));
  win.__sovereignDependencySignals = storedSignals;
  return storedSignals;
}

export function writeSovereignDependencySignals(next: SovereignDependencyCoachSignal[]): SovereignDependencyCoachSignal[] {
  const win = asBrowserWindow();
  const safeSignals = normalizeSignals(next);
  if (!win) return safeSignals;

  win.__sovereignDependencySignals = safeSignals;
  writeSessionJson(SIGNALS_STORAGE_KEY, safeSignals);
  return safeSignals;
}

export function upsertSovereignDependencySignal(signal: SovereignDependencyCoachSignal): SovereignDependencyCoachSignal[] {
  const previous = readSovereignDependencySignals().filter((item) => item.dependencyKey !== signal.dependencyKey);
  return writeSovereignDependencySignals([signal, ...previous].slice(0, MAX_SIGNALS));
}

function levelSymbol(signal: SovereignDependencyCoachSignal): string {
  if (signal.lamp === 'red') return 'rot';
  if (signal.lamp === 'yellow') return 'gelb';
  return 'gruen';
}

function ensurePanel(): HTMLElement | null {
  if (!canUseDom()) return null;

  let panel = document.getElementById(PANEL_ID);
  if (panel) return panel;

  const monitor = document.querySelector('[data-testid="operator-monitor"]');
  if (!monitor) return null;

  panel = document.createElement('section');
  panel.id = PANEL_ID;
  panel.setAttribute('aria-label', 'Dependency Status');
  monitor.appendChild(panel);
  return panel;
}

function appendText(parent: HTMLElement, tagName: keyof HTMLElementTagNameMap, text: string, className?: string): HTMLElement {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = text;
  parent.appendChild(element);
  return element;
}

export function renderSovereignDependencySignals(signals: SovereignDependencyCoachSignal[]): void {
  installStyle();
  const panel = ensurePanel();
  if (!panel) return;

  panel.replaceChildren();
  appendText(panel, 'h3', 'Dependency Status');
  const grid = document.createElement('div');
  grid.className = 'dependency-grid';
  panel.appendChild(grid);

  if (signals.length === 0) {
    appendText(grid, 'p', 'No dependency signals yet.');
    return;
  }

  for (const signal of signals) {
    const card = document.createElement('article');
    card.className = 'dependency-card';
    card.setAttribute('data-dependency-key', signal.dependencyKey);
    appendText(card, 'strong', `${signal.source} / ${signal.dependencyPhase}`);
    appendText(card, 'span', `${levelSymbol(signal)} · ${signal.title}`);
    appendText(card, 'p', signal.message);
    grid.appendChild(card);
  }
}

export function recordSovereignDependencyTelemetry(detail: unknown): Array<Record<string, unknown>> {
  const win = asBrowserWindow();
  const previous = Array.isArray(win?.__sovereignDependencyTelemetry)
    ? win.__sovereignDependencyTelemetry
    : Array.isArray(readSessionJson(TELEMETRY_STORAGE_KEY))
      ? readSessionJson(TELEMETRY_STORAGE_KEY) as Array<Record<string, unknown>>
      : [];
  const next = [detail as Record<string, unknown>, ...previous].slice(0, MAX_TELEMETRY);

  if (win) win.__sovereignDependencyTelemetry = next;
  writeSessionJson(TELEMETRY_STORAGE_KEY, next);
  return next;
}

export function installSovereignDependencyBrowserSurface(): void {
  const win = asBrowserWindow();
  if (!win) return;
  if (win.__sovereignDependencySurfaceInstalled) return;
  win.__sovereignDependencySurfaceInstalled = true;

  window.addEventListener('sovereign:dependency-lifecycle-state', (event) => {
    const detail = (event as CustomEvent<SovereignDependencyCoachSignal>).detail;
    if (!isSignal(detail)) return;
    renderSovereignDependencySignals(upsertSovereignDependencySignal(detail));
  });

  window.addEventListener('sovereign:dependency-telemetry-event', (event) => {
    recordSovereignDependencyTelemetry((event as CustomEvent).detail);
  });

  window.setTimeout(() => renderSovereignDependencySignals(readSovereignDependencySignals()), 0);
}

export function resetSovereignDependencyBrowserSurfaceForTests(): void {
  const win = asBrowserWindow();
  if (!win) return;
  delete win.__sovereignDependencySignals;
  delete win.__sovereignDependencyTelemetry;
  delete win.__sovereignDependencySurfaceInstalled;
  try {
    window.sessionStorage.removeItem(SIGNALS_STORAGE_KEY);
    window.sessionStorage.removeItem(TELEMETRY_STORAGE_KEY);
  } catch {
    // Storage cleanup is best-effort in non-browser test environments.
  }
  document.getElementById(PANEL_ID)?.remove();
  document.getElementById(STYLE_ID)?.remove();
}
