import { canSovereignProductTemplateAutoOpen, type SovereignProductTemplateAutoNavigationReason } from './features/product/runtime/sovereignProductTemplate';
import { assertMobileWorkflowDecisionValid, decideMobileWorkflow, type MobileWorkflowOrchestratorDecision } from './mobile-workflow-orchestrator';

export type MobileAgentLamp = 'green' | 'yellow' | 'red';

export interface MobileAgentCoachState {
  lamp: MobileAgentLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
  source?: string;
  updatedAt?: number;
  targetNav?: string;
  autoOpenTarget?: boolean;
  autoOpenReason?: SovereignProductTemplateAutoNavigationReason;
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

interface AgentAction {
  label: string;
  targetLabels: string[];
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
const STALE_THINKING_MS = 90_000;
const AUTO_OPEN_COOLDOWN_MS = 6_000;
const FOLLOW_UP_CLICK_DELAY_MS = 180;
const TEXT_NODE = 4;
const ACCEPT = 1;
const REJECT = 2;

const ACTIONS: AgentAction[] = [
  { label: 'Auftrag planen', targetLabels: ['Builder'] },
  { label: 'Package bauen', targetLabels: ['Auftrag in Produktion geben', 'Builder'] },
  { label: 'Files prüfen', targetLabels: ['Files'] },
  { label: 'Diff prüfen', targetLabels: ['Diff'] },
  { label: 'Workflow', targetLabels: ['Workflow'] },
  { label: 'Repair', targetLabels: ['Repair'] },
];

const FACES = ['^-_-^', '｡◕‿◕｡', '○¤○', '[>->_]', '_@=@_'];
const RUNTIME_EVENT_NAMES = [
  'sovereign:runtime-coach-state',
  'sovereign:runtime-state',
  'sovereign:metrics-state',
  'sovereign:workflow-state',
  'sovereign:telemetry-state',
  'sovereign:setup-state',
] as const;

let entries: MobileAgentLogEntry[] = [];
let lastSignature = '';
let lastTarget = '';
let lastTargetAt = 0;
let lastStableState: MobileAgentCoachState | null = null;

function now(): number {
  return Date.now();
}

function record(value: unknown): value is AnyRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function norm(value: string): string {
  return value.toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss').replace(/\s+/g, ' ').trim();
}

function bool(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') return value;
  if (typeof value !== 'string') return undefined;
  const normalized = norm(value);
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
    targetNav: text(value.targetNav),
    autoOpenTarget: bool(value.autoOpenTarget),
    autoOpenReason: value.autoOpenReason === 'active-work' || value.autoOpenReason === 'red-stopper' || value.autoOpenReason === 'passive-review' || value.autoOpenReason === 'awaiting-intent' || value.autoOpenReason === 'side-channel' || value.autoOpenReason === 'manual' ? value.autoOpenReason : undefined,
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
      targetNav: 'Live Monitor',
      autoOpenTarget: true,
      autoOpenReason: 'active-work',
    };
  }

  if (setup.setupPhase === 'repo-error' || setup.dependencyHealthy === false) {
    return {
      lamp: 'red',
      title: 'Repo Setup braucht Aufmerksamkeit',
      message: setup.status || 'GitHub Repo oder Zugriff ist noch nicht gültig.',
      action: 'Repo/PAT prüfen und erneut laden.',
      thinking: false,
      source: 'setup',
      updatedAt: setup.updatedAt ?? now(),
      targetNav: 'Repo',
      autoOpenTarget: true,
      autoOpenReason: 'red-stopper',
    };
  }

  if (setup.repoReady) {
    return {
      lamp: 'green',
      title: 'Bereit für Auftrag',
      message: setup.status || 'Repository ist geladen. Jetzt Auftrag planen oder Package bauen.',
      action: 'Auftrag planen oder Package bauen.',
      thinking: false,
      source: 'setup',
      updatedAt: setup.updatedAt ?? now(),
      targetNav: 'Builder',
      autoOpenTarget: false,
    };
  }

  return {
    lamp: 'yellow',
    title: 'Repository laden',
    message: setup.hasToken ? 'GitHub-Zugang ist gesetzt. Bitte Repository laden.' : 'Bitte GitHub-URL eingeben und Repository laden.',
    action: 'Repo laden.',
    thinking: false,
    source: 'repo',
    updatedAt: setup.updatedAt ?? now(),
  };
}

