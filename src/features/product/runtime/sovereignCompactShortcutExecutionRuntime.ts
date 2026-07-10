import type { OpenHandsRuntimeEvent } from './openhandsEnterpriseRuntime';
import type {
  SovereignActionEvent,
  SovereignActionEventInput,
} from './sovereignActionStreamRuntime';
import type {
  SovereignToolShortcutId,
} from './sovereignToolShortcutRuntime';
import type {
  SovereignExecutorIntentKind,
} from './sovereignExecutorRuntime';
import type { GitHubAccessState } from './githubAccessRuntime';

export type SovereignCompactShortcutSurface =
  | 'repo-setup'
  | 'repo-explorer'
  | 'files-explorer'
  | 'changed-files'
  | 'patch-diff'
  | 'github-access'
  | 'github-status'
  | 'executor-request'
  | 'runtime-logs'
  | 'inspection-tool'
  | 'blocked';

export interface SovereignCompactShortcutExecutionInput {
  readonly id: SovereignToolShortcutId;
  readonly repoSnapshotReady: boolean;
  readonly repoFileCount: number;
  readonly changedFiles: readonly string[];
  readonly patchDiffAvailable: boolean;
  readonly githubAccessState: GitHubAccessState;
  readonly executorAvailable: boolean;
  readonly executorIntent: SovereignExecutorIntentKind;
  readonly runtimeEventCount: number;
}

export interface SovereignCompactShortcutExecutionDecision {
  readonly canExecute: boolean;
  readonly surface: SovereignCompactShortcutSurface;
  readonly event?: SovereignActionEventInput;
  readonly reason: string;
  readonly nextAction: string;
}

function event(input: SovereignActionEventInput): SovereignActionEventInput {
  return input;
}

function blocked(
  route: SovereignActionEventInput['route'],
  label: string,
  reason: string,
  nextAction: string,
): SovereignCompactShortcutExecutionDecision {
  return {
    canExecute: false,
    surface: 'blocked',
    reason,
    nextAction,
    event: event({ kind: 'blocked', route, label, detail: `${reason} Nächste Aktion: ${nextAction}`, state: 'blocked' }),
  };
}

export function isExecutorExecutionIntent(intent: SovereignExecutorIntentKind): boolean {
  return intent === 'code_execution' || intent === 'draft_pr';
}

