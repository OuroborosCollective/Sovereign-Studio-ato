type CoachLamp = 'green' | 'yellow' | 'red';
type CoachSource = 'runtime-library' | 'workflow' | 'repair' | 'telemetry' | 'metrics' | 'pattern-memory' | 'remote-memory' | 'runtime' | 'repo' | 'dom-fallback' | 'unknown';

interface ExternalCoachState {
  lamp: CoachLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
  source?: CoachSource;
  tick?: number;
  hash?: string;
  updatedAt?: number;
}

type AnyRecord = Record<string, unknown>;
type CoachWindow = Window & typeof globalThis & {
  __sovereignMobileCoachInterval?: number;
  __sovereignMobileCoachObserver?: MutationObserver;
  __sovereignMobileCoachRenderTimer?: number;
  __sovereignCoachState?: unknown;
  __sovereignMobileCoachState?: unknown;
  __sovereignRuntimeCoachState?: unknown;
  __sovereignRuntime?: unknown;
  sovereignRuntime?: unknown;
};

const ROOT_ID = 'sovereign-mobile-coach';
const STYLE_ID = 'sovereign-mobile-coach-style';
const STORAGE_KEY = 'sovereign-mobile-coach-state';
const INITIAL_RENDER_DELAY_MS = 700;
const MUTATION_RENDER_DELAY_MS = 120;
const RENDER_INTERVAL_MS = 100;
const STALLED_AFTER_MS = 90_000;
const STORED_STATE_TTL_MS = 20 * 60_000;
const TEXT_NODE = 4;
const ACCEPT = 1;
const REJECT = 2;

const EVENTS = [
  'sovereign:coach-state',
  'sovereign:runtime-coach-state',
  'sovereign:runtime-state',
  'sovereign:workflow-state',
  'sovereign:repair-state',
  'sovereign:telemetry-state',
  'sovereign:metrics-state',
  'sovereign:pattern-memory-state',
  'sovereign:remote-memory-state',
  'sovereign:store-runtime-state',
];

const THINKING = ['running', 'in progress', 'busy', 'workflow running', 'package-build running', 'loading repo', 'metrics running', 'läuft'];
const READY = ['self review: accepted', 'generated-output-accepted', 'generated package passed self review', 'checks passed', 'green gate passed', 'code wiederhergestellt', 'code gesichert'];
const REPO_MISSING = ['repo fehlt', 'noch kein echtes repo', 'repo snapshot required', 'repository snapshot is not ready'];
const HEALTHY = ['runtime validation coverage', '21/21 runtime validation', 'runtime healthy', 'healthy'];
const GENERATED = ['generated files', 'generated file', 'files generated', 'pre-publish review'];
const MISSION = ['concrete mission', 'mission required', 'auftrag fehlt', 'konkreten auftrag', 'platzhalter'];
const MEMORY = ['pattern memory', 'remote memory', 'memory accepted', 'pattern accepted'];
const ACCEPTED = ['workflow accepted', 'workflow queued', 'mission accepted', 'auftrag angenommen'];
const STOPPERS = ['validation_failed', 'draft pr failed', 'build failed', 'workflow failed', 'critical blocker', 'typeerror', 'referenceerror', 'syntaxerror', 'fatal', 'error:', 'fehlgeschlagen'];
const HARMLESS = ['0 failed', '0 errors', 'no error', 'no errors', 'workflow: idle', 'no active step; 0 completed step(s), 0 failed step(s)'];
const FACES = ['_@=@_', '○¤○', '^-_-^', '[>->_]', ',.;@-@;.,', '｡◕‿◕｡'];

let lastValidState: ExternalCoachState | null = null;
let lastRuntimeState: ExternalCoachState | null = null;
let bridgeInstalled = false;

export function wallClockMs(): number {
  return Date.now();
}