function deriveEventCoachState(value: unknown): MobileAgentCoachState | null {
  const normalized = normalizeCoachState(value);
  if (normalized) return normalized;
  if (!record(value)) return null;

  const status = norm(text(value.status));
  const message = text(value.message) || text(value.summary) || text(value.reason) || text(value.error);
  const running = ['running', 'busy', 'active', 'pending'].includes(status);
  const failed = ['failed', 'failure', 'error', 'red', 'blocked'].includes(status) || Boolean(text(value.error));

  if (failed) {
    return {
      lamp: 'red',
      title: 'Runtime Stopper',
      message: message || 'Ein Runtime-Signal meldet einen Stopper.',
      action: 'Repair prüfen.',
      thinking: false,
      source: 'runtime-event',
      updatedAt: now(),
      targetNav: 'Repair',
      autoOpenTarget: true,
      autoOpenReason: 'red-stopper',
    };
  }

  if (running) {
    return {
      lamp: 'green',
      title: 'Runtime arbeitet',
      message: message || 'Ein Runtime-Signal ist aktiv.',
      action: 'Live Monitor prüfen.',
      thinking: true,
      source: 'runtime-event',
      updatedAt: now(),
      targetNav: 'Live Monitor',
      autoOpenTarget: true,
      autoOpenReason: 'active-work',
    };
  }

  if (message) {
    return {
      lamp: 'yellow',
      title: 'Runtime Signal',
      message,
      action: 'Status prüfen.',
      thinking: false,
      source: 'runtime-event',
      updatedAt: now(),
    };
  }

  return null;
}

function withStaleThinkingGuard(state: MobileAgentCoachState): MobileAgentCoachState {
  if (!state.thinking) return state;
  const updatedAt = state.updatedAt ?? now();
  if (now() - updatedAt <= STALE_THINKING_MS) return state;

  return {
    ...state,
    lamp: 'yellow',
    title: 'Aktivität ohne neues Runtime-Signal',
    message: `${state.title}: ${state.message}`,
    action: 'Repair oder Live Monitor prüfen.',
    thinking: false,
    source: state.source ?? 'stale-runtime',
    updatedAt,
    targetNav: 'Repair',
    autoOpenTarget: true,
    autoOpenReason: 'red-stopper',
  };
}

function isRepoReadyState(state: MobileAgentCoachState | null | undefined): boolean {
  if (!state) return false;
  const combined = norm(`${state.title} ${state.message} ${state.action}`);
  return combined.includes('bereit fuer auftrag') || combined.includes('repository ist geladen') || combined.includes('repo snapshot ist bereit') || combined.includes('repo snapshot ready');
}

function isRepoLoadPromptState(state: MobileAgentCoachState | null | undefined): boolean {
  if (!state) return false;
  const combined = norm(`${state.title} ${state.message} ${state.action}`);
  return combined.includes('repository laden') || combined.includes('repo laden') || combined.includes('github-url eingeben') || combined.includes('keinen lokalen code-stand') || combined.includes('kein gespeicherter code');
}

function shouldPreferSetupReady(setup: MobileAgentCoachState | null, runtime: MobileAgentCoachState | null): boolean {
  if (!isRepoReadyState(setup)) return false;
  if (!runtime) return true;
  if (runtime.lamp === 'red') return false;
  if (runtime.thinking) return false;
  if (isRepoLoadPromptState(runtime)) return true;
  return runtime.lamp === 'yellow' && runtime.source !== 'runtime-library';
}

function classifyWorkflowAutoOpenReason(decision: MobileWorkflowOrchestratorDecision): SovereignProductTemplateAutoNavigationReason {
  if (decision.lamp === 'red') return 'red-stopper';
  if (decision.mode === 'matrix-work') return 'active-work';
  if (decision.mode === 'review-log') return 'passive-review';
  if (decision.mode === 'nocode-plan') return 'awaiting-intent';
  return 'side-channel';
}

function workflowCoachState(): MobileAgentCoachState {
  try {
    const decision = decideMobileWorkflow({ visibleText: collectMobileAgentVisibleText() });
    assertMobileWorkflowDecisionValid(decision);
    return {
      lamp: decision.lamp,
      title: decision.title,
      message: decision.summary,
      action: decision.targetNav ? `${decision.targetNav} prüfen.` : 'Nächsten Schritt wählen.',
      thinking: decision.mode === 'matrix-work',
      source: decision.mode,
      updatedAt: now(),
      targetNav: decision.targetNav,
      autoOpenTarget: decision.autoOpenTarget,
      autoOpenReason: classifyWorkflowAutoOpenReason(decision),
    };
  } catch {
    return {
      lamp: 'yellow',
      title: 'Agent Monitor wartet',
      message: 'Noch kein stabiler Runtime-Zustand erkannt.',
      action: 'Repo oder Auftrag prüfen.',
      thinking: false,
      source: 'monitor',
      updatedAt: now(),
    };
  }
}

