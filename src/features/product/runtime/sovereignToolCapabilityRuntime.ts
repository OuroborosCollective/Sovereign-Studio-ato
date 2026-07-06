/**
 * Sovereign Tool Capability Runtime
 *
 * Runtime truth for available execution tools. The UI may display these records,
 * but it must not invent tool readiness itself.
 *
 * Product rules:
 * - No mocks, stubs or facades in live paths.
 * - No fake success: unavailable and blocked are explicit states.
 * - Raw secrets never enter this runtime; pass booleans such as tokenPresent only.
 */

import type {
  SovereignActionRoute,
} from './sovereignActionStreamRuntime';
import type { GitHubAccessState } from './githubAccessRuntime';

export type SovereignToolCapabilityId =
  | 'repo'
  | 'github_write'
  | 'direct_patch'
  | 'openhands'
  | 'worker_chat'
  | 'workspace'
  | 'draft_pr';

export type SovereignToolCapabilityStatus =
  | 'ready'
  | 'blocked'
  | 'validating'
  | 'failed'
  | 'unavailable';

export type SovereignCapabilityNextAction =
  | 'load_repo'
  | 'request_github_access'
  | 'wait_for_validation'
  | 'repair_configuration'
  | 'run_direct_patch'
  | 'start_openhands'
  | 'start_worker_chat'
  | 'start_workspace'
  | 'create_draft_pr'
  | 'show_blocker'
  | 'none';

export interface SovereignToolCapabilityRecord {
  readonly id: SovereignToolCapabilityId;
  readonly status: SovereignToolCapabilityStatus;
  readonly route: SovereignActionRoute;
  readonly label: string;
  readonly reason: string;
  readonly canStart: boolean;
  readonly blocker?: string;
  readonly nextAction: SovereignCapabilityNextAction;
  readonly requiredCapabilities: readonly SovereignToolCapabilityId[];
}

export interface SovereignToolCapabilityRegistry {
  readonly repo: SovereignToolCapabilityRecord;
  readonly githubWrite: SovereignToolCapabilityRecord;
  readonly directPatch: SovereignToolCapabilityRecord;
  readonly openhands: SovereignToolCapabilityRecord;
  readonly workerChat: SovereignToolCapabilityRecord;
  readonly workspace: SovereignToolCapabilityRecord;
  readonly draftPr: SovereignToolCapabilityRecord;
}

export interface SovereignToolCapabilityInput {
  readonly repoReady: boolean;
  readonly githubAccessState: GitHubAccessState;
  /** True when a raw token exists only in the caller's ephemeral ref/session. Never pass the token itself. */
  readonly githubTokenPresent: boolean;
  readonly directPatchSupported: boolean;
  readonly openhandsConfigured: boolean;
  readonly workerAvailable: boolean;
  readonly workspaceConfigured: boolean;
  readonly draftPrSupported: boolean;
  readonly activeExecutorStatus?: 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'blocked';
}

function record(args: SovereignToolCapabilityRecord): SovereignToolCapabilityRecord {
  return args;
}

function isActiveExecutor(status: SovereignToolCapabilityInput['activeExecutorStatus']): boolean {
  return status === 'queued' || status === 'running';
}

export function isGitHubWriteReady(input: Pick<SovereignToolCapabilityInput, 'githubAccessState' | 'githubTokenPresent'>): boolean {
  return input.githubAccessState === 'ready' && input.githubTokenPresent;
}