function norm(value: string): string {
  return value.toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss').replace(/\s+/g, ' ').trim();
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function num(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function bool(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') return value;
  if (typeof value !== 'string') return undefined;
  const normalized = norm(value);
  if (['1', 'true', 'yes', 'on', 'running', 'busy', 'active'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off', 'idle', 'ready', 'done'].includes(normalized)) return false;
  return undefined;
}

function record(value: unknown): value is AnyRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function source(value: unknown, fallback: CoachSource): CoachSource {
  return value === 'runtime-library' || value === 'workflow' || value === 'repair' || value === 'telemetry' || value === 'metrics' || value === 'pattern-memory' || value === 'remote-memory' || value === 'runtime' || value === 'repo' || value === 'dom-fallback'
    ? value
    : fallback;
}

function has(sourceText: string, tokens: string[]): boolean {
  const normalized = norm(sourceText);
  return tokens.some((token) => normalized.includes(norm(token)));
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

function normalizeState(value: unknown, fallbackSource: CoachSource): ExternalCoachState | null {
  if (!record(value)) return null;
  const lamp = value.lamp === 'green' || value.lamp === 'yellow' || value.lamp === 'red' ? value.lamp : null;
  const title = text(value.title);
  const message = text(value.message);
  const action = text(value.action);
  const src = source(value.source, fallbackSource);
  const tick = num(value.tick) ?? num(value.sequence);
  const stateHash = text(value.hash) || text(value.worldHash) || text(value.snapshotHash) || undefined;

  if (lamp && title && message && action) {
    return { lamp, title, message, action, thinking: bool(value.thinking) ?? false, source: src, tick, hash: stateHash, updatedAt: num(value.updatedAt) ?? wallClockMs() };
  }

  const status = norm(text(value.status) || text(value.state) || text(value.phase) || text(value.mode) || text(value.runState) || text(value.kind));
  const fallbackMessage = message || text(value.summary) || text(value.detail) || text(value.reason);
  const combined = `${status} ${fallbackMessage}`;
  if (!combined.trim() && tick === undefined && !stateHash) return null;

  if (has(combined, ['failed', 'failure', 'error', 'fatal', 'blocked', 'red'])) return { lamp: 'red', title: 'Runtime meldet einen Stopper', message: fallbackMessage || 'Die Runtime-Library hat einen blockierenden Zustand gemeldet.', action: 'Repair/Logs pruefen.', thinking: false, source: src, tick, hash: stateHash, updatedAt: wallClockMs() };
  if (has(combined, ['running', 'busy', 'active', 'building', 'watching', 'progress'])) return { lamp: 'green', title: 'Runtime arbeitet', message: fallbackMessage || 'Die Runtime-Library liefert aktive Workflow-, Telemetry- oder Metrik-Signale.', action: 'Bitte warten.', thinking: true, source: src, tick, hash: stateHash, updatedAt: wallClockMs() };
  if (has(combined, ['accepted', 'ready', 'healthy', 'passed', 'green', 'done', 'complete', 'written', 'restored'])) return { lamp: 'green', title: combined.includes('restored') ? 'Code wiederhergestellt' : 'Runtime ist bereit', message: fallbackMessage || 'Die Runtime-Library meldet einen gueltigen akzeptierten Zustand.', action: 'Files/Diff oder Monitor pruefen.', thinking: false, source: src, tick, hash: stateHash, updatedAt: wallClockMs() };
  return { lamp: 'yellow', title: 'Runtime wartet', message: fallbackMessage || 'Die Runtime-Library wartet auf Repo, Auftrag oder naechsten Schritt.', action: 'Repo/Plan pruefen.', thinking: false, source: src, tick, hash: stateHash, updatedAt: wallClockMs() };
}

function save(state: ExternalCoachState): void {
  try { window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ...state, updatedAt: state.updatedAt ?? wallClockMs() })); } catch { /* optional */ }
}

function stored(): ExternalCoachState | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const state = normalizeState(JSON.parse(raw), 'runtime-library');
    if (!state?.updatedAt || wallClockMs() - state.updatedAt > STORED_STATE_TTL_MS) return null;
    return state;
  } catch {
    return null;
  }
}

function remember(state: ExternalCoachState): ExternalCoachState {
  const normalized = { ...state, updatedAt: state.updatedAt ?? wallClockMs() };
  lastValidState = normalized;
  save(normalized);
  return normalized;
}

function stalled(state: ExternalCoachState): boolean {
  return state.thinking && wallClockMs() - (state.updatedAt ?? wallClockMs()) >= STALLED_AFTER_MS;
}

function stalledState(state: ExternalCoachState): ExternalCoachState {
  return { lamp: 'yellow', title: 'Aktivitaet ohne neues Runtime-Signal', message: 'Der Ablauf meldet noch Arbeit, aber Tick, Hash oder Update-Zeit bewegen sich nicht weiter. Oeffne Logs oder Repair, ohne den Auftrag neu zu starten.', action: 'Logs/Repair pruefen.', thinking: false, source: state.source ?? 'runtime-library', tick: state.tick, hash: state.hash, updatedAt: wallClockMs() };
}

