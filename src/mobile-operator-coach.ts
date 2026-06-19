type CoachLamp = 'green' | 'yellow' | 'red';

type CoachSource =
  | 'runtime-library'
  | 'workflow'
  | 'repair'
  | 'telemetry'
  | 'metrics'
  | 'pattern-memory'
  | 'remote-memory'
  | 'runtime'
  | 'repo'
  | 'dom-fallback'
  | 'unknown';

interface CoachState {
  lamp: CoachLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
}

interface ExternalCoachState extends CoachState {
  source?: CoachSource;
  tick?: number;
  hash?: string;
  updatedAt?: number;
}

type UnknownRecord = Record<string, unknown>;

type CoachWindow = Window &
  typeof globalThis & {
    __sovereignMobileCoachInterval?: number;
    __sovereignMobileCoachObserver?: MutationObserver;
    __sovereignMobileCoachRenderTimer?: number;
    __sovereignMobileCoachEventInstalled?: boolean;
    __sovereignMobileCoachState?: ExternalCoachState;
    __sovereignCoachState?: ExternalCoachState;
    __sovereignRuntimeCoachState?: ExternalCoachState;
    __sovereignRuntime?: UnknownRecord;
    sovereignRuntime?: UnknownRecord;
  };

interface SignalSnapshot {
  raw: string;
  normalized: string;
  lines: string[];
  hash: number;
}

const STYLE_ID = 'sovereign-mobile-coach-style';
const ROOT_ID = 'sovereign-mobile-coach';
const STORAGE_KEY = 'sovereign-mobile-coach-state';

const RENDER_INTERVAL_MS = 1400;
const INITIAL_RENDER_DELAY_MS = 700;
const MUTATION_RENDER_DELAY_MS = 120;
const STALLED_AFTER_MS = 90_000;
const STORED_STATE_TTL_MS = 20 * 60_000;
const EMPTY_SOURCE_HOLD_MS = 8_000;
const MAX_TEXT_NODES = 500;
const MAX_ATTRIBUTE_NODES = 500;
const MAX_SIGNAL_CHARS = 50_000;
const MAX_TERMINAL_LINES = 6;

const SHOW_TEXT = 4;
const FILTER_ACCEPT = 1;
const FILTER_REJECT = 2;

const COACH_EVENTS = [
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

const SIGNAL_ATTRIBUTES = [
  'aria-label',
  'title',
  'data-state',
  'data-status',
  'data-phase',
  'data-step',
  'data-mode',
  'data-run',
  'data-run-state',
  'data-workflow',
  'data-health',
  'data-telemetry',
  'data-metric',
  'data-metrics',
  'data-pattern',
  'data-pattern-memory',
  'data-remote-memory',
  'data-coach-lamp',
  'data-coach-title',
  'data-coach-message',
  'data-coach-action',
  'data-coach-thinking',
  'data-sovereign-coach-state',
];

const THINKING_TOKENS = [
  'läuft',
  'running',
  'busy',
  'in progress',
  'is building',
  'is watching',
  'draft pr läuft',
  'draft pr running',
  'generating',
  'analysing',
  'analyzing',
  'loading repo',
  'repo loading',
  'workflow running',
  'workflow started',
  'repair running',
  'monitor running',
  'telemetry running',
  'metrics running',
  'pattern scan running',
  'code wird gesichert',
  'speicher laeuft',
];

const READY_TOKENS = [
  'self review: accepted',
  'generated-output-accepted',
  'generated package passed self review',
  'review accepted',
  'accepted output',
  'checks passed',
  'all checks passed',
  'green gate passed',
  'code wiederhergestellt',
  'code gesichert',
];

const REPO_MISSING_TOKENS = [
  'repo fehlt',
  'repo snapshot required',
  'repository snapshot is not ready',
  'noch kein echtes repo',
  'automation needs a loaded repository snapshot',
];

const GENERATED_FILE_TOKENS = [
  'pre-publish review',
  'generated file',
  'generated files',
  'files generated',
];

const RUNTIME_HEALTHY_TOKENS = [
  'runtime validation coverage',
  'healthy',
  '21/21 runtime validation',
  'runtime healthy',
];

const MISSION_MISSING_TOKENS = [
  'platzhalter',
  'konkreten auftrag',
  'concrete mission',
  'mission required',
  'auftrag fehlt',
];

const TELEMETRY_TOKENS = [
  'telemetry',
  'telemetrie',
  'metrics',
  'metriken',
  'runtime metrics',
  'live monitor',
  'health snapshot',
  'coverage',
];

const PATTERN_MEMORY_TOKENS = [
  'pattern memory',
  'remote memory',
  'memory synced',
  'memory accepted',
  'pattern accepted',
  'pattern scan',
  'pattern stored',
];

const WORKFLOW_ACCEPTED_TOKENS = [
  'auftrag angenommen',
  'mission accepted',
  'workflow queued',
  'workflow accepted',
  'plan accepted',
  'request accepted',
  'task accepted',
];

const HARMLESS_STOPPER_TOKENS = [
  '0 failed',
  '0 error',
  '0 errors',
  'no error',
  'no errors',
  'without errors',
  'keine fehler',
  '0 fehlgeschlagen',
  'no active step; 0 completed step(s), 0 failed step(s)',
  'repair oder monitor pruefen',
  'repair or monitor',
  'repair plan idle',
  'workflow: idle',
];

const REAL_STOPPER_TOKENS = [
  'validation_failed',
  'draft pr failed',
  'build failed',
  'workflow failed',
  'critical blocker',
  'fehlgeschlagen',
  'blockierender fehler',
  'uncaught',
  'typeerror',
  'referenceerror',
  'syntaxerror',
  'fatal',
  'error:',
];

const MIMU_SMILEYS = [
  '_@=@_',
  '○¤○',
  '^-_-^',
  '[>->_]',
  ',.;@-@;.,',
  '⌐■_■',
  '｡◕‿◕｡',
  '(-.-)zz',
  'づ｡◕‿‿◕｡づ',
  'ʕ•ᴥ•ʔ',
];

let lastSignalHash = 0;
let lastSignalChangeAt = 0;
let lastValidState: ExternalCoachState | null = null;
let lastValidStateAt = 0;

function nowMs(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

function wallClockMs(): number {
  return Date.now();
}

function normalizeText(value: string): string {
  return value.toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss').replace(/\s+/g, ' ').trim();
}

function toText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function toNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  return undefined;
}

function toBoolean(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') return value;
  if (typeof value !== 'string') return undefined;

  const normalized = normalizeText(value);
  if (['1', 'true', 'yes', 'on', 'running', 'busy', 'active'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off', 'idle', 'ready', 'done'].includes(normalized)) return false;

  return undefined;
}

function validLamp(value: unknown): CoachLamp | null {
  return value === 'green' || value === 'yellow' || value === 'red' ? value : null;
}

function validSource(value: unknown): CoachSource {
  if (
    value === 'runtime-library' ||
    value === 'workflow' ||
    value === 'repair' ||
    value === 'telemetry' ||
    value === 'metrics' ||
    value === 'pattern-memory' ||
    value === 'remote-memory' ||
    value === 'runtime' ||
    value === 'repo' ||
    value === 'dom-fallback'
  ) {
    return value;
  }

  return 'unknown';
}

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function hashString(value: string): number {
  let hash = 2166136261;

  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }

  return hash >>> 0;
}

function hasAny(source: string, tokens: string[]): boolean {
  const lower = normalizeText(source);
  return tokens.some((token) => lower.includes(normalizeText(token)));
}

function lineHasAny(line: string, tokens: string[]): boolean {
  return tokens.some((token) => line.includes(normalizeText(token)));
}

function latestSignalIndex(lines: string[], tokens: string[]): number {
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    if (lineHasAny(lines[index], tokens)) return index;
  }

  return -1;
}

function newestOf(...indexes: number[]): number {
  return Math.max(...indexes);
}

function latestRealStopperIndex(lines: string[]): number {
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index];

    if (lineHasAny(line, HARMLESS_STOPPER_TOKENS)) continue;
    if (lineHasAny(line, REAL_STOPPER_TOKENS)) return index;
  }

  return -1;
}

