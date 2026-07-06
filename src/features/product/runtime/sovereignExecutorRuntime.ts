/**
 * Sovereign Executor Runtime
 *
 * Step-1 contract for routing execution under the chat surface. This file does
 * not call OpenHands, Direct Patch, Worker, GitHub or shell commands. It only
 * decides which route is allowed from runtime truth.
 */

import type {
  SovereignActionEventInput,
  SovereignActionRoute,
} from './sovereignActionStreamRuntime';
import type {
  SovereignToolCapabilityId,
  SovereignToolCapabilityRegistry,
  SovereignCapabilityNextAction,
} from './sovereignToolCapabilityRuntime';
import { getSovereignToolCapability } from './sovereignToolCapabilityRuntime';
import type {
  SovereignWorkspaceScope,
  SovereignWorkspaceScopeValidation,
} from './sovereignWorkspaceScopeRuntime';
import { canWorkspaceTouchPath, validateSovereignWorkspaceScope } from './sovereignWorkspaceScopeRuntime';

export type SovereignExecutorRoute =
  | 'local_status'
  | 'github_access'
  | 'direct_patch'
  | 'openhands'
  | 'worker_chat'
  | 'workspace'
  | 'blocked';

export type SovereignExecutorDecisionState = 'allowed' | 'blocked';

export type SovereignExecutorIntentKind =
  | 'status'
  | 'question'
  | 'direct_patch'
  | 'code_execution'
  | 'draft_pr'
  | 'unknown';

export interface SovereignExecutorDecision {
  readonly route: SovereignExecutorRoute;
  readonly actionRoute: SovereignActionRoute;
  readonly state: SovereignExecutorDecisionState;
  readonly reason: string;
  readonly nextAllowedAction: SovereignCapabilityNextAction;
  readonly requiredCapability?: SovereignToolCapabilityId;
  readonly blocker?: string;
  readonly terminal: boolean;
  readonly workspaceValidation?: SovereignWorkspaceScopeValidation;
  readonly event: SovereignActionEventInput;
}

export interface SovereignExecutorRouteInput {
  readonly text: string;
  readonly intent: SovereignExecutorIntentKind;
  readonly capabilities: SovereignToolCapabilityRegistry;
  readonly workspaceScope?: SovereignWorkspaceScope;
  readonly candidatePath?: string;
}

const STATUS_TOKENS = [
  'status',
  'was ist der status',
  'bist du fertig',
  'fertig?',
  'warum passiert nichts',
  'läuft',
  'laeuft',
];

const QUESTION_TOKENS = [
  'was ist',
  'wie funktioniert',
  'warum',
  'erklär',
  'erklaer',
  'explain',
  'how does',
  '?',
];

const DIRECT_PATCH_TOKENS = [
  'readme',
  'docs',
  'dokumentation',
  'changelog',
  'titel',
  'überschrift',
  'ueberschrift',
];

const CODE_EXECUTION_TOKENS = [
  'baue',
  'bauen',
  'implementiere',
  'implementieren',
  'fixe',
  'repariere',
  'ändere datei',
  'aendere datei',
  'code',
  'test',
  'refactor',
  'workflow',
  'backend',
  'frontend',
];

const DRAFT_PR_TOKENS = ['draft pr', 'pull request', 'pr erstellen', 'create pr'];

function includesAny(value: string, tokens: readonly string[]): boolean {
  return tokens.some((token) => value.includes(token));
}

export function classifySovereignExecutorIntent(text: string): SovereignExecutorIntentKind {
  const clean = text.trim().toLowerCase();
  if (!clean) return 'unknown';
  if (includesAny(clean, STATUS_TOKENS)) return 'status';
  if (includesAny(clean, DRAFT_PR_TOKENS)) return 'draft_pr';
  if (includesAny(clean, DIRECT_PATCH_TOKENS) && !includesAny(clean, CODE_EXECUTION_TOKENS)) return 'direct_patch';
  if (includesAny(clean, CODE_EXECUTION_TOKENS)) return 'code_execution';
  if (includesAny(clean, QUESTION_TOKENS)) return 'question';
  return 'unknown';
}

function event(args: {
  readonly route: SovereignActionRoute;
  readonly kind: SovereignActionEventInput['kind'];
  readonly label: string;
  readonly detail?: string;
  readonly state: SovereignActionEventInput['state'];
}): SovereignActionEventInput {
  return args;
}