function accept(value: unknown, fallbackSource: CoachSource): ExternalCoachState | null {
  const incoming = normalizeState(value, fallbackSource);
  if (!incoming) return null;
  const current = lastRuntimeState ?? lastValidState ?? stored();
  if (current && incoming.source === current.source && incoming.tick !== undefined && current.tick !== undefined && incoming.tick < current.tick) return current;
  if (current?.lamp === 'red' && incoming.lamp !== 'red' && incoming.thinking) return current;
  const accepted = remember(incoming);
  lastRuntimeState = accepted;
  scheduleRender();
  return accepted;
}

function runtimeObjectState(runtime: unknown): ExternalCoachState | null {
  if (!record(runtime)) return null;
  const direct = normalizeState(runtime.coachState ?? runtime.mobileCoachState ?? runtime.operatorCoachState ?? runtime.state ?? runtime.snapshot, 'runtime-library');
  if (direct) return direct;
  for (const key of ['getCoachState', 'getMobileCoachState', 'getSnapshot']) {
    if (typeof runtime[key] === 'function') {
      try { return normalizeState((runtime[key] as () => unknown).call(runtime), 'runtime-library'); } catch { return null; }
    }
  }
  return normalizeState(runtime.telemetry, 'telemetry') ?? normalizeState(runtime.metrics, 'metrics') ?? normalizeState(runtime.workflow, 'workflow') ?? normalizeState(runtime.patternMemory, 'pattern-memory') ?? normalizeState(runtime.remoteMemory, 'remote-memory');
}

function assignedRuntimeState(): ExternalCoachState | null {
  const win = window as CoachWindow;
  return normalizeState(win.__sovereignRuntimeCoachState, 'runtime-library') ?? normalizeState(win.__sovereignCoachState, 'runtime-library') ?? normalizeState(win.__sovereignMobileCoachState, 'runtime-library') ?? runtimeObjectState(win.__sovereignRuntime) ?? runtimeObjectState(win.sovereignRuntime);
}

function insideCoach(node: Node | null): boolean {
  if (!node) return false;
  const element = node instanceof Element ? node : node.parentElement;
  return Boolean(element?.closest(`#${ROOT_ID}, #${STYLE_ID}, script, style, noscript`));
}

function bodySignal(): { raw: string; normalized: string; lines: string[]; strong: boolean } {
  if (!document.body) return { raw: '', normalized: '', lines: [], strong: false };
  const parts: string[] = [];
  const walker = document.createTreeWalker(document.body, TEXT_NODE, { acceptNode: (node) => insideCoach(node) ? REJECT : ACCEPT });
  let node = walker.nextNode();
  while (node) {
    const value = node.nodeValue?.trim();
    if (value) parts.push(value);
    node = walker.nextNode();
  }
  const raw = parts.join('\n');
  const normalized = norm(raw);
  const lines = raw.split(/\n+/).map(norm).filter(Boolean);
  const strong = realStopper(lines) || has(normalized, [...THINKING, ...READY, ...REPO_MISSING, ...HEALTHY, ...GENERATED, ...MISSION, ...MEMORY, ...ACCEPTED]);
  return { raw, normalized, lines, strong };
}

function realStopper(lines: string[]): boolean {
  return lines.some((line) => has(line, STOPPERS) && !has(line, HARMLESS));
}

function domDataState(): ExternalCoachState | null {
  const carrier = document.querySelector<HTMLElement>('[data-sovereign-coach-state], [data-coach-lamp], [data-coach-title], [data-coach-message], [data-coach-action]');
  if (!carrier || carrier.closest(`#${ROOT_ID}`)) return null;
  const json = carrier.getAttribute('data-sovereign-coach-state');
  if (json) {
    try { return normalizeState(JSON.parse(json), 'dom-fallback'); } catch { return null; }
  }
  return normalizeState({ lamp: carrier.getAttribute('data-coach-lamp'), title: carrier.getAttribute('data-coach-title'), message: carrier.getAttribute('data-coach-message'), action: carrier.getAttribute('data-coach-action'), thinking: carrier.getAttribute('data-coach-thinking'), source: 'dom-fallback' }, 'dom-fallback');
}