function mimuFace(seed: string | number | undefined): string {
  const hash = hashString(String(seed ?? wallClockMs()));
  return MIMU_SMILEYS[hash % MIMU_SMILEYS.length];
}

function isInsideCoach(node: Node | null): boolean {
  if (!node) return false;

  const element =
    typeof Element !== 'undefined' && node instanceof Element
      ? node
      : node.parentElement;

  return Boolean(element?.closest(`#${ROOT_ID}, #${STYLE_ID}, script, style, noscript`));
}

function readTextSignals(): string[] {
  if (!document.body) return [];

  const parts: string[] = [];
  let visited = 0;

  const walker = document.createTreeWalker(document.body, SHOW_TEXT, {
    acceptNode(node) {
      if (visited >= MAX_TEXT_NODES) return FILTER_REJECT;
      if (isInsideCoach(node)) return FILTER_REJECT;
      return FILTER_ACCEPT;
    },
  });

  let node = walker.nextNode();

  while (node && visited < MAX_TEXT_NODES) {
    visited += 1;

    const text = node.nodeValue?.trim();
    if (text) parts.push(text);

    node = walker.nextNode();
  }

  return parts;
}

function readAttributeSignals(): string[] {
  if (!document.body) return [];

  const parts: string[] = [];
  const elements = Array.from(document.body.querySelectorAll('*')).slice(0, MAX_ATTRIBUTE_NODES);

  for (const element of elements) {
    if (isInsideCoach(element)) continue;

    for (const attribute of SIGNAL_ATTRIBUTES) {
      const value = element.getAttribute(attribute)?.trim();
      if (value) parts.push(`${attribute}: ${value}`);
    }
  }

  return parts;
}

function readSignalSnapshot(): SignalSnapshot {
  const parts = [...readTextSignals(), ...readAttributeSignals()];
  const raw = parts.join('\n').slice(0, MAX_SIGNAL_CHARS);
  const normalized = normalizeText(raw);
  const lines = raw
    .split(/\n+/)
    .map(normalizeText)
    .filter(Boolean);

  return {
    raw,
    normalized,
    lines,
    hash: hashString(normalized),
  };
}

function normalizeExternalState(value: unknown, fallbackSource: CoachSource): ExternalCoachState | null {
  if (!isRecord(value)) return null;

  const lamp = validLamp(value.lamp);
  const title = toText(value.title);
  const message = toText(value.message);
  const action = toText(value.action);

  if (lamp && title && message && action) {
    return {
      lamp,
      title,
      message,
      action,
      thinking: toBoolean(value.thinking) ?? false,
      source: validSource(value.source) === 'unknown' ? fallbackSource : validSource(value.source),
      tick: toNumber(value.tick),
      hash: toText(value.hash) || undefined,
      updatedAt: toNumber(value.updatedAt) ?? wallClockMs(),
    };
  }

  return deriveStateFromRuntimePayload(value, fallbackSource);
}