function currentCoachState(): MobileAgentCoachState {
  const win = window as MobileAgentWindow;
  const setup = setupCoachState(win.__sovereignSetupState);
  const runtime = normalizeCoachState(win.__sovereignRuntimeCoachState)
    ?? normalizeCoachState(win.__sovereignCoachState)
    ?? normalizeCoachState(win.__sovereignMobileCoachState);

  const selected = shouldPreferSetupReady(setup, runtime)
    ? setup
    : runtime ?? setup ?? workflowCoachState();

  const guarded = withStaleThinkingGuard(selected);
  lastStableState = guarded;
  return guarded;
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

function pruneEntriesForState(state: MobileAgentCoachState, current: MobileAgentLogEntry[]): MobileAgentLogEntry[] {
  if (!isRepoReadyState(state)) return current;
  return current.filter((entry) => {
    const entryText = norm(entry.text);
    return !entryText.includes('repository laden')
      && !entryText.includes('repo setup bereit')
      && !entryText.includes('kein gespeicherter code')
      && !entryText.includes('keinen lokalen code-stand');
  });
}

function appendEntry(state: MobileAgentCoachState): void {
  const signature = `${state.lamp}|${state.source ?? 'agent'}|${state.title}|${state.message}|${state.action}|${state.thinking}`;
  const current = pruneEntriesForState(state, loadEntries());
  if (signature === lastSignature) {
    entries = current.slice(-MAX_LOG_ENTRIES);
    saveEntries();
    return;
  }
  lastSignature = signature;

  entries = [
    ...current,
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
  const wanted = norm(label);
  return Array.from(document.querySelectorAll('button')).find((button) => {
    if (button.closest(ignoredSelector())) return false;
    const candidate = norm(`${button.textContent ?? ''} ${button.getAttribute('aria-label') ?? ''}`);
    return candidate === wanted || candidate.includes(wanted);
  }) ?? null;
}

function clickButton(button: HTMLButtonElement): void {
  button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

function triggerAction(label: string): void {
  const action = ACTIONS.find((item) => item.label === label) ?? { label, targetLabels: [label] };
  for (const targetLabel of action.targetLabels) {
    const button = findActionButton(targetLabel);
    if (button) {
      clickButton(button);
      if (label === 'Package bauen' && targetLabel === 'Builder') {
        window.setTimeout(() => {
          const production = findActionButton('Auftrag in Produktion geben');
          if (production && !production.disabled) clickButton(production);
        }, FOLLOW_UP_CLICK_DELAY_MS);
      }
      return;
    }
  }
}

function maybeAutoOpenTarget(state: MobileAgentCoachState): void {
  if (!state.autoOpenTarget || !state.targetNav || !state.autoOpenReason) return;
  if (!canSovereignProductTemplateAutoOpen(state.autoOpenReason)) return;

  const nowMs = now();
  if (lastTarget === state.targetNav && nowMs - lastTargetAt < AUTO_OPEN_COOLDOWN_MS) return;
  lastTarget = state.targetNav;
  lastTargetAt = nowMs;
  triggerAction(state.targetNav);
}

function anchorShell(): Element | null {
  return document.querySelector('#root > div.min-h-screen > div:nth-of-type(1)');
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
    #${ROOT_ID} .agent-actions { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:.42rem; padding:.68rem .78rem .78rem; border-top:1px solid rgba(148,163,184,.13); }
    #${ROOT_ID} .agent-actions button { border:1px solid rgba(34,211,238,.28); border-radius:.78rem; background:rgba(8,47,73,.62); color:#e0f2fe; padding:.62rem .35rem; font-size:.72rem; font-weight:950; }
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
    root.addEventListener('click', (event) => {
      const target = event.target instanceof HTMLElement ? event.target.closest<HTMLButtonElement>('button[data-agent-action]') : null;
      const action = target?.dataset.agentAction;
      if (action) triggerAction(action);
    });
  }

  if (root.previousElementSibling !== anchor) {
    anchor.insertAdjacentElement('afterend', root);
  }

  const state = currentCoachState();
  appendEntry(state);
  maybeAutoOpenTarget(state);
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
      ${ACTIONS.map((action) => `<button type="button" data-agent-action="${escapeHtml(action.label)}">${escapeHtml(action.label)}</button>`).join('')}
    </div>
  `;

  const log = root.querySelector<HTMLElement>('[data-agent-log="true"]');
  if (log) log.scrollTop = log.scrollHeight;
}

function handleRuntimeEvent(event: Event): void {
  const detail = event instanceof CustomEvent ? event.detail : undefined;
  const state = deriveEventCoachState(detail);
  if (!state) return;

  const setup = setupCoachState((window as MobileAgentWindow).__sovereignSetupState);
  if (shouldPreferSetupReady(setup, state)) {
    (window as MobileAgentWindow).__sovereignRuntimeCoachState = setup;
    appendEntry(setup);
    render();
    return;
  }

  const mobileWindow = window as MobileAgentWindow;
  mobileWindow.__sovereignRuntimeCoachState = state;
  appendEntry(withStaleThinkingGuard(state));
  render();
}

export function installMobileAgentMonitor(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const mobileWindow = window as MobileAgentWindow;
  if (mobileWindow.__sovereignMobileAgentMonitorInstalled) return;
  mobileWindow.__sovereignMobileAgentMonitorInstalled = true;

  for (const eventName of RUNTIME_EVENT_NAMES) {
    window.addEventListener(eventName, handleRuntimeEvent);
  }

  window.setTimeout(render, INITIAL_DELAY_MS);
  mobileWindow.__sovereignMobileAgentMonitorInterval = window.setInterval(render, RENDER_INTERVAL_MS);
}