function allowedDecision(args: {
  readonly route: SovereignExecutorRoute;
  readonly actionRoute: SovereignActionRoute;
  readonly reason: string;
  readonly nextAllowedAction: SovereignCapabilityNextAction;
  readonly requiredCapability?: SovereignToolCapabilityId;
  readonly eventLabel: string;
  readonly eventKind?: SovereignActionEventInput['kind'];
  readonly terminal?: boolean;
  readonly workspaceValidation?: SovereignWorkspaceScopeValidation;
}): SovereignExecutorDecision {
  return {
    route: args.route,
    actionRoute: args.actionRoute,
    state: 'allowed',
    reason: args.reason,
    nextAllowedAction: args.nextAllowedAction,
    requiredCapability: args.requiredCapability,
    terminal: args.terminal ?? false,
    workspaceValidation: args.workspaceValidation,
    event: event({
      route: args.actionRoute,
      kind: args.eventKind ?? 'route_selected',
      label: args.eventLabel,
      detail: args.reason,
      state: 'running',
    }),
  };
}

function blockedDecision(args: {
  readonly route: SovereignExecutorRoute;
  readonly actionRoute: SovereignActionRoute;
  readonly reason: string;
  readonly nextAllowedAction: SovereignCapabilityNextAction;
  readonly blocker: string;
  readonly requiredCapability?: SovereignToolCapabilityId;
  readonly eventLabel: string;
  readonly eventKind?: SovereignActionEventInput['kind'];
  readonly workspaceValidation?: SovereignWorkspaceScopeValidation;
}): SovereignExecutorDecision {
  return {
    route: args.route,
    actionRoute: args.actionRoute,
    state: 'blocked',
    reason: args.reason,
    nextAllowedAction: args.nextAllowedAction,
    requiredCapability: args.requiredCapability,
    blocker: args.blocker,
    terminal: true,
    workspaceValidation: args.workspaceValidation,
    event: event({
      route: args.actionRoute,
      kind: args.eventKind ?? 'blocked',
      label: args.eventLabel,
      detail: args.reason,
      state: 'blocked',
    }),
  };
}

function blockFromCapability(capabilityId: SovereignToolCapabilityId, capabilities: SovereignToolCapabilityRegistry): SovereignExecutorDecision {
  const capability = getSovereignToolCapability(capabilities, capabilityId);
  const route: SovereignExecutorRoute = capabilityId === 'github_write'
    ? 'github_access'
    : capabilityId === 'direct_patch'
      ? 'direct_patch'
      : capabilityId === 'openhands'
        ? 'openhands'
        : capabilityId === 'workspace'
          ? 'workspace'
          : 'blocked';

  return blockedDecision({
    route,
    actionRoute: capability.route,
    reason: capability.reason,
    nextAllowedAction: capability.nextAction,
    blocker: capability.blocker ?? `${capabilityId}_blocked`,
    requiredCapability: capabilityId,
    eventLabel: capability.label,
    eventKind: capabilityId === 'github_write' ? 'github_access_required' : 'blocked',
  });
}

function validateWorkspaceForExecution(input: SovereignExecutorRouteInput): SovereignWorkspaceScopeValidation | null {
  if (!input.workspaceScope) return null;
  const validation = validateSovereignWorkspaceScope(input.workspaceScope);
  if (!validation.allowed) return validation;
  if (!input.candidatePath) return validation;
  const pathCheck = canWorkspaceTouchPath(input.workspaceScope, input.candidatePath);
  return pathCheck.allowed
    ? validation
    : {
        status: 'blocked',
        allowed: false,
        blockers: [pathCheck.reason],
        warnings: validation.warnings,
      };
}