function deriveStateFromRuntimePayload(value: UnknownRecord, fallbackSource: CoachSource): ExternalCoachState | null {
  const status = normalizeText(
    toText(value.status) ||
      toText(value.state) ||
      toText(value.phase) ||
      toText(value.mode) ||
      toText(value.runState) ||
      toText(value.kind),
  );

  const source = validSource(value.source) === 'unknown' ? fallbackSource : validSource(value.source);
  const tick = toNumber(value.tick) ?? toNumber(value.sequence);
  const hash = toText(value.hash) || toText(value.worldHash) || toText(value.snapshotHash) || undefined;
  const message =
    toText(value.message) ||
    toText(value.summary) ||
    toText(value.detail) ||
    toText(value.reason);

  if (!status && !message && tick === undefined && !hash) return null;

  if (status.includes('restored') || message.includes('restored')) {
    return {
      lamp: 'green',
      title: 'Code wiederhergestellt',
      message: message || 'Dein Code wurde lokal wiederhergestellt und in den Workspace geladen.',
      action: 'Weiterbauen.',
      thinking: false,
      source,
      tick,
      hash,
      updatedAt: wallClockMs(),
    };
  }

  if (status.includes('queued') || message.includes('queued') || message.includes('wird gesichert')) {
    return {
      lamp: 'green',
      title: 'Code wird gesichert',
      message: message || 'Ich schreibe den aktuellen Code-Stand in den lokalen Speicher.',
      action: 'Speicher laeuft.',
      thinking: true,
      source,
      tick,
      hash,
      updatedAt: wallClockMs(),
    };
  }

  if (
    status.includes('failed') ||
    status.includes('failure') ||
    status.includes('error') ||
    status.includes('fatal') ||
    status.includes('blocked') ||
    status.includes('red')
  ) {
    return {
      lamp: 'red',
      title: 'Runtime meldet einen Stopper',
      message: message || 'Die Runtime-Library hat einen blockierenden Zustand gemeldet.',
      action: 'Repair/Logs pruefen.',
      thinking: false,
      source,
      tick,
      hash,
      updatedAt: wallClockMs(),
    };
  }

  if (
    status.includes('running') ||
    status.includes('busy') ||
    status.includes('active') ||
    status.includes('building') ||
    status.includes('watching') ||
    status.includes('progress')
  ) {
    return {
      lamp: 'green',
      title: 'Runtime arbeitet',
      message: message || 'Die Runtime-Library liefert aktive Workflow-, Telemetry- oder Metrik-Signale.',
      action: 'Bitte warten.',
      thinking: true,
      source,
      tick,
      hash,
      updatedAt: wallClockMs(),
    };
  }

  if (
    status.includes('accepted') ||
    status.includes('ready') ||
    status.includes('healthy') ||
    status.includes('passed') ||
    status.includes('green') ||
    status.includes('done') ||
    status.includes('complete') ||
    status.includes('written')
  ) {
    return {
      lamp: 'green',
      title: status.includes('written') ? 'Code gesichert' : 'Runtime ist bereit',
      message: message || 'Die Runtime-Library meldet einen gueltigen akzeptierten Zustand.',
      action: status.includes('written') ? 'Alles gut.' : 'Files/Diff oder Monitor pruefen.',
      thinking: false,
      source,
      tick,
      hash,
      updatedAt: wallClockMs(),
    };
  }

  if (
    status.includes('missing') ||
    status.includes('idle') ||
    status.includes('waiting') ||
    status.includes('yellow')
  ) {
    return {
      lamp: 'yellow',
      title: 'Runtime wartet',
      message: message || 'Die Runtime-Library wartet auf Repo, Auftrag oder naechsten Schritt.',
      action: 'Repo/Plan pruefen.',
      thinking: false,
      source,
      tick,
      hash,
      updatedAt: wallClockMs(),
    };
  }

  return {
    lamp: 'green',
    title: 'Runtime-Signal empfangen',
    message: message || 'Ein gueltiges Runtime-Signal wurde angenommen und gehalten.',
    action: 'Live Monitor pruefen.',
    thinking: toBoolean(value.thinking) ?? false,
    source,
    tick,
    hash,
    updatedAt: wallClockMs(),
  };
}

function saveState(state: ExternalCoachState): void {
  const win = window as CoachWindow;
  const normalized = {
    ...state,
    updatedAt: state.updatedAt ?? wallClockMs(),
  };

  win.__sovereignMobileCoachState = normalized;
  win.__sovereignCoachState = normalized;

  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
  } catch {
    // sessionStorage can be blocked in some WebViews.
  }
}

function readStoredState(): ExternalCoachState | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw) as unknown;
    const state = normalizeExternalState(parsed, 'runtime-library');

    if (!state?.updatedAt) return null;
    if (wallClockMs() - state.updatedAt > STORED_STATE_TTL_MS) return null;

    return state;
  } catch {
    return null;
  }
}

function rememberState(state: ExternalCoachState): ExternalCoachState {
  const normalized = {
    ...state,
    updatedAt: state.updatedAt ?? wallClockMs(),
  };

  lastValidState = normalized;
  lastValidStateAt = nowMs();
  saveState(normalized);

  return normalized;
}