export function buildSovereignToolCapabilityRegistry(
  input: SovereignToolCapabilityInput,
): SovereignToolCapabilityRegistry {
  const repo = input.repoReady
    ? record({
        id: 'repo',
        status: 'ready',
        route: 'repo',
        label: 'Repository geladen',
        reason: 'Repo-Snapshot ist verfügbar.',
        canStart: true,
        nextAction: 'none',
        requiredCapabilities: [],
      })
    : record({
        id: 'repo',
        status: 'blocked',
        route: 'repo',
        label: 'Repository fehlt',
        reason: 'Ohne Repo-Snapshot darf keine Schreib- oder Executor-Route starten.',
        canStart: false,
        blocker: 'repo_missing',
        nextAction: 'load_repo',
        requiredCapabilities: [],
      });

  const githubWriteReady = isGitHubWriteReady(input);
  const githubWrite = githubWriteReady
    ? record({
        id: 'github_write',
        status: 'ready',
        route: 'github-access',
        label: 'GitHub-Schreibzugang bereit',
        reason: 'GitHub-Zugang wurde validiert; der rohe Token bleibt außerhalb dieser Runtime.',
        canStart: true,
        nextAction: 'none',
        requiredCapabilities: ['repo'],
      })
    : record({
        id: 'github_write',
        status: input.githubAccessState === 'validating' || input.githubAccessState === 'requested'
          ? 'validating'
          : input.githubAccessState === 'invalid'
            ? 'failed'
            : 'blocked',
        route: 'github-access',
        label: 'GitHub-Schreibzugang fehlt',
        reason: input.githubAccessState === 'validating' || input.githubAccessState === 'requested'
          ? 'GitHub-Zugang wird geprüft oder wurde angefordert.'
          : input.githubAccessState === 'invalid'
            ? 'GitHub-Zugang ist ungültig und muss erneuert werden.'
            : 'Schreibende Routen brauchen validierten GitHub-Zugang.',
        canStart: false,
        blocker: input.githubAccessState === 'invalid' ? 'github_access_invalid' : 'github_access_missing',
        nextAction: input.githubAccessState === 'validating' || input.githubAccessState === 'requested'
          ? 'wait_for_validation'
          : 'request_github_access',
        requiredCapabilities: ['repo'],
      });

  const activeExecutor = isActiveExecutor(input.activeExecutorStatus);

  const directPatch = input.repoReady && githubWriteReady && input.directPatchSupported && !activeExecutor
    ? record({
        id: 'direct_patch',
        status: 'ready',
        route: 'direct-github-patch',
        label: 'Direct Patch bereit',
        reason: 'Repo, GitHub-Zugang und Direct-Patch-Unterstützung sind bereit.',
        canStart: true,
        nextAction: 'run_direct_patch',
        requiredCapabilities: ['repo', 'github_write'],
      })
    : record({
        id: 'direct_patch',
        status: activeExecutor ? 'blocked' : 'unavailable',
        route: 'direct-github-patch',
        label: 'Direct Patch nicht bereit',
        reason: activeExecutor
          ? 'Ein Executor läuft bereits; parallele Schreibwege sind blockiert.'
          : !input.repoReady
            ? 'Direct Patch braucht einen geladenen Repo-Snapshot.'
            : !githubWriteReady
              ? 'Direct Patch braucht validierten GitHub-Schreibzugang.'
              : 'Der Auftrag oder Zielpfad ist nicht für Direct Patch geeignet.',
        canStart: false,
        blocker: activeExecutor
          ? 'executor_active'
          : !input.repoReady
            ? 'repo_missing'
            : !githubWriteReady
              ? 'github_access_missing'
              : 'direct_patch_unsupported',
        nextAction: !input.repoReady
          ? 'load_repo'
          : !githubWriteReady
            ? 'request_github_access'
            : activeExecutor
              ? 'show_blocker'
              : 'show_blocker',
        requiredCapabilities: ['repo', 'github_write'],
      });

  const openhands = input.repoReady && githubWriteReady && input.openhandsConfigured && !activeExecutor
    ? record({
        id: 'openhands',
        status: 'ready',
        route: 'openhands',
        label: 'OpenHands bereit',
        reason: 'OpenHands darf nur mit geladenem Repo und validiertem GitHub-Schreibzugang starten.',
        canStart: true,
        nextAction: 'start_openhands',
        requiredCapabilities: ['repo', 'github_write'],
      })
    : record({
        id: 'openhands',
        status: activeExecutor ? 'blocked' : input.openhandsConfigured ? 'blocked' : 'unavailable',
        route: 'openhands',
        label: 'OpenHands nicht bereit',
        reason: activeExecutor
          ? 'Ein Executor läuft bereits; OpenHands darf nicht parallel starten.'
          : !input.repoReady
            ? 'OpenHands braucht einen geladenen Repo-Snapshot.'
            : !githubWriteReady
              ? 'OpenHands-Ausführung mit Schreibabsicht braucht GitHub-Schreibzugang.'
              : 'OpenHands ist nicht konfiguriert.',
        canStart: false,
        blocker: activeExecutor
          ? 'executor_active'
          : !input.repoReady
            ? 'repo_missing'
            : !githubWriteReady
              ? 'github_access_missing'
              : 'openhands_unavailable',
        nextAction: !input.repoReady
          ? 'load_repo'
          : !githubWriteReady
            ? 'request_github_access'
            : 'repair_configuration',
        requiredCapabilities: ['repo', 'github_write'],
      });

  const workerChat = input.workerAvailable
    ? record({
        id: 'worker_chat',
        status: 'ready',
        route: 'worker',
        label: 'Worker Chat bereit',
        reason: 'Worker Chat darf beraten, aber keine Schreibwahrheit erzeugen.',
        canStart: true,
        nextAction: 'start_worker_chat',
        requiredCapabilities: [],
      })
    : record({
        id: 'worker_chat',
        status: 'unavailable',
        route: 'worker',
        label: 'Worker Chat nicht bereit',
        reason: 'Worker ist nicht verfügbar.',
        canStart: false,
        blocker: 'worker_unavailable',
        nextAction: 'show_blocker',
        requiredCapabilities: [],
      });

  const workspace = input.repoReady && githubWriteReady && input.workspaceConfigured && !activeExecutor
    ? record({
        id: 'workspace',
        status: 'ready',
        route: 'toolchain',
        label: 'Workspace bereit',
        reason: 'Isolierter Workspace darf Draft-PR-only arbeiten.',
        canStart: true,
        nextAction: 'start_workspace',
        requiredCapabilities: ['repo', 'github_write'],
      })
    : record({
        id: 'workspace',
        status: activeExecutor ? 'blocked' : input.workspaceConfigured ? 'blocked' : 'unavailable',
        route: 'toolchain',
        label: 'Workspace nicht bereit',
        reason: activeExecutor
          ? 'Ein Executor läuft bereits; Workspace darf nicht parallel starten.'
          : !input.repoReady
            ? 'Workspace braucht ein geladenes Repo.'
            : !githubWriteReady
              ? 'Workspace braucht validierten GitHub-Zugang.'
              : 'Workspace ist nicht konfiguriert.',
        canStart: false,
        blocker: activeExecutor
          ? 'executor_active'
          : !input.repoReady
            ? 'repo_missing'
            : !githubWriteReady
              ? 'github_access_missing'
              : 'workspace_unavailable',
        nextAction: !input.repoReady
          ? 'load_repo'
          : !githubWriteReady
            ? 'request_github_access'
            : 'repair_configuration',
        requiredCapabilities: ['repo', 'github_write'],
      });

  const draftPr = input.repoReady && githubWriteReady && input.draftPrSupported
    ? record({
        id: 'draft_pr',
        status: 'ready',
        route: 'github-patch',
        label: 'Draft PR bereit',
        reason: 'Draft PR ist als terminaler Schreibpfad erlaubt; Auto-Merge bleibt blockiert.',
        canStart: true,
        nextAction: 'create_draft_pr',
        requiredCapabilities: ['repo', 'github_write'],
      })
    : record({
        id: 'draft_pr',
        status: input.draftPrSupported ? 'blocked' : 'unavailable',
        route: 'github-patch',
        label: 'Draft PR nicht bereit',
        reason: !input.repoReady
          ? 'Draft PR braucht ein geladenes Repo.'
          : !githubWriteReady
            ? 'Draft PR braucht validierten GitHub-Schreibzugang.'
            : 'Draft PR Route ist nicht verfügbar.',
        canStart: false,
        blocker: !input.repoReady
          ? 'repo_missing'
          : !githubWriteReady
            ? 'github_access_missing'
            : 'draft_pr_unavailable',
        nextAction: !input.repoReady
          ? 'load_repo'
          : !githubWriteReady
            ? 'request_github_access'
            : 'repair_configuration',
        requiredCapabilities: ['repo', 'github_write'],
      });

  return {
    repo,
    githubWrite,
    directPatch,
    openhands,
    workerChat,
    workspace,
    draftPr,
  };
}

export function getSovereignToolCapability(
  registry: SovereignToolCapabilityRegistry,
  id: SovereignToolCapabilityId,
): SovereignToolCapabilityRecord {
  switch (id) {
    case 'repo':
      return registry.repo;
    case 'github_write':
      return registry.githubWrite;
    case 'direct_patch':
      return registry.directPatch;
    case 'openhands':
      return registry.openhands;
    case 'worker_chat':
      return registry.workerChat;
    case 'workspace':
      return registry.workspace;
    case 'draft_pr':
      return registry.draftPr;
  }
}

export function summarizeBlockedCapabilities(
  registry: SovereignToolCapabilityRegistry,
): readonly SovereignToolCapabilityRecord[] {
  return [
    registry.repo,
    registry.githubWrite,
    registry.directPatch,
    registry.openhands,
    registry.workerChat,
    registry.workspace,
    registry.draftPr,
  ].filter((capability) => capability.status !== 'ready');
}
