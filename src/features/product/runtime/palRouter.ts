export type PalModelTier = 'fast' | 'balanced' | 'power';
export type PalIntent = 'answer' | 'repo-scan' | 'code-change' | 'repair' | 'draft-pr' | 'unknown';
export type PalSignal = 'green' | 'yellow' | 'red';
export type PalAutomationMode = 'manual' | 'auto-review' | 'full-auto-draft-pr';

export interface PalRouterInput {
  mission: string;
  repoReady: boolean;
  repoFileCount: number;
  blockers?: string[];
  automationMode?: PalAutomationMode;
  hasDiffPreview?: boolean;
  hasDraftCommit?: boolean;
}

export interface PalRouterDecision {
  intent: PalIntent;
  tier: PalModelTier;
  signal: PalSignal;
  blocked: boolean;
  reason: string;
  recommendedAction: string;
  facts: string[];
}

const REPAIR_RE = /\b(error|fehler|fix|repair|reparier|kaputt|failed|failure|red gate|workflow|ci|build|test|typecheck|lint)\b/i;
const CODE_CHANGE_RE = /\b(add|build|implement|integrier|erstelle|füge|fuege|ändere|aendere|refactor|umbau|feature|patch|commit|push)\b/i;
const DRAFT_PR_RE = /\b(draft\s*pr|pull request|pr erstellen|publish|veröffentlichen|veroeffentlichen)\b/i;
const REPO_SCAN_RE = /\b(repo|repository|analyse|analysiere|scan|hotspot|brownfield|dateibaum|architektur)\b/i;
const ANSWER_RE = /\b(erklär|erklaer|warum|was ist|wie geht|bewerte|meinung|zusammenfass|summary)\b/i;

function cleanMission(mission: unknown): string {
  return typeof mission === 'string' ? mission.trim() : '';
}

function safeFileCount(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
}

function safeBlockers(blockers: unknown): string[] {
  if (!Array.isArray(blockers)) return [];
  return blockers
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    .map((item) => item.trim())
    .slice(0, 5);
}

function classifyIntent(mission: string, automationMode: PalAutomationMode): PalIntent {
  if (DRAFT_PR_RE.test(mission) || automationMode === 'full-auto-draft-pr') return 'draft-pr';
  if (REPAIR_RE.test(mission)) return 'repair';
  if (CODE_CHANGE_RE.test(mission)) return 'code-change';
  if (REPO_SCAN_RE.test(mission) || automationMode === 'auto-review') return 'repo-scan';
  if (ANSWER_RE.test(mission)) return 'answer';
  return mission ? 'unknown' : 'answer';
}

function intentNeedsRepo(intent: PalIntent): boolean {
  return intent === 'repo-scan' || intent === 'code-change' || intent === 'repair' || intent === 'draft-pr';
}

function tierFor(intent: PalIntent, fileCount: number, automationMode: PalAutomationMode): PalModelTier {
  if (intent === 'answer' && fileCount < 200) return 'fast';
  if (intent === 'draft-pr') return 'power';
  if (intent === 'repair') return fileCount > 400 || automationMode !== 'manual' ? 'power' : 'balanced';
  if (intent === 'code-change') return fileCount > 800 ? 'power' : 'balanced';
  if (intent === 'repo-scan') return fileCount > 1200 ? 'power' : fileCount > 250 ? 'balanced' : 'fast';
  return fileCount > 500 ? 'balanced' : 'fast';
}

function factList(input: {
  intent: PalIntent;
  fileCount: number;
  repoReady: boolean;
  automationMode: PalAutomationMode;
  blockers: string[];
}): string[] {
  const facts = [
    `intent=${input.intent}`,
    `repo=${input.repoReady ? 'ready' : 'not-ready'}`,
    `files=${input.fileCount}`,
    `mode=${input.automationMode}`,
  ];
  if (input.blockers.length > 0) facts.push(`blockers=${input.blockers.length}`);
  return facts;
}

export function decidePalRoute(input: PalRouterInput): PalRouterDecision {
  const mission = cleanMission(input.mission);
  const repoFileCount = safeFileCount(input.repoFileCount);
  const blockers = safeBlockers(input.blockers);
  const automationMode = input.automationMode ?? 'manual';
  const intent = classifyIntent(mission, automationMode);
  const repoRequired = intentNeedsRepo(intent);
  const repoReady = input.repoReady === true && repoFileCount > 0;
  const tier = tierFor(intent, repoFileCount, automationMode);
  const facts = factList({ intent, fileCount: repoFileCount, repoReady, automationMode, blockers });

  if (blockers.length > 0) {
    return {
      intent,
      tier: 'fast',
      signal: 'red',
      blocked: true,
      reason: `PAL blockiert Routing wegen ${blockers.length} aktivem Stopper.`,
      recommendedAction: blockers[0],
      facts,
    };
  }

  if (repoRequired && !repoReady) {
    return {
      intent,
      tier: 'fast',
      signal: 'yellow',
      blocked: true,
      reason: 'PAL braucht zuerst einen echten Repo-Snapshot für diese Aufgabe.',
      recommendedAction: 'Repo laden oder gültigen Repo-Snapshot wiederherstellen.',
      facts,
    };
  }

  if (intent === 'answer') {
    return {
      intent,
      tier,
      signal: 'green',
      blocked: false,
      reason: 'PAL wählt Fast-Tier, weil keine Repo-Änderung nötig ist.',
      recommendedAction: 'Direkt beantworten.',
      facts,
    };
  }

  return {
    intent,
    tier,
    signal: tier === 'power' ? 'yellow' : 'green',
    blocked: false,
    reason: `PAL wählt ${tier} für ${intent} auf ${repoFileCount} Repo-Dateien.`,
    recommendedAction: intent === 'draft-pr'
      ? 'Vor Draft PR Generated-File-Review und Diff prüfen.'
      : 'Mit validiertem Runtime-Kontext fortfahren.',
    facts,
  };
}
