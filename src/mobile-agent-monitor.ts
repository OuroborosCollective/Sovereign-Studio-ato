import { assertMobileWorkflowDecisionValid, decideMobileWorkflow } from './mobile-workflow-orchestrator';

export type MobileAgentLamp = 'green' | 'yellow' | 'red';

export interface MobileAgentCoachState {
  lamp: MobileAgentLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
  source?: string;
  updatedAt?: number;
}

interface SetupStateLike {
  hasToken?: boolean;
  tokenStatus?: string;
  repoReady?: boolean;
  setupPhase?: string;
  isBusy?: boolean;
  status?: string;
  dependencyHealthy?: boolean;
  updatedAt?: number;
}

interface MobileAgentLogEntry {
  id: string;
  ts: number;
  lamp: MobileAgentLamp;
  source: string;
  text: string;
}

type AnyRecord = Record<string, unknown>;

type MobileAgentWindow = Window & typeof globalThis & {
  __sovereignMobileAgentMonitorInstalled?: boolean;
  __sovereignMobileAgentMonitorInterval?: number;
  __sovereignCoachState?: unknown;
  __sovereignMobileCoachState?: unknown;
  __sovereignRuntimeCoachState?: unknown;
  __sovereignSetupState?: SetupStateLike;
};

const ROOT_ID = 'sovereign-mobile-coach';
const STYLE_ID = 'sovereign-mobile-agent-monitor-style';
const SETUP_ID = 'sovereign-mobile-setup-drawer';
const STORAGE_KEY = 'sovereign-mobile-agent-monitor-log';
const MAX_LOG_ENTRIES = 80;
const RENDER_INTERVAL_MS = 1000;
const INITIAL_DELAY_MS = 650;
const TEXT_NODE = 4;
const ACCEPT = 1;
const REJECT = 2;

const ACTIONS = ['Repo', 'Builder', 'Files', 'Diff', 'Workflow', 'Repair'] as const;
const FACES = ['^-_-^', '｡◕‿◕｡', '○¤○', '[>->_]', '_@=@_'];

let entries: MobileAgentLogEntry[] = [];
let lastSignature = '';

function now(): number {
  return Date.now();
}

