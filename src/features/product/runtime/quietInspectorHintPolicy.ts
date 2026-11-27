export type QuietInspectorLamp = 'green' | 'yellow' | 'red';
export type QuietInspectorTarget = 'repo' | 'files' | 'diff' | 'workflow' | 'repair' | 'remote' | 'monitor' | 'telemetry' | 'health' | 'runtime' | 'coverage' | 'findings' | 'memory';

export interface QuietInspectorSignal {
  readonly id: string;
  readonly source: string;
  readonly lamp: QuietInspectorLamp;
  readonly message: string;
  readonly targetTab: QuietInspectorTarget;
  readonly visible?: boolean;
  readonly updatedAt?: number;
}

export interface QuietInspectorPolicyResult {
  readonly hasVisibleSignals: boolean;
  readonly topLamp: QuietInspectorLamp;
  readonly summary: string;
  readonly signals: QuietInspectorSignal[];
}

const MAX_SIGNALS = 5;

// ⚡ Bolt: Hoist static whitespace RegExp to module scope to avoid re-compilation per text sanitization
const WHITESPACE_REGEX = /\s+/g;

function lampWeight(lamp: QuietInspectorLamp): number {
  if (lamp === 'red') return 3;
  if (lamp === 'yellow') return 2;
  return 1;
}

function signalPriority(signal: QuietInspectorSignal): number {
  if (signal.id === 'pal') return 100;
  if (signal.id === 'brownfield') return 80;
  if (signal.id === 'remote-memory') return 60;
  return 0;
}

function sanitizeText(value: string, max = 120): string {
  // ⚡ Bolt: Single-pass replace and trim with hoisted regex, avoiding redundant regex test passes
  const replaced = value.replace(WHITESPACE_REGEX, ' ').trim();
  return replaced.length > max ? replaced.slice(0, max) : replaced;
}

function normalizeSignal(signal: QuietInspectorSignal): QuietInspectorSignal | null {
  // ⚡ Bolt: Fast return if signal is explicitly hidden to skip unnecessary text sanitization
  if (signal.visible === false) return null;
  const id = sanitizeText(signal.id, 80);
  if (!id) return null;
  const source = sanitizeText(signal.source, 40);
  if (!source) return null;
  const message = sanitizeText(signal.message, 140);
  if (!message) return null;
  return {
    id,
    source,
    lamp: signal.lamp,
    message,
    targetTab: signal.targetTab,
    visible: true,
    updatedAt: typeof signal.updatedAt === 'number' && Number.isFinite(signal.updatedAt) ? Math.floor(signal.updatedAt) : 0,
  };
}

function summaryFor(signals: QuietInspectorSignal[]): string {
  const len = signals.length;
  if (len === 0) return 'Keine neuen Inspector-Hinweise.';
  // ⚡ Bolt: Single-pass indexed loop counting lamp statuses replaces 3 separate sequential .filter() passes
  let red = 0;
  let yellow = 0;
  let green = 0;
  for (let i = 0; i < len; i++) {
    const lamp = signals[i].lamp;
    if (lamp === 'red') red++;
    else if (lamp === 'yellow') yellow++;
    else if (lamp === 'green') green++;
  }
  const parts: string[] = [];
  if (red > 0) parts.push(`${red} Blocker`);
  if (yellow > 0) parts.push(`${yellow} Hinweise`);
  if (green > 0) parts.push(`${green} OK`);
  return `Inspector: ${parts.join(' · ')}`;
}

export function mergeQuietInspectorSignals(signals: QuietInspectorSignal[]): QuietInspectorPolicyResult {
  // ⚡ Bolt: Single-pass accumulation eliminates intermediate array allocations from chained .map().filter()
  const normalized: QuietInspectorSignal[] = [];
  for (let i = 0; i < signals.length; i++) {
    const norm = normalizeSignal(signals[i]);
    if (norm !== null) {
      normalized.push(norm);
    }
  }

  normalized.sort((a, b) =>
    lampWeight(b.lamp) - lampWeight(a.lamp) ||
    signalPriority(b) - signalPriority(a) ||
    (b.updatedAt ?? 0) - (a.updatedAt ?? 0) ||
    a.id.localeCompare(b.id)
  );

  // ⚡ Bolt: Only slice when length exceeds MAX_SIGNALS to avoid redundant shallow array allocations
  const finalSignals = normalized.length > MAX_SIGNALS ? normalized.slice(0, MAX_SIGNALS) : normalized;
  const topLamp = finalSignals[0]?.lamp ?? 'green';

  return {
    hasVisibleSignals: finalSignals.length > 0,
    topLamp,
    summary: summaryFor(finalSignals),
    signals: finalSignals,
  };
}