function domState(signal = bodySignal()): ExternalCoachState {
  const dataState = domDataState();
  if (dataState) return remember(dataState);
  if (realStopper(signal.lines)) return remember({ lamp: 'red', title: 'Ich sehe einen echten Stopper', message: 'Ich zeige dir jetzt Repair oder Logs. Folge nur dem naechsten markierten Schritt.', action: 'Repair/Logs automatisch pruefen.', thinking: false, source: 'dom-fallback', updatedAt: wallClockMs() });
  if (has(signal.normalized, THINKING) && !has(signal.normalized, READY)) return remember({ lamp: 'green', title: 'Ich arbeite gerade', message: 'Ich analysiere und pruefe. Du musst jetzt nichts suchen oder klicken.', action: 'Bitte warten.', thinking: true, source: 'dom-fallback', updatedAt: wallClockMs() });
  if (has(signal.normalized, READY)) return remember({ lamp: 'green', title: has(signal.normalized, ['code wiederhergestellt']) ? 'Code wiederhergestellt' : 'Ergebnis ist bereit', message: 'Die Dateien sind akzeptiert. Pruefe Files und Diff. Danach kann der Draft PR bewusst erstellt werden.', action: 'Files/Diff pruefen.', thinking: false, source: 'dom-fallback', updatedAt: wallClockMs() });
  if (has(signal.normalized, REPO_MISSING)) return remember({ lamp: 'yellow', title: 'Ich brauche zuerst dein Repo', message: 'Oeffne das Zahnrad oder tippe Repo. Trage Repository URL und optional privaten Zugang ein. Danach Load Repo.', action: 'Repo Setup oeffnen.', thinking: false, source: 'dom-fallback', updatedAt: wallClockMs() });
  if (has(signal.normalized, GENERATED)) return remember({ lamp: 'green', title: 'Ich habe Ergebnis-Dateien', message: 'Pruefe kurz die erzeugten Dateien. Wenn alles passt, geht es weiter zum Draft PR.', action: 'Dateien pruefen.', thinking: false, source: 'dom-fallback', updatedAt: wallClockMs() });
  if (has(signal.normalized, ACCEPTED)) return remember({ lamp: 'green', title: 'Auftrag ist angenommen', message: 'Der externe Auftrag wurde erkannt und bleibt im Ablauf.', action: 'Plan/Logs verfolgen.', thinking: false, source: 'dom-fallback', updatedAt: wallClockMs() });
  if (has(signal.normalized, MEMORY)) return remember({ lamp: 'green', title: 'Pattern Memory ist aktiv', message: 'Pattern- oder Memory-Signale wurden erkannt.', action: 'Pattern/Memory pruefen.', thinking: false, source: 'dom-fallback', updatedAt: wallClockMs() });
  if (has(signal.normalized, HEALTHY)) return remember({ lamp: 'green', title: 'Checks sehen gesund aus', message: 'Die Runtime-Pruefung ist gruen. Du kannst zum Repo, Plan oder Dateien zurueck.', action: 'Weiter im Hauptfluss.', thinking: false, source: 'dom-fallback', updatedAt: wallClockMs() });
  if (has(signal.normalized, MISSION)) return remember({ lamp: 'yellow', title: 'Ich brauche deinen Wunsch', message: 'Schreibe kurz, was ich verbessern soll. Ich plane danach automatisch weiter.', action: 'Auftrag schreiben.', thinking: false, source: 'dom-fallback', updatedAt: wallClockMs() });
  return remember({ lamp: 'yellow', title: 'Ich warte auf den Start', message: 'Beginne mit Repo Setup. Danach fuehre ich dich Schritt fuer Schritt weiter.', action: 'Repo oeffnen.', thinking: false, source: 'dom-fallback', updatedAt: wallClockMs() });
}

function coachState(): ExternalCoachState {
  const runtime = assignedRuntimeState();
  if (runtime) return remember(stalled(runtime) ? stalledState(runtime) : runtime);
  if (lastRuntimeState) return stalled(lastRuntimeState) ? remember(stalledState(lastRuntimeState)) : lastRuntimeState;
  const signal = bodySignal();
  if (signal.strong) return domState(signal);
  const recovery = lastValidState ?? stored();
  if (recovery && recovery.source !== 'dom-fallback') return remember(stalled(recovery) ? stalledState(recovery) : recovery);
  return domState(signal);
}