function record(value: unknown): value is AnyRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function bool(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') return value;
  if (typeof value !== 'string') return undefined;
  const normalized = value.trim().toLowerCase();
  if (['1', 'true', 'yes', 'on', 'running', 'busy', 'active'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off', 'idle', 'ready', 'done'].includes(normalized)) return false;
  return undefined;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function hash(value: string): number {
  let next = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    next ^= value.charCodeAt(index);
    next = Math.imul(next, 16777619);
  }
  return next >>> 0;
}

function face(seed: string): string {
  return FACES[hash(seed) % FACES.length];
}

function ignoredSelector(): string {
  return `#${ROOT_ID}, #${STYLE_ID}, #${SETUP_ID}, script, style, noscript`;
}

function closestElement(node: Node): Element | null {
  return node instanceof Element ? node : node.parentElement;
}

function shouldReadTextNode(node: Node): number {
  const element = closestElement(node);
  if (!element) return REJECT;
  return element.closest(ignoredSelector()) ? REJECT : ACCEPT;
}

export function collectMobileAgentVisibleText(root?: ParentNode | null): string {
  if (typeof document === 'undefined') return '';
  const safeRoot = root ?? document.body;
  if (!safeRoot) return '';

  const parts: string[] = [];
  const walker = document.createTreeWalker(safeRoot, TEXT_NODE, { acceptNode: shouldReadTextNode });
  let node = walker.nextNode();

  while (node) {
    const value = node.nodeValue?.trim();
    if (value) parts.push(value);
    node = walker.nextNode();
  }

  return parts.join('\n');
}

function normalizeCoachState(value: unknown): MobileAgentCoachState | null {
  if (!record(value)) return null;
  const lamp = value.lamp === 'green' || value.lamp === 'yellow' || value.lamp === 'red' ? value.lamp : null;
  const title = text(value.title);
  const message = text(value.message);
  const action = text(value.action);
  if (!lamp || !title || !message || !action) return null;

  return {
    lamp,
    title,
    message,
    action,
    thinking: bool(value.thinking) ?? false,
    source: text(value.source) || 'runtime',
    updatedAt: typeof value.updatedAt === 'number' ? value.updatedAt : now(),
  };
}

function setupCoachState(setup: SetupStateLike | undefined): MobileAgentCoachState | null {
  if (!setup) return null;
  if (setup.isBusy || setup.setupPhase === 'repo-loading') {
    return {
      lamp: 'green',
      title: 'Repository wird geladen',
      message: setup.status || 'Repo Snapshot wird aus GitHub geladen.',
      action: 'Bitte warten.',
      thinking: true,
      source: 'setup',
      updatedAt: setup.updatedAt ?? now(),
    };
  }

  if (setup.setupPhase === 'repo-error' || setup.dependencyHealthy === false) {
    return {
      lamp: 'red',
      title: 'Repo Setup braucht Aufmerksamkeit',
      message: setup.status || 'GitHub Repo oder Zugriff ist noch nicht gueltig.',
      action: 'Repo/PAT pruefen und erneut laden.',
      thinking: false,
      source: 'setup',
      updatedAt: setup.updatedAt ?? now(),
    };
  }

  if (setup.repoReady) {
    return {
      lamp: 'green',
      title: 'Repository geladen',
      message: setup.status || 'Repo Snapshot ist bereit.',
      action: 'Auftrag eingeben oder Package bauen.',
      thinking: false,
      source: 'setup',
      updatedAt: setup.updatedAt ?? now(),
    };
  }

  return {
    lamp: 'yellow',
    title: 'Repo Setup bereit',
    message: setup.hasToken ? 'Privater Zugriff ist gesetzt. Repo laden.' : 'Repo URL und PAT eintragen.',
    action: 'Repo laden.',
    thinking: false,
    source: 'setup',
    updatedAt: setup.updatedAt ?? now(),
  };
}

function workflowCoachState(): MobileAgentCoachState {
  try {
    const decision = decideMobileWorkflow({ visibleText: collectMobileAgentVisibleText() });
    assertMobileWorkflowDecisionValid(decision);
    return {
      lamp: decision.lamp,
      title: decision.title,
      message: decision.summary,
      action: decision.targetNav ? `${decision.targetNav} pruefen.` : 'Naechsten Schritt waehlen.',
      thinking: decision.mode === 'matrix-work',
      source: decision.mode,
      updatedAt: now(),
    };
  } catch {
    return {
      lamp: 'yellow',
      title: 'Agent Monitor wartet',
      message: 'Noch kein stabiler Runtime-Zustand erkannt.',
      action: 'Repo oder Auftrag pruefen.',
      thinking: false,
      source: 'monitor',
      updatedAt: now(),
    };
  }
}

function currentCoachState(): MobileAgentCoachState {
  const win = window as MobileAgentWindow;
  return normalizeCoachState(win.__sovereignRuntimeCoachState)
    ?? normalizeCoachState(win.__sovereignCoachState)
    ?? normalizeCoachState(win.__sovereignMobileCoachState)
    ?? setupCoachState(win.__sovereignSetupState)
    ?? workflowCoachState();
}

function loadEntries(): MobileAgentLogEntry[] {
  if (entries.length) return entries;
  try {
    const parsed = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || '[]');
    if (!Array.isArray(parsed)) return [];
    entries = parsed
      .filter((item): item is MobileAgentLogEntry => record(item) && typeof item.id === 'string' && typeof item.ts === 'number' && typeof item.text === 'string')
      .slice(-MAX_LOG_ENTRIES);
    return entries;
  } catch {
    return [];
  }
}

function saveEntries(): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(-MAX_LOG_ENTRIES)));
  } catch {
    // Optional monitor persistence must never break the app.
  }
}

function appendEntry(state: MobileAgentCoachState): void {
  const signature = `${state.lamp}|${state.source ?? 'agent'}|${state.title}|${state.message}|${state.action}|${state.thinking}`;
  if (signature === lastSignature) return;
  lastSignature = signature;

  entries = [
    ...loadEntries(),
    {
      id: `${state.updatedAt ?? now()}-${hash(signature)}`,
      ts: state.updatedAt ?? now(),
      lamp: state.lamp,
      source: state.source ?? 'agent',
      text: `${state.title}: ${state.message}`,
    },
  ].slice(-MAX_LOG_ENTRIES);
  saveEntries();
}

function findActionButton(label: string): HTMLButtonElement | null {
  const wanted = label.toLowerCase();
  return Array.from(document.querySelectorAll('button')).find((button) => {
    if (button.closest(ignoredSelector())) return false;
    return (button.textContent ?? '').trim().toLowerCase() === wanted;
  }) ?? null;
}