function shouldAcceptIncomingState(incoming: ExternalCoachState, current: ExternalCoachState | null): boolean {
  if (!current) return true;
  if (incoming.lamp === 'red') return true;
  if (current.lamp === 'red' && incoming.lamp !== 'red' && incoming.thinking) return false;

  if (
    incoming.tick !== undefined &&
    current.tick !== undefined &&
    incoming.source === current.source &&
    incoming.tick < current.tick
  ) {
    return false;
  }

  if (
    incoming.hash &&
    current.hash &&
    incoming.hash === current.hash &&
    incoming.thinking === current.thinking &&
    incoming.lamp === current.lamp
  ) {
    return false;
  }

  return true;
}

function acceptExternalCoachState(value: unknown, fallbackSource: CoachSource): ExternalCoachState | null {
  const incoming = normalizeExternalState(value, fallbackSource);
  if (!incoming) return null;

  const current = lastValidState ?? readStoredState();

  if (!shouldAcceptIncomingState(incoming, current)) {
    return current;
  }

  const accepted = rememberState(incoming);
  scheduleRender();

  return accepted;
}

function readRuntimeObjectState(runtime: unknown): ExternalCoachState | null {
  if (!isRecord(runtime)) return null;

  const direct =
    runtime.coachState ??
    runtime.mobileCoachState ??
    runtime.operatorCoachState ??
    runtime.state ??
    runtime.snapshot;

  const directState = normalizeExternalState(direct, 'runtime-library');
  if (directState) return directState;

  const getter =
    typeof runtime.getCoachState === 'function'
      ? runtime.getCoachState
      : typeof runtime.getMobileCoachState === 'function'
        ? runtime.getMobileCoachState
        : typeof runtime.getSnapshot === 'function'
          ? runtime.getSnapshot
          : null;

  if (getter) {
    try {
      return normalizeExternalState(getter.call(runtime), 'runtime-library');
    } catch {
      return null;
    }
  }

  const telemetry = normalizeExternalState(runtime.telemetry, 'telemetry');
  if (telemetry) return telemetry;

  const metrics = normalizeExternalState(runtime.metrics, 'metrics');
  if (metrics) return metrics;

  const workflow = normalizeExternalState(runtime.workflow, 'workflow');
  if (workflow) return workflow;

  const patternMemory = normalizeExternalState(runtime.patternMemory, 'pattern-memory');
  if (patternMemory) return patternMemory;

  const remoteMemory = normalizeExternalState(runtime.remoteMemory, 'remote-memory');
  if (remoteMemory) return remoteMemory;

  return null;
}

function readAssignedRuntimeState(): ExternalCoachState | null {
  const win = window as CoachWindow;

  const candidates: Array<[unknown, CoachSource]> = [
    [win.__sovereignRuntimeCoachState, 'runtime-library'],
    [win.__sovereignCoachState, 'runtime-library'],
    [win.__sovereignMobileCoachState, 'runtime-library'],
    [readRuntimeObjectState(win.__sovereignRuntime), 'runtime-library'],
    [readRuntimeObjectState(win.sovereignRuntime), 'runtime-library'],
  ];

  for (const [candidate, source] of candidates) {
    const state = normalizeExternalState(candidate, source);
    if (state) return state;
  }

  return readStoredState();
}

function sourceLooksStalled(state: ExternalCoachState): boolean {
  if (!state.thinking) return false;

  const updatedAt = state.updatedAt ?? wallClockMs();
  return wallClockMs() - updatedAt >= STALLED_AFTER_MS;
}

function stalledStateFrom(state: ExternalCoachState): ExternalCoachState {
  return {
    lamp: 'yellow',
    title: 'Aktivitaet ohne neues Runtime-Signal',
    message: 'Der Ablauf meldet noch Arbeit, aber Tick, Hash oder Update-Zeit bewegen sich nicht weiter. Oeffne Logs oder Repair, ohne den Auftrag neu zu starten.',
    action: 'Logs/Repair pruefen.',
    thinking: false,
    source: state.source ?? 'runtime-library',
    tick: state.tick,
    hash: state.hash,
    updatedAt: wallClockMs(),
  };
}

function readExternalCoachStateFromDom(): ExternalCoachState | null {
  const carrier =
    document.querySelector<HTMLElement>('[data-sovereign-coach-state], [data-coach-lamp], [data-coach-title], [data-coach-message], [data-coach-action]') ??
    document.body;

  if (!carrier) return null;

  const jsonState = carrier.getAttribute('data-sovereign-coach-state');

  if (jsonState) {
    try {
      return normalizeExternalState(JSON.parse(jsonState), 'dom-fallback');
    } catch {
      return null;
    }
  }

  const lamp = carrier.getAttribute('data-coach-lamp');
  const title = carrier.getAttribute('data-coach-title');
  const message = carrier.getAttribute('data-coach-message');
  const action = carrier.getAttribute('data-coach-action');
  const thinking = carrier.getAttribute('data-coach-thinking');

  return normalizeExternalState(
    {
      lamp,
      title,
      message,
      action,
      thinking,
      source: 'dom-fallback',
    },
    'dom-fallback',
  );
}