function installStyle(): void {
  document.getElementById(STYLE_ID)?.remove();
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `#${ROOT_ID}{border:1px solid rgba(34,211,238,.28);border-radius:1.25rem;background:#020617;color:#e2e8f0;overflow:hidden;font-family:Inter,ui-sans-serif,system-ui,sans-serif}#${ROOT_ID}.green{border-color:#34d399}#${ROOT_ID}.yellow{border-color:#fbbf24}#${ROOT_ID}.red{border-color:#fb7185}#${ROOT_ID} .coach-head{display:flex;align-items:center;gap:.7rem;padding:.85rem .9rem}#${ROOT_ID} .coach-bot{font-size:1.45rem}#${ROOT_ID} .coach-lamp{width:.78rem;height:.78rem;border-radius:999px;background:currentColor}#${ROOT_ID}.green .coach-lamp{color:#34d399}#${ROOT_ID}.yellow .coach-lamp{color:#fbbf24}#${ROOT_ID}.red .coach-lamp{color:#fb7185}#${ROOT_ID} .coach-title{font-weight:950;color:#f8fafc}#${ROOT_ID} .coach-action{color:#a5b4fc;font-size:.75rem;font-weight:850}#${ROOT_ID} .coach-body{border-top:1px solid rgba(148,163,184,.14);padding:.82rem .9rem .92rem}#${ROOT_ID} .coach-message{font-size:.82rem;line-height:1.38;color:#cbd5e1}#${ROOT_ID} .coach-terminal{margin-top:.78rem;min-height:9.8rem;border:1px solid rgba(34,211,238,.22);border-radius:.95rem;background:#000;padding:.78rem;color:#67e8f9;font:800 .72rem/1.55 ui-monospace,monospace}#${ROOT_ID} .terminal-line{display:block;white-space:pre-wrap}#${ROOT_ID} .terminal-dim{color:#94a3b8}#${ROOT_ID} .coach-buttons{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.42rem;margin-top:.72rem}#${ROOT_ID} .coach-buttons button{border:1px solid rgba(148,163,184,.25);border-radius:.82rem;background:#0f172a;color:#e2e8f0;padding:.5rem .35rem;font-size:.72rem;font-weight:850}`;
  document.head.appendChild(style);
}

function appShell(): HTMLElement | null {
  return document.querySelector('#root > div.min-h-screen') ?? document.querySelector('#root > div');
}

function navShell(): Element | null {
  const shell = appShell();
  return shell?.querySelector('[data-role="primary-nav"]') ?? shell?.querySelector('nav') ?? shell?.querySelector('[role="navigation"]') ?? shell?.firstElementChild ?? null;
}

function clickNav(label: string): void {
  const wanted = norm(label);
  const buttons = Array.from(document.querySelectorAll('button')).filter((button) => !button.closest(`#${ROOT_ID}`));
  const target = buttons.find((button) => norm(button.textContent ?? '') === wanted || norm(button.getAttribute('aria-label') ?? '') === wanted) ?? buttons.find((button) => norm(button.textContent ?? '').includes(wanted));
  target?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

function build(root: HTMLElement): void {
  root.setAttribute('aria-live', 'polite');
  root.replaceChildren();
  const head = document.createElement('div');
  head.className = 'coach-head';
  const bot = document.createElement('div');
  bot.className = 'coach-bot';
  bot.setAttribute('aria-hidden', 'true');
  bot.textContent = '🤖';
  const lamp = document.createElement('span');
  lamp.className = 'coach-lamp';
  lamp.setAttribute('aria-hidden', 'true');
  const copy = document.createElement('div');
  const title = document.createElement('div');
  title.className = 'coach-title';
  const action = document.createElement('div');
  action.className = 'coach-action';
  copy.append(title, action);
  head.append(bot, lamp, copy);
  const body = document.createElement('div');
  body.className = 'coach-body';
  const message = document.createElement('div');
  message.className = 'coach-message';
  const terminal = document.createElement('div');
  terminal.className = 'coach-terminal';
  terminal.setAttribute('aria-label', 'Sovereign Code Monitor Log');
  const buttons = document.createElement('div');
  buttons.className = 'coach-buttons';
  for (const [label, target] of [['Repo', 'Repo'], ['Planen', 'Builder'], ['Dateien', 'Files'], ['Logs', 'Live Monitor']] as Array<[string, string]>) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.go = target;
    button.textContent = label;
    button.addEventListener('click', () => clickNav(target));
    buttons.appendChild(button);
  }
  body.append(message, terminal, buttons);
  root.append(head, body);
}

function mode(state: ExternalCoachState): string {
  if (state.thinking) return 'matrix-work';
  if (state.lamp === 'red') return 'repair-log';
  if (state.source === 'runtime-library' || state.source === 'runtime') return 'runtime';
  if (state.title.includes('Ergebnis')) return 'review-log';
  return 'nocode-plan';
}