export function decideSovereignExecutorRoute(input: SovereignExecutorRouteInput): SovereignExecutorDecision {
  const repo = input.capabilities.repo;
  const githubWrite = input.capabilities.githubWrite;
  const directPatch = input.capabilities.directPatch;
  const openhands = input.capabilities.openhands;
  const workerChat = input.capabilities.workerChat;
  const workspace = input.capabilities.workspace;

  if (input.intent === 'status') {
    return allowedDecision({
      route: 'local_status',
      actionRoute: 'runtime',
      reason: 'Status- und Diagnosefragen werden aus lokalem Runtime-State beantwortet.',
      nextAllowedAction: 'none',
      eventLabel: 'Lokale Statusroute gewählt',
      terminal: true,
    });
  }

  if (input.intent === 'question') {
    if (workerChat.canStart) {
      return allowedDecision({
        route: 'worker_chat',
        actionRoute: 'worker',
        reason: 'Frage darf über Worker Chat beantwortet werden; keine Schreibroute wird gestartet.',
        nextAllowedAction: 'start_worker_chat',
        requiredCapability: 'worker_chat',
        eventLabel: 'Worker Chat Route gewählt',
      });
    }
    return blockFromCapability('worker_chat', input.capabilities);
  }

  if (!repo.canStart) {
    return blockFromCapability('repo', input.capabilities);
  }

  if (input.intent === 'direct_patch') {
    if (directPatch.canStart) {
      return allowedDecision({
        route: 'direct_patch',
        actionRoute: 'direct-github-patch',
        reason: 'Ein kleiner README/Dokumentationsauftrag darf über Direct Patch laufen.',
        nextAllowedAction: 'run_direct_patch',
        requiredCapability: 'direct_patch',
        eventLabel: 'Direct Patch Route gewählt',
      });
    }
    if (!githubWrite.canStart) return blockFromCapability('github_write', input.capabilities);
    return blockFromCapability('direct_patch', input.capabilities);
  }

  if (input.intent === 'draft_pr') {
    if (!githubWrite.canStart) return blockFromCapability('github_write', input.capabilities);
    const draftPr = input.capabilities.draftPr;
    if (draftPr.canStart) {
      return allowedDecision({
        route: 'workspace',
        actionRoute: 'github-patch',
        reason: 'Draft PR darf als terminale Schreibroute vorbereitet werden; Auto-Merge bleibt blockiert.',
        nextAllowedAction: 'create_draft_pr',
        requiredCapability: 'draft_pr',
        eventLabel: 'Draft PR Route gewählt',
      });
    }
    return blockFromCapability('draft_pr', input.capabilities);
  }

  if (input.intent === 'code_execution') {
    if (!githubWrite.canStart) return blockFromCapability('github_write', input.capabilities);

    const workspaceValidation = validateWorkspaceForExecution(input);
    if (workspaceValidation && !workspaceValidation.allowed) {
      return blockedDecision({
        route: 'workspace',
        actionRoute: 'toolchain',
        reason: workspaceValidation.blockers.join(' '),
        nextAllowedAction: 'show_blocker',
        blocker: 'workspace_scope_blocked',
        requiredCapability: 'workspace',
        eventLabel: 'Workspace Scope blockiert',
        workspaceValidation,
      });
    }

    if (directPatch.canStart && input.candidatePath && input.workspaceScope && canWorkspaceTouchPath(input.workspaceScope, input.candidatePath).allowed) {
      return allowedDecision({
        route: 'direct_patch',
        actionRoute: 'direct-github-patch',
        reason: 'Codeauftrag hat einen erlaubten kleinen Zielpfad und darf Direct Patch nutzen.',
        nextAllowedAction: 'run_direct_patch',
        requiredCapability: 'direct_patch',
        eventLabel: 'Direct Patch Route gewählt',
        workspaceValidation: workspaceValidation ?? undefined,
      });
    }

    if (openhands.canStart) {
      return allowedDecision({
        route: 'openhands',
        actionRoute: 'openhands',
        reason: 'Komplexer Codeauftrag darf OpenHands starten, weil Repo und GitHub Write bereit sind.',
        nextAllowedAction: 'start_openhands',
        requiredCapability: 'openhands',
        eventLabel: 'OpenHands Route gewählt',
        workspaceValidation: workspaceValidation ?? undefined,
      });
    }

    if (workspace.canStart) {
      return allowedDecision({
        route: 'workspace',
        actionRoute: 'toolchain',
        reason: 'Komplexer Codeauftrag darf über den isolierten Workspace laufen.',
        nextAllowedAction: 'start_workspace',
        requiredCapability: 'workspace',
        eventLabel: 'Workspace Route gewählt',
        workspaceValidation: workspaceValidation ?? undefined,
      });
    }

    return blockFromCapability('openhands', input.capabilities);
  }

  if (workerChat.canStart) {
    return allowedDecision({
      route: 'worker_chat',
      actionRoute: 'worker',
      reason: 'Unklarer Auftrag wird zuerst als Beratung behandelt; keine Schreibroute startet ohne klaren Intent.',
      nextAllowedAction: 'start_worker_chat',
      requiredCapability: 'worker_chat',
      eventLabel: 'Worker Chat Route gewählt',
    });
  }

  return blockedDecision({
    route: 'blocked',
    actionRoute: 'runtime',
    reason: 'Kein erlaubter Executor-Pfad verfügbar.',
    nextAllowedAction: 'show_blocker',
    blocker: 'no_executor_route',
    eventLabel: 'Executor Route blockiert',
  });
}
