import type { SovereignDependencyCoachSignal } from './sovereignDependencyCoachBridge';

const STYLE_ID = 'sovereign-dependency-surface-style';
const PANEL_ID = 'sovereign-dependency-surface';
const MAX_SIGNALS = 8;

type BrowserWindow = Window & typeof globalThis & {
  __sovereignDependencySignals?: SovereignDependencyCoachSignal[];
  __sovereignDependencyTelemetry?: Array<Record<string, unknown>>;
};

function canUseDom(): boolean {
  return typeof window !== 'undefined' && typeof document !== 'undefined';
}

function asBrowserWindow(): BrowserWindow | null {
  return canUseDom() ? window as BrowserWindow : null;
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

function readSignals(): SovereignDependencyCoachSignal[] {
  const win = asBrowserWindow();
  return Array.isArray(win?.__sovereignDependencySignals) ? win.__sovereignDependencySignals : [];
}

function writeSignals(next: SovereignDependencyCoachSignal[]): void {
  const win = asBrowserWindow();
  if (!win) return;
  win.__sovereignDependencySignals = next.slice(0, MAX_SIGNALS);
}

function upsertSignal(signal: SovereignDependencyCoachSignal): SovereignDependencyCoachSignal[] {
  const previous = readSignals().filter((item) => item.dependencyKey !== signal.dependencyKey);
  const next = [signal, ...previous].slice(0, MAX_SIGNALS);
  writeSignals(next);
  return next;
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

function renderSignals(signals: SovereignDependencyCoachSignal[]): void {
  installStyle();
  const panel = ensurePanel();
  if (!panel) return;

  const cards = signals.map((signal) => `
    <article class="dependency-card" data-dependency-key="${signal.dependencyKey}">
      <strong>${signal.source} / ${signal.dependencyPhase}</strong>
      <span>${levelSymbol(signal)} · ${signal.title}</span>
      <p>${signal.message}</p>
    </article>
  `).join('');

  panel.innerHTML = `
    <h3>Dependency Status</h3>
    <div class="dependency-grid">${cards || '<p>No dependency signals yet.</p>'}</div>
  `;
}

function recordTelemetry(detail: unknown): void {
  const win = asBrowserWindow();
  if (!win) return;
  const previous = Array.isArray(win.__sovereignDependencyTelemetry) ? win.__sovereignDependencyTelemetry : [];
  win.__sovereignDependencyTelemetry = [detail as Record<string, unknown>, ...previous].slice(0, 25);
}

export function installSovereignDependencyBrowserSurface(): void {
  if (!canUseDom()) return;

  window.addEventListener('sovereign:dependency-lifecycle-state', (event) => {
    const detail = (event as CustomEvent<SovereignDependencyCoachSignal>).detail;
    if (!detail?.dependencyKey) return;
    renderSignals(upsertSignal(detail));
  });

  window.addEventListener('sovereign:dependency-telemetry-event', (event) => {
    recordTelemetry((event as CustomEvent).detail);
  });

  window.setTimeout(() => renderSignals(readSignals()), 0);
}