function triggerAction(label: string): void {
  const button = findActionButton(label);
  if (!button) return;
  button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

function anchorShell(): Element | null {
  return document.querySelector('#root > div.min-h-screen > div:nth-of-type(1)') ?? document.getElementById('root');
}

function installStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    #${ROOT_ID} { margin:.78rem 0; border:1px solid rgba(34,211,238,.28); border-radius:1.15rem; background:rgba(2,6,23,.94); color:#e2e8f0; overflow:hidden; box-shadow:0 18px 48px rgba(0,0,0,.28); }
    #${ROOT_ID} .agent-head { display:flex; justify-content:space-between; gap:.7rem; padding:.72rem .85rem; border-bottom:1px solid rgba(148,163,184,.14); }
    #${ROOT_ID} .agent-title { font-weight:950; font-size:.84rem; color:#f8fafc; }
    #${ROOT_ID} .agent-badge { font-size:.67rem; font-weight:950; letter-spacing:.08em; text-transform:uppercase; color:#67e8f9; }
    #${ROOT_ID} .agent-log { max-height:10.5rem; overflow-y:auto; padding:.65rem .78rem; scroll-behavior:smooth; background:rgba(15,23,42,.52); }
    #${ROOT_ID} .agent-entry { display:grid; grid-template-columns:auto 1fr; gap:.48rem; padding:.38rem 0; border-bottom:1px solid rgba(148,163,184,.08); font-size:.73rem; line-height:1.35; }
    #${ROOT_ID} .agent-entry:last-child { border-bottom:0; }
    #${ROOT_ID} .agent-dot { width:.62rem; height:.62rem; border-radius:999px; margin-top:.2rem; background:#fbbf24; box-shadow:0 0 0 .2rem rgba(251,191,36,.12); }
    #${ROOT_ID} .agent-entry.green .agent-dot { background:#34d399; box-shadow:0 0 0 .2rem rgba(52,211,153,.12); }
    #${ROOT_ID} .agent-entry.red .agent-dot { background:#fb7185; box-shadow:0 0 0 .2rem rgba(251,113,133,.13); }
    #${ROOT_ID} .agent-meta { display:block; color:#94a3b8; font-size:.64rem; font-weight:800; }
    #${ROOT_ID} .agent-thinking { display:flex; align-items:center; justify-content:space-between; gap:.65rem; padding:.58rem .78rem; border-top:1px solid rgba(148,163,184,.13); font-size:.76rem; color:#cbd5e1; }
    #${ROOT_ID} .agent-face { color:#67e8f9; font-weight:950; white-space:nowrap; }
    #${ROOT_ID} .agent-actions { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:.42rem; padding:.68rem .78rem .78rem; border-top:1px solid rgba(148,163,184,.13); }
    #${ROOT_ID} .agent-actions button { border:1px solid rgba(34,211,238,.28); border-radius:.78rem; background:rgba(8,47,73,.62); color:#e0f2fe; padding:.55rem .35rem; font-size:.72rem; font-weight:950; }
    #${ROOT_ID} .agent-actions button:active { transform:scale(.98); }
    #${ROOT_ID}.red { border-color:rgba(251,113,133,.48); }
    #${ROOT_ID}.green { border-color:rgba(52,211,153,.4); }
    #${ROOT_ID} .dots::after { content:''; animation: agentDots 1.25s steps(4,end) infinite; }
    @keyframes agentDots { 0%{content:''} 25%{content:'.'} 50%{content:'..'} 75%,100%{content:'...'} }
  `;
  document.head.appendChild(style);
}

function render(): void {
  if (typeof document === 'undefined') return;
  installStyle();

  const anchor = anchorShell();
  if (!anchor) return;

  let root = document.getElementById(ROOT_ID);
  if (!root) {
    root = document.createElement('section');
    root.id = ROOT_ID;
    anchor.insertAdjacentElement('afterend', root);
    root.addEventListener('click', (event) => {
      const target = event.target instanceof HTMLElement ? event.target.closest<HTMLButtonElement>('button[data-agent-action]') : null;
      const action = target?.dataset.agentAction;
      if (action) triggerAction(action);
    });
  }

  const state = currentCoachState();
  appendEntry(state);
  const logEntries = loadEntries();
  const thinking = state.thinking ? `<span class="dots">denkt</span>` : 'bereit';

  root.className = state.lamp;
  root.innerHTML = `
    <div class="agent-head">
      <div><div class="agent-title">Agenten-Monitor · Sovereign Bot</div><div class="agent-badge">Coach · Live Log · Actions</div></div>
      <div class="agent-face">${escapeHtml(face(`${state.title}${state.message}`))}</div>
    </div>
    <div class="agent-log" data-agent-log="true">
      ${logEntries.map((entry) => `<div class="agent-entry ${entry.lamp}"><span class="agent-dot"></span><div><span class="agent-meta">${new Date(entry.ts).toLocaleTimeString()} · ${escapeHtml(entry.source)}</span>${escapeHtml(entry.text)}</div></div>`).join('')}
    </div>
    <div class="agent-thinking">
      <span>${escapeHtml(state.title)} · ${thinking}</span>
      <span>${escapeHtml(state.action)}</span>
    </div>
    <div class="agent-actions">
      ${ACTIONS.map((action) => `<button type="button" data-agent-action="${escapeHtml(action)}">${escapeHtml(action)}</button>`).join('')}
    </div>
  `;

  const log = root.querySelector<HTMLElement>('[data-agent-log="true"]');
  if (log) log.scrollTop = log.scrollHeight;
}

export function installMobileAgentMonitor(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const mobileWindow = window as MobileAgentWindow;
  if (mobileWindow.__sovereignMobileAgentMonitorInstalled) return;
  mobileWindow.__sovereignMobileAgentMonitorInstalled = true;

  window.setTimeout(render, INITIAL_DELAY_MS);
  mobileWindow.__sovereignMobileAgentMonitorInterval = window.setInterval(render, RENDER_INTERVAL_MS);
}
