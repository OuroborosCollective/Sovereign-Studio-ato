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

function lampWeight(lamp: QuietInspectorLamp): number {
  if (lamp === 'red') return 3;
  if (lamp === 'yellow') return 2;
  return 1;
}

function sanitizeText(value: string, max = 120): string {
  return value.replace(/\s+/g, ' ').trim().slice(0, max);
}

function normalizeSignal(signal: QuietInspectorSignal): QuietInspectorSignal | null {
  const id = sanitizeText(signal.id, 80);
  const source = sanitizeText(signal.source, 40);
  const message = sanitizeText(signal.message, 140);
  if (!id || !source || !message || signal.visible === false) return null;
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
  if (signals.length === 0) return 'Keine neuen Inspector-Hinweise.';
  const red = signals.filter((signal) => signal.lamp === 'red').length;
  const yellow = signals.filter((signal) => signal.lamp === 'yellow').length;
  const green = signals.filter((signal) => signal.lamp === 'green').length;
  const parts = [
    red > 0 ? `${red} Blocker` : '',
    yellow > 0 ? `${yellow} Hinweise` : '',
    green > 0 ? `${green} OK` : '',
  ].filter(Boolean);
  return `Inspector: ${parts.join(' · ')}`;
}

export function mergeQuietInspectorSignals(signals: QuietInspectorSignal[]): QuietInspectorPolicyResult {
  const normalized = signals
    .map(normalizeSignal)
    .filter((signal): signal is QuietInspectorSignal => Boolean(signal))
    .sort((a, b) => {
      const diff = lampWeight(b.lamp) - lampWeight(a.lamp);
      if (diff !== 0) return diff;

      // Tie-break: PAL signal always wins for the top position if weight is equal
      if (a.id === 'pal' && b.id !== 'pal') return -1;
      if (b.id === 'pal' && a.id !== 'pal') return 1;

      return (b.updatedAt ?? 0) - (a.updatedAt ?? 0) || a.id.localeCompare(b.id);
    })
    .slice(0, MAX_SIGNALS);

  const topLamp = normalized[0]?.lamp ?? 'green';

  return {
    hasVisibleSignals: normalized.length > 0,
    topLamp,
    summary: summaryFor(normalized),
    signals: normalized,
  };
}