function lines(state: ExternalCoachState, coachMode: string): string[] {
  const prefix = `${coachMode} $ ${face(state.title)}`;
  if (state.lamp === 'red') return [`${prefix} stopper erkannt`, 'repair.scan(tick:auto) => blocked', `reason: ${state.message}`, `next: ${state.action}`];
  if (state.thinking) return [`${prefix} thinking loop aktiv`, 'read.signals(tick:auto) => ok', `status: ${state.message}`];
  return [`${prefix} monitor.update()`, `source:${state.source ?? 'dom'} tick:${state.tick ?? 'auto'}${state.hash ? ` hash:${state.hash}` : ''}`, `lamp:${state.lamp} thinking:${String(state.thinking)}`, `message: ${state.message}`, `next: ${state.action}`];
}

function rootAfter(nav: Element): HTMLElement {
  let root = document.getElementById(ROOT_ID);
  if (!root) {
    root = document.createElement('section');
    root.id = ROOT_ID;
    build(root);
  }
  if (!root.querySelector('.coach-title')) build(root);
  if (root.previousElementSibling !== nav) nav.insertAdjacentElement('afterend', root);
  return root;
}

function renderCoach(): void {
  try {
    installStyle();
    const nav = navShell();
    if (!appShell() || !nav) return;
    const root = rootAfter(nav);
    const state = coachState();
    const coachMode = mode(state);
    const terminalLines = lines(state, coachMode);
    const signature = JSON.stringify({ state, coachMode, terminalLines });
    if (root.dataset.signature === signature) return;
    root.dataset.signature = signature;
    root.className = state.lamp;
    root.querySelector('.coach-title')!.textContent = `Sovereign Bot · ${state.title}`;
    root.querySelector('.coach-action')!.textContent = state.action;
    root.querySelector('.coach-message')!.textContent = state.message;
    const terminal = root.querySelector('.coach-terminal')!;
    terminal.replaceChildren(...terminalLines.map((line) => {
      const span = document.createElement('span');
      span.className = line.startsWith('source:') || line.startsWith('lamp:') ? 'terminal-line terminal-dim' : 'terminal-line';
      span.textContent = line;
      return span;
    }));
  } catch (error) {
    console.warn('[Coach] Render error (non-fatal):', error instanceof Error ? error.message : String(error));
  }
}

function scheduleRender(): void {
  const win = window as CoachWindow;
  if (win.__sovereignMobileCoachRenderTimer) window.clearTimeout(win.__sovereignMobileCoachRenderTimer);
  win.__sovereignMobileCoachRenderTimer = window.setTimeout(() => {
    win.__sovereignMobileCoachRenderTimer = undefined;
    renderCoach();
  }, MUTATION_RENDER_DELAY_MS);
}

function eventSource(eventName: string): CoachSource {
  if (eventName.includes('workflow')) return 'workflow';
  if (eventName.includes('repair')) return 'repair';
  if (eventName.includes('telemetry')) return 'telemetry';
  if (eventName.includes('metrics')) return 'metrics';
  if (eventName.includes('pattern-memory')) return 'pattern-memory';
  if (eventName.includes('remote-memory')) return 'remote-memory';
  if (eventName.includes('store-runtime')) return 'runtime';
  return eventName.includes('runtime') ? 'runtime-library' : 'runtime-library';
}

function installBridge(): void {
  if (bridgeInstalled) return;
  bridgeInstalled = true;
  for (const eventName of EVENTS) {
    window.addEventListener(eventName, (event) => accept(event instanceof CustomEvent ? event.detail : null, eventSource(eventName)));
  }
}

export function publishMobileOperatorCoachState(state: ExternalCoachState): void {
  if (typeof window === 'undefined') return;
  accept({ ...state, source: state.source ?? 'runtime-library', updatedAt: state.updatedAt ?? wallClockMs() }, state.source ?? 'runtime-library');
}

export function installMobileOperatorCoach(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const win = window as CoachWindow;
  installBridge();
  if (!lastValidState) lastValidState = stored();
  window.setTimeout(renderCoach, INITIAL_RENDER_DELAY_MS);
  if (!win.__sovereignMobileCoachInterval) win.__sovereignMobileCoachInterval = window.setInterval(renderCoach, RENDER_INTERVAL_MS);
  if (!win.__sovereignMobileCoachObserver && document.body) {
    win.__sovereignMobileCoachObserver = new MutationObserver((records) => {
      if (records.every((record) => insideCoach(record.target))) return;
      scheduleRender();
    });
    win.__sovereignMobileCoachObserver.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true });
  }
}