function readDomFallbackState(): ExternalCoachState {
  const snapshot = readSignalSnapshot();
  const domExternalState = readExternalCoachStateFromDom();

  if (!snapshot.raw && lastValidState && nowMs() - lastValidStateAt <= EMPTY_SOURCE_HOLD_MS) {
    return lastValidState;
  }

  if (domExternalState?.lamp === 'red') {
    return rememberState(domExternalState);
  }

  const stopperIndex = latestRealStopperIndex(snapshot.lines);

  if (stopperIndex >= 0) {
    return rememberState({
      lamp: 'red',
      title: 'Ich sehe einen echten Stopper',
      message: 'Ich zeige dir jetzt Repair oder Logs. Folge nur dem naechsten markierten Schritt.',
      action: 'Repair/Logs automatisch pruefen.',
      thinking: false,
      source: 'dom-fallback',
      updatedAt: wallClockMs(),
    });
  }

  if (domExternalState) {
    return rememberState(domExternalState);
  }

  const thinkingIndex = latestSignalIndex(snapshot.lines, THINKING_TOKENS);
  const readyIndex = latestSignalIndex(snapshot.lines, READY_TOKENS);
  const repoIndex = latestSignalIndex(snapshot.lines, REPO_MISSING_TOKENS);
  const generatedIndex = latestSignalIndex(snapshot.lines, GENERATED_FILE_TOKENS);
  const healthyIndex = latestSignalIndex(snapshot.lines, RUNTIME_HEALTHY_TOKENS);
  const missionIndex = latestSignalIndex(snapshot.lines, MISSION_MISSING_TOKENS);
  const telemetryIndex = latestSignalIndex(snapshot.lines, TELEMETRY_TOKENS);
  const patternIndex = latestSignalIndex(snapshot.lines, PATTERN_MEMORY_TOKENS);
  const workflowAcceptedIndex = latestSignalIndex(snapshot.lines, WORKFLOW_ACCEPTED_TOKENS);

  const newestDoneIndex = newestOf(
    readyIndex,
    generatedIndex,
    healthyIndex,
    telemetryIndex,
    patternIndex,
    workflowAcceptedIndex,
  );

  const thinking = thinkingIndex >= 0 && thinkingIndex >= newestDoneIndex;

  if (snapshot.hash !== lastSignalHash) {
    lastSignalHash = snapshot.hash;
    lastSignalChangeAt = nowMs();
  }

  if (thinking && nowMs() - lastSignalChangeAt >= STALLED_AFTER_MS) {
    return rememberState({
      lamp: 'yellow',
      title: 'Ich sehe Aktivitaet ohne Fortschritt',
      message: 'Der Ablauf meldet noch Arbeit, aber es kam laenger kein neues Signal. Oeffne Logs oder Repair, ohne den Auftrag neu zu starten.',
      action: 'Logs/Repair pruefen.',
      thinking: false,
      source: 'dom-fallback',
      updatedAt: wallClockMs(),
    });
  }

  if (thinking) {
    return rememberState({
      lamp: 'green',
      title: 'Ich arbeite gerade',
      message: 'Ich analysiere und pruefe. Du musst jetzt nichts suchen oder klicken.',
      action: 'Bitte warten.',
      thinking: true,
      source: 'dom-fallback',
      updatedAt: wallClockMs(),
    });
  }

  lastSignalChangeAt = nowMs();

  if (readyIndex >= 0) {
    return rememberState({
      lamp: 'green',
      title: hasAny(snapshot.normalized, ['code wiederhergestellt']) ? 'Code wiederhergestellt' : 'Ergebnis ist bereit',
      message: hasAny(snapshot.normalized, ['code wiederhergestellt'])
        ? 'Dein Code wurde wiederhergestellt. Du kannst an derselben Stelle weiterbauen.'
        : 'Die Dateien sind akzeptiert. Pruefe Files und Diff. Danach kann der Draft PR bewusst erstellt werden.',
      action: hasAny(snapshot.normalized, ['code wiederhergestellt']) ? 'Weiterbauen.' : 'Files/Diff pruefen.',
      thinking: false,
      source: 'dom-fallback',
      updatedAt: wallClockMs(),
    });
  }

  if (repoIndex >= 0) {
    return rememberState({
      lamp: 'yellow',
      title: 'Ich brauche zuerst dein Repo',
      message: 'Oeffne das Zahnrad oder tippe Repo. Trage Repository URL und optional privaten Zugang ein. Danach Load Repo.',
      action: 'Repo Setup oeffnen.',
      thinking: false,
      source: 'dom-fallback',
      updatedAt: wallClockMs(),
    });
  }

  if (generatedIndex >= 0 && !hasAny(snapshot.normalized, ['self review'])) {
    return rememberState({
      lamp: 'green',
      title: 'Ich habe Ergebnis-Dateien',
      message: 'Pruefe kurz die erzeugten Dateien. Wenn alles passt, geht es weiter zum Draft PR.',
      action: 'Dateien pruefen.',
      thinking: false,
      source: 'dom-fallback',
      updatedAt: wallClockMs(),
    });
  }

  if (workflowAcceptedIndex >= 0) {
    return rememberState({
      lamp: 'green',
      title: 'Auftrag ist angenommen',
      message: 'Der externe Auftrag wurde erkannt und bleibt im Ablauf. Pruefe Plan, Telemetry oder Logs fuer den naechsten Schritt.',
      action: 'Plan/Logs verfolgen.',
      thinking: false,
      source: 'dom-fallback',
      updatedAt: wallClockMs(),
    });
  }

  if (patternIndex >= 0) {
    return rememberState({
      lamp: 'green',
      title: 'Pattern Memory ist aktiv',
      message: 'Pattern- oder Memory-Signale wurden erkannt. Der Coach haelt diesen Kontext und fuehrt dich im Hauptfluss weiter.',
      action: 'Pattern/Memory pruefen.',
      thinking: false,
      source: 'dom-fallback',
      updatedAt: wallClockMs(),
    });
  }

  if (telemetryIndex >= 0) {
    return rememberState({
      lamp: 'green',
      title: 'Telemetry und Metriken laufen',
      message: 'Runtime-, Coverage- oder Health-Signale wurden erkannt. Oeffne Live Monitor fuer Details.',
      action: 'Live Monitor pruefen.',
      thinking: false,
      source: 'dom-fallback',
      updatedAt: wallClockMs(),
    });
  }

  if (healthyIndex >= 0) {
    return rememberState({
      lamp: 'green',
      title: 'Checks sehen gesund aus',
      message: 'Die Runtime-Pruefung ist gruen. Du kannst zum Repo, Plan oder Dateien zurueck.',
      action: 'Weiter im Hauptfluss.',
      thinking: false,
      source: 'dom-fallback',
      updatedAt: wallClockMs(),
    });
  }

  if (missionIndex >= 0) {
    return rememberState({
      lamp: 'yellow',
      title: 'Ich brauche deinen Wunsch',
      message: 'Schreibe kurz, was ich verbessern soll. Ich plane danach automatisch weiter.',
      action: 'Auftrag schreiben.',
      thinking: false,
      source: 'dom-fallback',
      updatedAt: wallClockMs(),
    });
  }

  return rememberState({
    lamp: 'yellow',
    title: 'Ich warte auf den Start',
    message: 'Beginne mit Repo Setup. Danach fuehre ich dich Schritt fuer Schritt weiter.',
    action: 'Repo oeffnen.',
    thinking: false,
    source: 'dom-fallback',
    updatedAt: wallClockMs(),
  });
}

