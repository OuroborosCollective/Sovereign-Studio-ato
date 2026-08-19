/**
 * Sovereign Executor Runtime
 *
 * Step-1 contract for routing execution under the chat surface. This file does
 * not call Sovereign Agent, Direct Patch, Worker, GitHub or shell commands. It only
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
  | 'sovereign-agent'
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
  readonly intent: SovereignExecutorIntentKind;
  readonly taskComplexity?: 'simple' | 'medium' | 'complex' | 'unknown';
  readonly capabilities: SovereignToolCapabilityRegistry;
  readonly workspaceScope?: SovereignWorkspaceScope;
  readonly candidatePath?: string;
}

const OFFLINE_EXACT_COMMANDS: Readonly<Record<string, SovereignExecutorIntentKind>> = {
  '/status': 'status',
  '/question': 'question',
  '/direct-patch': 'direct_patch',
  '/code': 'code_execution',
  '/agent': 'code_execution',
  '/draft-pr': 'draft_pr',
};

/**
 * Offline/degraded fallback for explicit machine controls only.
 *
 * Free user language must remain `unknown` until an online LLM returns structured
 * intent evidence. This runtime deliberately does not infer meaning from words,
 * punctuation or language-specific token lists.
 */
export function classifyOfflineSovereignExecutorIntent(text: string): SovereignExecutorIntentKind {
  const clean = text.trim().toLowerCase();
  if (!clean) return 'unknown';
  const command = clean.split(/\s+/, 1)[0];
  return OFFLINE_EXACT_COMMANDS[command] ?? 'unknown';
}

/**
 * Issue #1567 (A2): fail-closed gate for the offline free-text chat fallback.
 *
 * When the online intent answer violates the schema or free language is not
 * safely classifiable (`unknown` == free_language_not_safely_classifiable), a
 * raw free-text answer must never be adopted as a chat fallback with
 * success/`fertig` semantics while a mutating/actionable intent may have been
 * requested. Only safely classified pure chat intents (`question`, `status`)
 * keep the free fallback. Everything else returns a structured BLOCKED outcome
 * with the concrete missing gates and exactly one next safe action.
 */
export type SovereignChatFallbackGate =
  | 'repo_ready'
  | 'github_write_access'
  | 'agent_route'
  | 'online_intent_evidence';

export interface SovereignChatFallbackInput {
  readonly intent: SovereignExecutorIntentKind;
  readonly repoReady?: boolean;
  readonly githubWriteAllowed?: boolean;
  readonly agentReady?: boolean;
}

export type SovereignChatFallbackDecision =
  | { readonly state: 'chat_fallback_allowed'; readonly reason: string }
  | {
      readonly state: 'blocked';
      readonly reason: string;
      readonly missingGates: readonly SovereignChatFallbackGate[];
      readonly nextAction: string;
    };

const CHAT_FALLBACK_NEXT_ACTION: Record<SovereignChatFallbackGate, string> = {
  repo_ready: 'Repository laden, damit der Auftrag gegen echten Repo-State geprüft werden kann.',
  github_write_access: 'GitHub-Schreibzugriff verifizieren; ohne bestätigten Zugang bleibt jede Mutation blockiert.',
  agent_route: 'Sovereign-Agent-Route konfigurieren und bereitstellen, bevor ein Ausführungsauftrag angenommen wird.',
  online_intent_evidence: 'Online-Sprachdeutung wiederherstellen und den Auftrag erneut senden; Freitext wird nicht als Erfolg gewertet.',
};

export function decideOfflineSovereignChatFallback(
  input: SovereignChatFallbackInput,
): SovereignChatFallbackDecision {
  if (input.intent === 'question' || input.intent === 'status') {
    return {
      state: 'chat_fallback_allowed',
      reason: 'Sicher klassifizierter reiner Chat-/Status-Intent; Freitext-Fallback ohne Aktionssemantik erlaubt.',
    };
  }

  if (input.intent === 'unknown') {
    return {
      state: 'blocked',
      reason: 'Offline-Fallback=free_language_not_safely_classifiable: Absicht nicht sicher klassifizierbar; ein mutierender Auftrag kann nicht ausgeschlossen werden.',
      missingGates: ['online_intent_evidence'],
      nextAction: CHAT_FALLBACK_NEXT_ACTION.online_intent_evidence,
    };
  }

  const missingGates: SovereignChatFallbackGate[] = [];
  if (!input.repoReady) missingGates.push('repo_ready');
  if (!input.githubWriteAllowed) missingGates.push('github_write_access');
  if (!input.agentReady) missingGates.push('agent_route');
  missingGates.push('online_intent_evidence');

  return {
    state: 'blocked',
    reason: `Mutierender Intent (${input.intent}) ohne gültige Online-Intent-Evidence; Freitext-Fallback mit Erfolgssemantik ist verboten.`,
    missingGates,
    nextAction: CHAT_FALLBACK_NEXT_ACTION[missingGates[0]],
  };
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
      state: args.terminal ? 'done' : 'queued',
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
      : capabilityId === 'sovereign-agent'
        ? 'sovereign-agent'
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
  const agent = input.capabilities.agent;
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

    if (agent.canStart) {
      return allowedDecision({
        route: 'sovereign-agent',
        actionRoute: 'sovereign-agent',
        reason: 'Komplexer Codeauftrag darf Sovereign Agent starten, weil Repo und GitHub Write bereit sind.',
        nextAllowedAction: 'start_agent',
        requiredCapability: 'sovereign-agent',
        eventLabel: 'Sovereign Agent Route gewählt',
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

    return blockFromCapability('sovereign-agent', input.capabilities);
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
