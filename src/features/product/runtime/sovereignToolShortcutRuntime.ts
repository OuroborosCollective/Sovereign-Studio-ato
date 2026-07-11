/**
 * Runtime truth for the compact Sovereign tool launcher.
 *
 * The UI may display these decisions, but it must not infer availability itself.
 * Every shortcut resolves to an explicit gate, reason and next action.
 */

import {
  isSovereignToolInspectionEvidenceFresh,
  type SovereignToolInspectionEvidenceMap,
} from './sovereignToolInspectionRuntime';
import type { SovereignExecutorIntentKind } from './sovereignExecutorRuntime';

export type SovereignToolShortcutId =
  | 'repo'
  | 'files'
  | 'diff'
  | 'github_access'
  | 'executor'
  | 'runtime_logs'
  | 'health'
  | 'memory'
  | 'coverage'
  | 'settings';

export type SovereignToolShortcutState =
  | 'ready'
  | 'setup_required'
  | 'evidence_missing'
  | 'inspection';

export type SovereignToolShortcutRoute =
  | 'repo'
  | 'files'
  | 'diff'
  | 'github-access'
  | 'agent-job'
  | 'runtime-logs'
  | 'health'
  | 'memory'
  | 'coverage'
  | 'settings';

export interface SovereignToolShortcutContext {
  readonly repoReady: boolean;
  readonly repoFileCount: number;
  readonly hasDiffEvidence: boolean;
  readonly githubAccessState: 'missing' | 'requested' | 'validating' | 'ready' | 'invalid' | 'failed';
  readonly executorAvailable: boolean;
  readonly hasExecutorMission: boolean;
  readonly executorIntent: SovereignExecutorIntentKind;
  readonly runtimeLogCount: number;
  readonly inspectionEvidence?: SovereignToolInspectionEvidenceMap;
}

export interface SovereignToolShortcutDefinition {
  readonly id: SovereignToolShortcutId;
  readonly label: string;
  readonly icon: string;
  readonly route: SovereignToolShortcutRoute;
}

export interface SovereignToolShortcutGate extends SovereignToolShortcutDefinition {
  readonly canOpen: boolean;
  readonly state: SovereignToolShortcutState;
  readonly statusLabel: string;
  readonly reason: string;
  readonly nextAction: string;
}

export const SOVEREIGN_TOOL_SHORTCUTS: readonly SovereignToolShortcutDefinition[] = [
  { id: 'repo', label: 'Repo', icon: '⎇', route: 'repo' },
  { id: 'files', label: 'Files', icon: '📄', route: 'files' },
  { id: 'diff', label: 'Diff', icon: '±', route: 'diff' },
  { id: 'github_access', label: 'GitHub Access', icon: '🔑', route: 'github-access' },
  { id: 'executor', label: 'Executor', icon: '▶', route: 'agent-job' },
  { id: 'runtime_logs', label: 'Runtime Logs', icon: '≡', route: 'runtime-logs' },
  { id: 'health', label: 'Health', icon: '♥', route: 'health' },
  { id: 'memory', label: 'Memory', icon: '◈', route: 'memory' },
  { id: 'coverage', label: 'Coverage', icon: '✦', route: 'coverage' },
  { id: 'settings', label: 'Settings', icon: '⚙', route: 'settings' },
] as const;

function normalizeCount(value: number): number {
  return Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
}

function gate(
  definition: SovereignToolShortcutDefinition,
  values: Omit<SovereignToolShortcutGate, keyof SovereignToolShortcutDefinition>,
): SovereignToolShortcutGate {
  return { ...definition, ...values };
}