function readCoachState(): ExternalCoachState {
  const runtimeState = readAssignedRuntimeState();

  if (runtimeState) {
    const accepted = rememberState(runtimeState);
    return sourceLooksStalled(accepted) ? rememberState(stalledStateFrom(accepted)) : accepted;
  }

  return readDomFallbackState();
}

function installStyle(): void {
  const previous = document.getElementById(STYLE_ID);
  if (previous) previous.remove();

  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    #${ROOT_ID} {
      border: 1px solid rgba(34,211,238,.28);
      border-radius: 1.25rem;
      background: linear-gradient(135deg, rgba(2,6,23,.97), rgba(15,23,42,.92));
      color: #e2e8f0;
      overflow: hidden;
      box-shadow: 0 .9rem 2rem rgba(0,0,0,.22);
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
    }

    #${ROOT_ID}.green { border-color: rgba(52,211,153,.38); }
    #${ROOT_ID}.yellow { border-color: rgba(251,191,36,.42); }
    #${ROOT_ID}.red { border-color: rgba(251,113,133,.48); }

    #${ROOT_ID} .coach-head {
      display: flex;
      align-items: center;
      gap: .7rem;
      padding: .85rem .9rem;
    }

    #${ROOT_ID} .coach-bot {
      display: grid;
      place-items: center;
      width: 2.8rem;
      height: 2.8rem;
      border-radius: .9rem;
      border: 1px solid rgba(34,211,238,.38);
      background: radial-gradient(circle at 35% 25%, rgba(103,232,249,.28), rgba(8,47,73,.78));
      font-size: 1.45rem;
      flex: 0 0 auto;
      box-shadow: inset 0 0 1.1rem rgba(34,211,238,.14), 0 0 1rem rgba(34,211,238,.08);
    }

    #${ROOT_ID} .coach-lamp {
      width: .78rem;
      height: .78rem;
      border-radius: 999px;
      box-shadow: 0 0 1rem currentColor;
      flex: 0 0 auto;
    }

    #${ROOT_ID}.green .coach-lamp { color: #34d399; background: #34d399; }
    #${ROOT_ID}.yellow .coach-lamp { color: #fbbf24; background: #fbbf24; }
    #${ROOT_ID}.red .coach-lamp { color: #fb7185; background: #fb7185; }

    #${ROOT_ID} .coach-copy {
      min-width: 0;
      flex: 1;
    }

    #${ROOT_ID} .coach-title {
      font-size: .95rem;
      font-weight: 950;
      color: #f8fafc;
      line-height: 1.1;
    }

    #${ROOT_ID} .coach-action {
      color: #a5b4fc;
      font-size: .75rem;
      font-weight: 850;
      margin-top: .15rem;
    }

    #${ROOT_ID} .coach-body {
      border-top: 1px solid rgba(148,163,184,.14);
      padding: .82rem .9rem .92rem;
    }

    #${ROOT_ID} .coach-message {
      font-size: .82rem;
      line-height: 1.38;
      color: #cbd5e1;
    }

    #${ROOT_ID} .coach-terminal {
      margin-top: .78rem;
      min-height: 9.8rem;
      max-height: 14rem;
      overflow: hidden;
      border: 1px solid rgba(34,211,238,.22);
      border-radius: .95rem;
      background:
        linear-gradient(180deg, rgba(0,0,0,.92), rgba(2,6,23,.96)),
        radial-gradient(circle at 15% 0%, rgba(34,211,238,.16), transparent 35%);
      padding: .78rem;
      color: #67e8f9;
      font: 800 .72rem/1.55 ui-monospace, SFMono-Regular, Menlo, monospace;
      word-break: break-word;
      box-shadow: inset 0 0 1.2rem rgba(34,211,238,.08);
    }

    #${ROOT_ID} .terminal-line {
      display: block;
      white-space: pre-wrap;
      opacity: .94;
    }

    #${ROOT_ID} .terminal-line + .terminal-line {
      margin-top: .22rem;
    }

    #${ROOT_ID} .terminal-face {
      color: #f0abfc;
    }

    #${ROOT_ID} .terminal-dim {
      color: #94a3b8;
    }

    #${ROOT_ID} .prompt {
      color: #a7f3d0;
    }

    #${ROOT_ID}.red .coach-terminal {
      border-color: rgba(251,113,133,.3);
      color: #fecdd3;
    }

    #${ROOT_ID}.yellow .coach-terminal {
      border-color: rgba(251,191,36,.28);
      color: #fde68a;
    }

    #${ROOT_ID} .coach-buttons {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: .42rem;
      margin-top: .72rem;
    }

    #${ROOT_ID} .coach-buttons button {
      border: 1px solid rgba(148,163,184,.25);
      border-radius: .82rem;
      background: rgba(15,23,42,.86);
      color: #e2e8f0;
      padding: .5rem .35rem;
      font-size: .72rem;
      font-weight: 850;
      cursor: pointer;
      touch-action: manipulation;
    }

    #${ROOT_ID} .coach-buttons button:active {
      transform: translateY(1px);
    }

    #${ROOT_ID} .dots::after {
      content: '';
      animation: sovereignDots 1.2s steps(4, end) infinite;
    }

    @keyframes sovereignDots {
      0% { content: ''; }
      25% { content: '.'; }
      50% { content: '..'; }
      75%, 100% { content: '...'; }
    }
  `;

  document.head.appendChild(style);
}

function clickNav(label: string): void {
  const wanted = normalizeText(label);
  const buttons = Array.from(document.querySelectorAll('button')).filter(
    (button) => !button.closest(`#${ROOT_ID}`),
  );

  const exact = buttons.find((button) => {
    const text = normalizeText(button.textContent ?? '');
    const aria = normalizeText(button.getAttribute('aria-label') ?? '');
    return text === wanted || aria === wanted;
  });

  const fallback = buttons.find((button) => {
    const text = normalizeText(button.textContent ?? '');
    const aria = normalizeText(button.getAttribute('aria-label') ?? '');
    return text.includes(wanted) || aria.includes(wanted);
  });

  const target = exact ?? fallback;
  target?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

