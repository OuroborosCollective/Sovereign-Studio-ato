export type ReleaseGuideLamp = 'green' | 'yellow' | 'red';

export type ReleaseGuideTab =
  | 'repo'
  | 'builder'
  | 'files'
  | 'diff'
  | 'workflow'
  | 'repair'
  | 'remote'
  | 'memory'
  | 'telemetry'
  | 'monitor'
  | 'readiness'
  | 'integrity'
  | 'findings'
  | 'health'
  | 'runtime'
  | 'coverage';

export interface ReleaseGuideInput {
  lamp: ReleaseGuideLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
  source: string;
}

export interface ReleaseGuideState {
  progress: number;
  progressLabel: string;
  helperTitle: string;
  helperMessage: string;
  mood: string;
  targetTab: ReleaseGuideTab | null;
  previousTab: ReleaseGuideTab | null;
  nextLabel: string;
  nextEnabled: boolean;
  confirmLabel: string;
  waitingReason: string;
}

const TAB_PATTERNS: Array<{ tab: ReleaseGuideTab; tokens: string[] }> = [
  { tab: 'workflow', tokens: ['workflow', 'ci', 'checks', 'draft pr', 'pull request', 'diff', 'files prüfen', 'source snapshots'] },
  { tab: 'repair', tokens: ['repair', 'reparieren', 'fehlerlog'] },
  { tab: 'builder', tokens: ['builder', 'auftrag', 'ideenfabrik', 'mission'] },
  { tab: 'repo', tokens: ['repo', 'repository'] },
  { tab: 'remote', tokens: ['remote memory'] },
  { tab: 'memory', tokens: ['pattern memory'] },
  { tab: 'telemetry', tokens: ['telemetry', 'telemetrie'] },
  { tab: 'monitor', tokens: ['monitor', 'log'] },
  { tab: 'readiness', tokens: ['readiness'] },
  { tab: 'integrity', tokens: ['integrity'] },
  { tab: 'findings', tokens: ['findings'] },
  { tab: 'health', tokens: ['health'] },
  { tab: 'runtime', tokens: ['runtime'] },
  { tab: 'coverage', tokens: ['coverage'] },
];

const PREVIOUS_TAB: Partial<Record<ReleaseGuideTab, ReleaseGuideTab>> = {
  repo: 'monitor',
  builder: 'repo',
  files: 'builder',
  diff: 'workflow',
  workflow: 'builder',
  repair: 'workflow',
  remote: 'repo',
  memory: 'remote',
  telemetry: 'memory',
  monitor: 'repo',
  readiness: 'repo',
  integrity: 'readiness',
  findings: 'integrity',
  health: 'findings',
  runtime: 'health',
  coverage: 'runtime',
};

function normalize(value: string): string {
  return value.toLowerCase().replace(/\s+/g, ' ').trim();
}

function textOf(input: ReleaseGuideInput): string {
  return normalize(`${input.title} ${input.message} ${input.action} ${input.source}`);
}

function actionTextOf(input: ReleaseGuideInput): string {
  return normalize(input.action);
}

function hasAny(source: string, tokens: string[]): boolean {
  return tokens.some((token) => source.includes(token));
}

function step5(value: number): number {
  const safe = Math.max(0, Math.min(100, value));
  return Math.round(safe / 5) * 5;
}

function inferTabFromText(source: string): ReleaseGuideTab | null {
  for (const entry of TAB_PATTERNS) {
    if (hasAny(source, entry.tokens)) return entry.tab;
  }
  return null;
}

export function inferReleaseGuideTab(input: ReleaseGuideInput): ReleaseGuideTab | null {
  return inferTabFromText(actionTextOf(input)) ?? inferTabFromText(textOf(input));
}