function inspectionGate(
  definition: SovereignToolShortcutDefinition,
  context: SovereignToolShortcutContext,
  fallback: Omit<SovereignToolShortcutGate, keyof SovereignToolShortcutDefinition>,
): SovereignToolShortcutGate {
  if (
    definition.id !== 'health'
    && definition.id !== 'memory'
    && definition.id !== 'coverage'
    && definition.id !== 'settings'
  ) {
    return gate(definition, fallback);
  }

  const evidence = context.inspectionEvidence?.[definition.id];
  if (!evidence) return gate(definition, fallback);
  if (!isSovereignToolInspectionEvidenceFresh(evidence)) {
    return gate(definition, {
      canOpen: true,
      state: 'inspection',
      statusLabel: 'Erneut prüfen',
      reason: 'Die gespeicherte Tool-Evidence ist veraltet und wird nicht mehr als aktueller Status verwendet.',
      nextAction: 'Tool öffnen und Runtime-Prüfung erneut ausführen.',
    });
  }

  const state: SovereignToolShortcutState = evidence.outcome === 'ready'
    ? 'ready'
    : evidence.outcome === 'checking'
      ? 'inspection'
      : 'evidence_missing';

  return gate(definition, {
    canOpen: true,
    state,
    statusLabel: evidence.statusLabel,
    reason: evidence.reason,
    nextAction: evidence.nextAction,
  });
}