function appShell(): HTMLElement | null {
  return document.querySelector('#root > div.min-h-screen') ?? document.querySelector('#root > div');
}

function navShell(): Element | null {
  const shell = appShell();
  if (!shell) return null;

  return (
    shell.querySelector('nav') ??
    shell.querySelector('[role="navigation"]') ??
    shell.firstElementChild
  );
}

function coachMode(state: ExternalCoachState): string {
  if (state.thinking) return 'matrix-work';
  if (state.lamp === 'red') return 'repair-log';
  if (state.title.includes('Code')) return 'code-memory';
  if (state.source === 'telemetry' || state.source === 'metrics') return 'telemetry';
  if (state.source === 'pattern-memory' || state.source === 'remote-memory') return 'pattern-memory';
  if (state.source === 'runtime-library' || state.source === 'runtime') return 'runtime';
  if (state.title.includes('Ergebnis')) return 'review-log';

  return 'nocode-plan';
}

function ensureText(parent: Element, selector: string, value: string): void {
  const node = parent.querySelector(selector);
  if (node && node.textContent !== value) node.textContent = value;
}

function terminalLinesForState(state: ExternalCoachState, mode: string): string[] {
  const face = mimuFace(`${state.title}:${state.hash ?? state.tick ?? state.updatedAt}`);
  const tick = state.tick === undefined ? 'tick:auto' : `tick:${state.tick}`;
  const hash = state.hash ? ` hash:${state.hash}` : '';

  if (state.lamp === 'red') {
    return [
      `${mode} $ ${face} stopper erkannt`,
      `repair.scan(${tick}${hash}) => blocked`,
      `reason: ${state.message}`,
      `next: ${state.action}`,
      `${mimuFace('repair')} ich halte den Ablauf sicher an _@=@_`,
    ];
  }

  if (state.thinking) {
    return [
      `${mode} $ ${face} thinking loop aktiv`,
      `read.signals(${tick}${hash}) => ok`,
      `diff.map(workspace) => code flow wird visualisiert`,
      `persist.queue(local-code-memory) => pending`,
      `${mimuFace('type')} schreibe/prüfe leise weiter ^-_-^`,
      `status: ${state.message}`,
    ];
  }

  if (state.title.includes('Code wiederhergestellt')) {
    return [
      `${mode} $ ${face} restore.local_code()`,
      `mirror.read(native-storage) => valid`,
      `normalize.workspace_state() => safe`,
      `redux.dispatch(restoreCodeState) => done`,
      `${mimuFace('restore')} dein Code ist wieder da ○¤○`,
      `next: ${state.action}`,
    ];
  }

  if (state.title.includes('Code gesichert')) {
    return [
      `${mode} $ ${face} save.local_code()`,
      `mirror.write(native-storage) => done`,
      `workspace.snapshot() => stable`,
      `${mimuFace('saved')} alles liegt sicher im Speicher ｡◕‿◕｡`,
      `next: ${state.action}`,
    ];
  }

  return [
    `${mode} $ ${face} monitor.update()`,
    `source:${state.source ?? 'dom'} ${tick}${hash}`,
    `lamp:${state.lamp} thinking:${String(state.thinking)}`,
    `message: ${state.message}`,
    `next: ${state.action}`,
  ];
}