export function deriveReleaseGuideProgress(input: ReleaseGuideInput): number {
  const source = textOf(input);
  const action = actionTextOf(input);

  if (input.lamp === 'red') return step5(10);
  if (hasAny(action, ['workflow', 'ci', 'checks', 'draft pr', 'pull request'])) return step5(85);
  if (hasAny(action, ['repair', 'reparieren', 'fehlerlog'])) return step5(90);
  if (hasAny(source, ['repo fehlt', 'repository laden', 'load repo'])) return step5(10);
  if (hasAny(source, ['repo geladen', 'repository snapshot', 'repo snapshot ready'])) return step5(25);
  if (hasAny(source, ['auftrag analysieren', 'ideenfabrik', 'builder'])) return step5(35);
  if (hasAny(source, ['auftrag starten', 'package-build', 'building'])) return step5(55);
  if (hasAny(source, ['package bereit', 'package wurde erstellt'])) return step5(80);
  if (hasAny(source, ['diff', 'files prüfen', 'generated file', 'load source snapshots'])) return step5(80);
  if (hasAny(source, ['workflow', 'ci'])) return step5(85);
  if (hasAny(source, ['draft pr', 'pull request'])) return step5(95);
  if (hasAny(source, ['release', 'completed', 'success', 'fertig'])) return step5(100);
  if (input.thinking) return step5(45);
  return input.lamp === 'green' ? step5(60) : step5(20);
}

function progressLabel(progress: number): string {
  if (progress >= 100) return '100% · abgeschlossen';
  if (progress >= 95) return `${progress}% · Draft/Release prüfen`;
  if (progress >= 85) return `${progress}% · Workflow prüfen`;
  if (progress >= 80) return `${progress}% · interne Prüfung abgeschlossen`;
  if (progress >= 55) return `${progress}% · Paket wird vorbereitet`;
  if (progress >= 35) return `${progress}% · Auftrag wird analysiert`;
  if (progress >= 25) return `${progress}% · Repository bereit`;
  return `${progress}% · Startphase`;
}

function helperMessage(input: ReleaseGuideInput, targetTab: ReleaseGuideTab | null, progress: number): string {
  if (input.thinking) return 'Ich arbeite gerade und halte dich sichtbar auf dem Laufenden.';
  if (targetTab === 'workflow') return 'Ich überspringe die sichtbare Diff-Schleife und führe den nächsten GitHub-/Workflow-Schritt automatisch weiter.';
  if (targetTab) return `Nächster interner Bereich: ${targetTab}. Ich steuere das automatisch.`;
  if (progress >= 100) return 'Fertig. Ergebnis liegt vor.';
  return 'Ich warte auf den nächsten klaren Systemschritt, damit du nicht raten musst.';
}

export function deriveReleaseGuideState(input: ReleaseGuideInput): ReleaseGuideState {
  const targetTab = inferReleaseGuideTab(input);
  const progress = deriveReleaseGuideProgress(input);
  const nextEnabled = Boolean(targetTab) && !input.thinking;

  return {
    progress,
    progressLabel: progressLabel(progress),
    helperTitle: input.thinking ? 'Sovereign Helper arbeitet' : 'Sovereign Helper begleitet dich',
    helperMessage: helperMessage(input, targetTab, progress),
    mood: input.thinking ? '🤖💭' : input.lamp === 'green' ? '😊✨' : input.lamp === 'yellow' ? '🙂🔎' : '🛟⚠️',
    targetTab,
    previousTab: targetTab ? PREVIOUS_TAB[targetTab] ?? 'repo' : 'repo',
    nextLabel: targetTab ? `Weiter zu ${targetTab}` : 'Weiter noch gesperrt',
    nextEnabled,
    confirmLabel: progress >= 100 ? 'Abschluss bestätigen' : 'Schritt bestätigen',
    waitingReason: nextEnabled ? '' : 'Noch kein sicherer nächster Schritt verfügbar.',
  };
}

export function releaseGuideTabTestId(tab: ReleaseGuideTab): string {
  return `tabbar__${tab}`;
}