export function decideSovereignCompactShortcutExecution(
  input: SovereignCompactShortcutExecutionInput,
): SovereignCompactShortcutExecutionDecision {
  switch (input.id) {
    case 'repo':
      if (!input.repoSnapshotReady) {
        return {
          canExecute: true,
          surface: 'repo-setup',
          reason: 'Noch kein vollständiger Repo-Snapshot vorhanden.',
          nextAction: 'GitHub-URL eingeben und Repo-Snapshot laden.',
          event: event({
            kind: 'done',
            route: 'repo',
            label: 'Repo-Setup geöffnet',
            detail: 'Setup-Fläche geöffnet; es wurde noch kein Repo als geladen markiert.',
            state: 'done',
          }),
        };
      }
      return {
        canExecute: true,
        surface: 'repo-explorer',
        reason: 'Vollständiger Repo-Snapshot vorhanden.',
        nextAction: 'Repo-Explorer prüfen.',
        event: event({ kind: 'done', route: 'repo', label: 'Repo-Explorer geöffnet', detail: `${input.repoFileCount} bestätigte Dateien im Snapshot.`, state: 'done' }),
      };

    case 'files':
      if (!input.repoSnapshotReady) return blocked('files', 'Files blockiert', 'Kein vollständiger Repo-Snapshot vorhanden.', 'Repo laden.');
      if (input.repoFileCount <= 0) return blocked('files', 'Files blockiert', 'Der Snapshot enthält keine bestätigte Dateiliste.', 'Repo-Snapshot erneut laden.');
      return {
        canExecute: true,
        surface: 'files-explorer',
        reason: 'Bestätigte Datei-Evidence vorhanden.',
        nextAction: 'Datei-Explorer prüfen.',
        event: event({ kind: 'done', route: 'files', label: 'Datei-Explorer geöffnet', detail: `${input.repoFileCount} bestätigte Dateien im Snapshot.`, state: 'done' }),
      };

    case 'diff':
      if (input.changedFiles.length > 0) {
        return {
          canExecute: true,
          surface: 'changed-files',
          reason: 'Bestätigte Changed-Files-Evidence vorhanden.',
          nextAction: 'Geänderte Dateien prüfen.',
          event: event({ kind: 'done', route: 'diff', label: 'Diff-Prüfung geöffnet', detail: `${input.changedFiles.length} bestätigte Changed Files: ${input.changedFiles.join(' · ')}`, state: 'done' }),
        };
      }
      if (input.patchDiffAvailable) {
        return {
          canExecute: true,
          surface: 'patch-diff',
          reason: 'Gespeicherter Patch-Diff-Report vorhanden.',
          nextAction: 'Patch-Diff prüfen.',
          event: event({ kind: 'done', route: 'diff', label: 'Patch-Diff geöffnet', detail: 'Gespeicherter Diff-Report wird angezeigt.', state: 'done' }),
        };
      }
      return blocked('diff', 'Diff blockiert', 'Keine Changed-Files- oder Patch-Diff-Evidence vorhanden.', 'Zuerst Patch oder Diff erzeugen.');

    case 'github_access':
      if (input.githubAccessState === 'requested' || input.githubAccessState === 'validating') {
        return {
          canExecute: true,
          surface: 'github-status',
          reason: 'GitHub-Zugang wird bereits validiert.',
          nextAction: 'Laufenden Validierungsstatus anzeigen.',
          event: event({ kind: 'route_selected', route: 'github-access', label: 'GitHub-Zugangsprüfung angezeigt', detail: 'Keine zweite Validierung gestartet; keine Secrets angezeigt.', state: 'running' }),
        };
      }
      if (input.githubAccessState === 'ready') {
        return {
          canExecute: true,
          surface: 'github-status',
          reason: 'GitHub-Schreibzugang wurde validiert.',
          nextAction: 'Validierten Status anzeigen.',
          event: event({ kind: 'done', route: 'github-access', label: 'GitHub-Zugangsstatus angezeigt', detail: 'Validierter Schreibzugang; Secret-Werte bleiben verborgen.', state: 'done' }),
        };
      }
      return {
        canExecute: true,
        surface: 'github-access',
        reason: 'Kein validierter GitHub-Zugang vorhanden.',
        nextAction: 'Sicheres Zugangsfeld öffnen.',
        event: event({ kind: 'access_required', route: 'github-access', label: 'GitHub-Zugang geöffnet', detail: 'Sicheres Zugangsfeld geöffnet; keine Secrets im Chat.', state: 'blocked' }),
      };

    case 'executor':
      if (!input.repoSnapshotReady) return blocked('agent-job', 'Executor blockiert', 'Kein vollständiger Repo-Snapshot vorhanden.', 'Repo laden.');
      if (!isExecutorExecutionIntent(input.executorIntent)) return blocked('agent-job', 'Executor blockiert', 'Der aktuelle Text ist kein bestätigter Code- oder Draft-PR-Ausführungsauftrag.', 'Einen klaren Ausführungsauftrag eingeben.');
      if (input.githubAccessState !== 'ready') {
        return {
          canExecute: false,
          surface: 'github-access',
          reason: 'Executor-Schreibpfad braucht validierten GitHub-Zugang.',
          nextAction: 'GitHub-Zugang sicher validieren.',
          event: event({ kind: 'github_access_required', route: 'github-access', label: 'Executor braucht GitHub-Zugang', detail: 'Ausführungsauftrag erkannt, aber GitHub-Schreibzugang ist nicht validiert.', state: 'blocked' }),
        };
      }
      if (!input.executorAvailable) return blocked('agent-job', 'Executor blockiert', 'Agent-Runtime oder Start-Callback ist nicht verfügbar.', 'Agent-Runtime verbinden.');
      return {
        canExecute: true,
        surface: 'executor-request',
        reason: 'Repo, GitHub-Zugang, Executor und Ausführungsintent sind bestätigt.',
        nextAction: 'Agent-Job anfragen und auf Backend-Job-State warten.',
      };

    case 'runtime_logs':
      return {
        canExecute: true,
        surface: 'runtime-logs',
        reason: input.runtimeEventCount > 0 ? 'Gespeicherte Runtime-Evidence vorhanden.' : 'Noch keine Runtime-Evidence vorhanden.',
        nextAction: 'Runtime-Evidence-Log öffnen.',
        event: event({
          kind: 'done',
          route: 'runtime-logs',
          label: 'Runtime-Evidence-Log geöffnet',
          detail: input.runtimeEventCount > 0 ? `${input.runtimeEventCount} echte Runtime-Ereignisse vorhanden.` : 'Log-Fläche geöffnet; noch keine Runtime-Ereignisse vorhanden.',
          state: 'done',
        }),
      };

    case 'health':
    case 'memory':
    case 'coverage':
    case 'settings':
      return {
        canExecute: true,
        surface: 'inspection-tool',
        reason: 'Inspektions-Tool erzeugt sein Ergebnis aus eigener Runtime-Evidence.',
        nextAction: 'Tool öffnen und Ergebnis abwarten.',
      };
  }
}

export type SovereignRuntimeEvidenceSource = 'action-stream' | 'agent-runtime';

export interface SovereignRuntimeEvidenceLogEntry {
  readonly id: string;
  readonly at: number;
  readonly source: SovereignRuntimeEvidenceSource;
  readonly level: 'info' | 'warning' | 'error' | 'success';
  readonly scope: string;
  readonly message: string;
}

function actionLevel(event: SovereignActionEvent): SovereignRuntimeEvidenceLogEntry['level'] {
  if (event.state === 'failed') return 'error';
  if (event.state === 'blocked') return 'warning';
  if (event.state === 'done') return 'success';
  return 'info';
}

export function buildSovereignRuntimeEvidenceLog(
  actionEvents: readonly SovereignActionEvent[],
  agentEvents: readonly OpenHandsRuntimeEvent[],
): readonly SovereignRuntimeEvidenceLogEntry[] {
  const fromActions = actionEvents.map((entry) => ({
    id: `action:${entry.id}`,
    at: entry.createdAt,
    source: 'action-stream' as const,
    level: actionLevel(entry),
    scope: `${entry.route}/${entry.kind}`,
    message: entry.detail ? `${entry.label} · ${entry.detail}` : entry.label,
  }));
  const fromAgent = agentEvents.map((entry, index) => ({
    id: `agent:${entry.at}:${entry.stage}:${index}`,
    at: entry.at,
    source: 'agent-runtime' as const,
    level: entry.level,
    scope: entry.stage,
    message: entry.message,
  }));
  return [...fromActions, ...fromAgent].sort((left, right) => left.at - right.at);
}