function renderTerminal(root: HTMLElement, lines: string[]): void {
  const terminal = root.querySelector('.coach-terminal');
  if (!terminal) return;

  terminal.replaceChildren();

  for (const line of lines.slice(0, MAX_TERMINAL_LINES)) {
    const row = document.createElement('span');
    row.className = 'terminal-line';

    const face = MIMU_SMILEYS.find((candidate) => line.includes(candidate));
    if (face) {
      const [before, after] = line.split(face);
      row.append(document.createTextNode(before));

      const faceNode = document.createElement('span');
      faceNode.className = 'terminal-face';
      faceNode.textContent = face;
      row.append(faceNode, document.createTextNode(after ?? ''));
    } else if (line.startsWith('source:') || line.startsWith('lamp:')) {
      row.className = 'terminal-line terminal-dim';
      row.textContent = line;
    } else {
      row.textContent = line;
    }

    terminal.appendChild(row);
  }
}

function buildCoachShell(root: HTMLElement): void {
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
  copy.className = 'coach-copy';

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

  const terminalMessage = document.createElement('span');
  terminalMessage.className = 'terminal-message';
  terminalMessage.textContent = 'booting code monitor...';
  terminal.appendChild(terminalMessage);

  const buttons = document.createElement('div');
  buttons.className = 'coach-buttons';

  const navButtons: Array<[string, string]> = [
    ['Repo', 'Repo'],
    ['Planen', 'Builder'],
    ['Dateien', 'Files'],
    ['Logs', 'Live Monitor'],
  ];

  for (const [label, target] of navButtons) {
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

function ensureCoachRoot(nav: Element): HTMLElement {
  let root = document.getElementById(ROOT_ID);

  if (!root) {
    root = document.createElement('section');
    root.id = ROOT_ID;
    buildCoachShell(root);
  }

  if (!root.querySelector('.coach-title') || !root.querySelector('.coach-buttons')) {
    buildCoachShell(root);
  }

  if (root.previousElementSibling !== nav) {
    nav.insertAdjacentElement('afterend', root);
  }

  return root;
}

function renderCoach(): void {
  if (typeof document === 'undefined') return;

  installStyle();

  const nav = navShell();
  if (!appShell() || !nav) return;

  const root = ensureCoachRoot(nav);
  const state = readCoachState();
  const mode = coachMode(state);
  const terminalLines = terminalLinesForState(state, mode);
  const signature = JSON.stringify({
    lamp: state.lamp,
    title: state.title,
    message: state.message,
    action: state.action,
    thinking: state.thinking,
    source: state.source,
    tick: state.tick,
    hash: state.hash,
    mode,
    terminalLines,
  });

  if (root.dataset.signature === signature) return;

  root.dataset.signature = signature;
  root.className = state.lamp;

  ensureText(root, '.coach-title', `Sovereign Bot · ${state.title}`);
  ensureText(root, '.coach-action', state.action);
  ensureText(root, '.coach-message', state.message);
  renderTerminal(root, terminalLines);

  root.querySelector('.coach-title')?.classList.toggle('dots', state.thinking);
  root.querySelector('.terminal-message')?.classList.toggle('dots', state.thinking);
}

function scheduleRender(): void {
  if (typeof window === 'undefined') return;

  const win = window as CoachWindow;

  if (win.__sovereignMobileCoachRenderTimer) {
    window.clearTimeout(win.__sovereignMobileCoachRenderTimer);
  }

  win.__sovereignMobileCoachRenderTimer = window.setTimeout(() => {
    win.__sovereignMobileCoachRenderTimer = undefined;
    renderCoach();
  }, MUTATION_RENDER_DELAY_MS);
}

function mutationBelongsOnlyToCoach(records: MutationRecord[]): boolean {
  return records.length > 0 && records.every((record) => isInsideCoach(record.target));
}

function eventSourceFromName(eventName: string): CoachSource {
  if (eventName.includes('workflow')) return 'workflow';
  if (eventName.includes('repair')) return 'repair';
  if (eventName.includes('telemetry')) return 'telemetry';
  if (eventName.includes('metrics')) return 'metrics';
  if (eventName.includes('pattern-memory')) return 'pattern-memory';
  if (eventName.includes('remote-memory')) return 'remote-memory';
  if (eventName.includes('store-runtime')) return 'runtime';
  if (eventName.includes('runtime')) return 'runtime-library';

  return 'runtime-library';
}

function installCoachEventBridge(): void {
  const win = window as CoachWindow;

  if (win.__sovereignMobileCoachEventInstalled) return;
  win.__sovereignMobileCoachEventInstalled = true;

  for (const eventName of COACH_EVENTS) {
    window.addEventListener(eventName, (event) => {
      const detail = event instanceof CustomEvent ? event.detail : null;
      acceptExternalCoachState(detail, eventSourceFromName(eventName));
    });
  }
}

export function publishMobileOperatorCoachState(state: ExternalCoachState): void {
  if (typeof window === 'undefined') return;

  acceptExternalCoachState(
    {
      ...state,
      source: state.source ?? 'runtime-library',
      updatedAt: state.updatedAt ?? wallClockMs(),
    },
    state.source ?? 'runtime-library',
  );
}

export function installMobileOperatorCoach(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  const win = window as CoachWindow;

  installCoachEventBridge();

  const stored = readStoredState();
  if (stored) rememberState(stored);

  window.setTimeout(renderCoach, INITIAL_RENDER_DELAY_MS);

  if (!win.__sovereignMobileCoachInterval) {
    win.__sovereignMobileCoachInterval = window.setInterval(renderCoach, RENDER_INTERVAL_MS);
  }

  if (!win.__sovereignMobileCoachObserver && document.body) {
    win.__sovereignMobileCoachObserver = new MutationObserver((records) => {
      if (mutationBelongsOnlyToCoach(records)) return;
      scheduleRender();
    });

    win.__sovereignMobileCoachObserver.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: SIGNAL_ATTRIBUTES,
    });
  }
}