export function evaluateSovereignToolShortcutGate(
  definition: SovereignToolShortcutDefinition,
  context: SovereignToolShortcutContext,
): SovereignToolShortcutGate {
  const fileCount = normalizeCount(context.repoFileCount);

  switch (definition.id) {
    case 'repo':
      return gate(definition, context.repoReady
        ? { canOpen: true, state: 'ready', statusLabel: 'Repo geladen', reason: 'Ein bestätigter Repo-Snapshot ist vorhanden.', nextAction: 'Repo-Explorer öffnen.' }
        : { canOpen: true, state: 'setup_required', statusLabel: 'Repo laden', reason: 'Noch kein bestätigter Repo-Snapshot vorhanden.', nextAction: 'Repo-Setup öffnen.' });
    case 'files':
      if (!context.repoReady) return gate(definition, { canOpen: false, state: 'setup_required', statusLabel: 'Repo fehlt', reason: 'Files brauchen zuerst einen bestätigten Repo-Snapshot.', nextAction: 'Repo laden.' });
      if (fileCount === 0) return gate(definition, { canOpen: false, state: 'evidence_missing', statusLabel: 'Dateiliste fehlt', reason: 'Der Repo-State enthält noch keine bestätigte Dateiliste.', nextAction: 'Repo-Snapshot erneut laden.' });
      return gate(definition, { canOpen: true, state: 'ready', statusLabel: `${fileCount} Dateien`, reason: 'Bestätigte Datei-Evidence ist vorhanden.', nextAction: 'Datei-Explorer öffnen.' });
    case 'diff':
      return gate(definition, context.hasDiffEvidence
        ? { canOpen: true, state: 'ready', statusLabel: 'Diff vorhanden', reason: 'Changed-Files-, Patch- oder Diff-Evidence ist vorhanden.', nextAction: 'Diff-Prüfung öffnen.' }
        : { canOpen: false, state: 'evidence_missing', statusLabel: 'Kein Diff', reason: 'Es liegt noch keine bestätigte Diff- oder Changed-Files-Evidence vor.', nextAction: 'Zuerst Patch oder Diff erzeugen.' });
    case 'github_access':
      if (context.githubAccessState === 'ready') return gate(definition, { canOpen: true, state: 'ready', statusLabel: 'Validiert', reason: 'GitHub-Zugang wurde von der Runtime validiert.', nextAction: 'Zugangsstatus anzeigen.' });
      if (context.githubAccessState === 'validating' || context.githubAccessState === 'requested') return gate(definition, { canOpen: true, state: 'setup_required', statusLabel: 'Prüfung läuft', reason: 'GitHub-Zugang ist noch nicht validiert.', nextAction: 'Validierungsstatus anzeigen.' });
      return gate(definition, { canOpen: true, state: 'setup_required', statusLabel: 'Zugang fehlt', reason: 'Kein validierter GitHub-Zugang vorhanden.', nextAction: 'Sicheres Zugangsfeld öffnen.' });
    case 'executor':
      if (!context.repoReady) return gate(definition, { canOpen: false, state: 'setup_required', statusLabel: 'Repo fehlt', reason: 'Der Executor braucht einen vollständigen Repo-Snapshot.', nextAction: 'Repo laden.' });
      if (!context.hasExecutorMission || (context.executorIntent !== 'code_execution' && context.executorIntent !== 'draft_pr')) return gate(definition, { canOpen: false, state: 'evidence_missing', statusLabel: 'Ausführungsauftrag fehlt', reason: 'Ein Executor-Start braucht einen bestätigten Code- oder Draft-PR-Auftrag.', nextAction: 'Klaren Ausführungsauftrag in den Chat eingeben.' });
      if (context.githubAccessState !== 'ready') return gate(definition, { canOpen: false, state: 'setup_required', statusLabel: context.githubAccessState === 'requested' || context.githubAccessState === 'validating' ? 'Zugang wird geprüft' : 'GitHub-Zugang fehlt', reason: 'Der Executor-Schreibpfad braucht validierten GitHub-Zugang.', nextAction: 'GitHub-Zugang sicher validieren.' });
      if (!context.executorAvailable) return gate(definition, { canOpen: false, state: 'setup_required', statusLabel: 'Nicht verbunden', reason: 'Die Agent-Runtime oder ihr Start-Callback ist nicht verfügbar.', nextAction: 'Agent-Runtime verbinden.' });
      return gate(definition, { canOpen: true, state: 'ready', statusLabel: 'Start möglich', reason: 'Repo, GitHub-Zugang, Agent-Runtime und Ausführungsauftrag sind bestätigt.', nextAction: 'Agent-Job anfragen.' });
    case 'runtime_logs':
      return gate(definition, { canOpen: true, state: context.runtimeLogCount > 0 ? 'ready' : 'inspection', statusLabel: context.runtimeLogCount > 0 ? `${normalizeCount(context.runtimeLogCount)} Events` : 'Noch leer', reason: context.runtimeLogCount > 0 ? 'Gespeicherte Runtime-Events sind vorhanden.' : 'Die Log-Fläche darf geöffnet werden, behauptet aber noch keine Events.', nextAction: 'Runtime-Logs öffnen.' });
    case 'health':
      return inspectionGate(definition, context, { canOpen: true, state: 'inspection', statusLabel: 'Prüft beim Öffnen', reason: 'Health wird erst im Tool durch echte Runtime-Checks bestimmt.', nextAction: 'Health-Checks öffnen.' });
    case 'memory':
      return inspectionGate(definition, context, { canOpen: true, state: 'inspection', statusLabel: 'Prüft beim Öffnen', reason: 'Memory-Verfügbarkeit wird erst im Tool aus Runtime-Evidence gelesen.', nextAction: 'Memory-Inspektion öffnen.' });
    case 'coverage':
      return inspectionGate(definition, context, { canOpen: true, state: 'inspection', statusLabel: 'Prüft beim Öffnen', reason: 'Coverage wird erst aus vorhandenen Reports oder Runtime-Checks bestimmt.', nextAction: 'Coverage-Prüfung öffnen.' });
    case 'settings':
      return inspectionGate(definition, context, { canOpen: true, state: 'inspection', statusLabel: 'Session-Einstellungen', reason: 'Settings öffnen nur die Session-Konfiguration und behaupten keinen Runtime-Erfolg.', nextAction: 'Settings öffnen.' });
  }
}

export function deriveSovereignToolShortcutGates(context: SovereignToolShortcutContext): readonly SovereignToolShortcutGate[] {
  return SOVEREIGN_TOOL_SHORTCUTS.map((definition) => evaluateSovereignToolShortcutGate(definition, context));
}

export function createEmptySovereignToolShortcutContext(): SovereignToolShortcutContext {
  return { repoReady: false, repoFileCount: 0, hasDiffEvidence: false, githubAccessState: 'missing', executorAvailable: false, hasExecutorMission: false, executorIntent: 'unknown', runtimeLogCount: 0, inspectionEvidence: {} };
}
