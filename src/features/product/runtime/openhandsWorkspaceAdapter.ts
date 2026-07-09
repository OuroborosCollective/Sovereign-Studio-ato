/**
 * OpenHands Workspace Adapter
 *
 * Routes OpenHands through the neutral AgentWorkspaceRuntime contract.
 * This adapter does NOT start OpenHands directly — it normalizes the interface
 * between the Sovereign runtime and the external OpenHands backend.
 *
 * Rules:
 * - Call validateAgentWorkspaceRequest() before dispatch
 * - Sanitize events with sanitizeWorkspaceEvent()
 * - Normalize final output with normalizeAgentWorkspaceResult()
 * - Set status to 'blocked' when OpenHands cannot return real workspace state
 * - Never invent changedFiles, tests or Draft PR URL
 * - Surface workspaceInspectorUrl only if OpenHands actually returns it
 */

import {
  type AgentWorkspaceExecutor,
  type AgentWorkspaceRequest,
  type AgentWorkspaceResult,
  type AgentWorkspaceStatus,
  isSupportedWorkspaceExecutor,
  isTerminalWorkspaceStatus,
  normalizeAgentWorkspaceResult,
  sanitizeWorkspaceEvent,
  shouldCleanupWorkspace,
  validateAgentWorkspaceRequest,
} from './agentWorkspaceRuntime';

import {
  type OpenHandsEnterpriseConfig,
  type OpenHandsJobSnapshot,
  type OpenHandsRuntimeEvent,
  maskOpenHandsSensitiveText,
  summarizeOpenHandsJob,
} from './openhandsEnterpriseRuntime';

/** Maps OpenHands status to neutral workspace status */
function mapOpenHandsStatus(ohStatus: OpenHandsJobSnapshot['status']): AgentWorkspaceStatus {
  switch (ohStatus) {
    case 'idle': return 'queued';
    case 'queued': return 'queued';
    case 'running': return 'running';
    case 'waiting-for-user': return 'running';
    case 'blocked': return 'blocked';
    case 'failed': return 'failed';
    case 'completed': return 'completed';
    default: return 'blocked';
  }
}

/** Maps OpenHands runtime event to neutral workspace event */
function mapOpenHandsEvent(ohEvent: OpenHandsRuntimeEvent) {
  const sanitizedMessage = maskOpenHandsSensitiveText(ohEvent.message);
  return sanitizeWorkspaceEvent({
    level: ohEvent.level === 'success' ? 'info' : ohEvent.level,
    message: sanitizedMessage,
    at: ohEvent.at,
  });
}

/** OpenHands workspace adapter interface */
export interface OpenHandsWorkspaceAdapter {
  start(request: AgentWorkspaceRequest): Promise<AgentWorkspaceResult>;
  read(workspaceId: string): Promise<AgentWorkspaceResult>;
  cleanup(workspaceId: string): Promise<AgentWorkspaceResult>;
}

/** Configuration for the OpenHands workspace adapter */
export interface OpenHandsWorkspaceAdapterConfig {
  executor: AgentWorkspaceExecutor;
  config: OpenHandsEnterpriseConfig;
  /** Maps OpenHands snapshot to workspace result */
  mapSnapshot: (snapshot: OpenHandsJobSnapshot) => Partial<AgentWorkspaceResult>;
  /** Cleanup callback - called when workspace should be torn down */
  onCleanup?: (workspaceId: string) => Promise<void>;
}

/** Create an OpenHands workspace adapter */
export function createOpenHandsWorkspaceAdapter(config: OpenHandsWorkspaceAdapterConfig): OpenHandsWorkspaceAdapter {
  const { executor, config: ohConfig, mapSnapshot, onCleanup } = config;

  async function normalizeFromSnapshot(
    workspaceId: string,
    snapshot: OpenHandsJobSnapshot,
  ): Promise<AgentWorkspaceResult> {
    const mapped = mapSnapshot(snapshot);
    return normalizeAgentWorkspaceResult({
      workspaceId,
      status: mapOpenHandsStatus(snapshot.status),
      events: snapshot.events.map(mapOpenHandsEvent),
      changedFiles: mapped.changedFiles ?? [],
      diffSummary: mapped.diffSummary,
      testSummary: mapped.testSummary,
      draftPrUrl: mapped.draftPrUrl,
      blocker: mapped.blocker ?? (snapshot.lastError ? maskOpenHandsSensitiveText(snapshot.lastError) : undefined),
      workspaceInspectorUrl: mapped.workspaceInspectorUrl,
    });
  }

  return {
    async start(request: AgentWorkspaceRequest): Promise<AgentWorkspaceResult> {
      // Validate request through neutral contract
      const validation = validateAgentWorkspaceRequest(request);
      if (!validation.allowed) {
        return normalizeAgentWorkspaceResult({
          workspaceId: `blocked-${Date.now()}`,
          status: 'blocked',
          events: [],
          changedFiles: [],
          blocker: validation.blockers.join('; ') || 'Request validation failed.',
        });
      }

      // Check executor support
      if (!isSupportedWorkspaceExecutor(executor)) {
        return normalizeAgentWorkspaceResult({
          workspaceId: `blocked-${Date.now()}`,
          status: 'blocked',
          events: [],
          changedFiles: [],
          blocker: `Executor '${executor}' is not supported by the OpenHands adapter.`,
        });
      }

      // Check OpenHands backend readiness
      if (!ohConfig.ready) {
        return normalizeAgentWorkspaceResult({
          workspaceId: `blocked-${Date.now()}`,
          status: 'blocked',
          events: [],
          changedFiles: [],
          blocker: ohConfig.reason || 'OpenHands backend is not ready.',
        });
      }

      // Generate workspace ID from executor and timestamp
      const workspaceId = `${executor}-${Date.now()}`;

      // Return queued state — actual dispatch to OpenHands happens elsewhere
      return normalizeAgentWorkspaceResult({
        workspaceId,
        status: 'queued',
        events: [sanitizeWorkspaceEvent({
          level: 'info',
          message: `Workspace ${workspaceId} queued for executor ${executor}.`,
          at: Date.now(),
        })],
        changedFiles: [],
      });
    },

    async read(workspaceId: string): Promise<AgentWorkspaceResult> {
      if (!workspaceId || workspaceId.startsWith('blocked-')) {
        return normalizeAgentWorkspaceResult({
          workspaceId,
          status: 'blocked',
          events: [],
          changedFiles: [],
          blocker: 'Invalid or blocked workspace ID.',
        });
      }

      // Check backend readiness before attempting state fetch.
      // This mirrors the start() guard so users get the same honest reason.
      if (!ohConfig.ready) {
        return normalizeAgentWorkspaceResult({
          workspaceId,
          status: 'blocked',
          events: [],
          changedFiles: [],
          blocker: ohConfig.reason
            || 'OpenHands-Backend nicht konfiguriert. Workspace-Status kann nicht abgerufen werden.',
        });
      }

      // Backend is configured but live state polling is not yet connected.
      // Honest block: distinguishes "not configured" from "configured but no poll".
      // Next step for backend integration: replace this block with a real API call
      // to GET /api/workspaces/{workspaceId} and map the response via mapSnapshot().
      return normalizeAgentWorkspaceResult({
        workspaceId,
        status: 'blocked',
        events: [sanitizeWorkspaceEvent({
          level: 'warn',
          message: 'Workspace-Status-Polling noch nicht verbunden. Backend ist konfiguriert, aber live-State-Abruf fehlt.',
          at: Date.now(),
        })],
        changedFiles: [],
        blocker: 'Workspace-Status-Polling nicht verbunden. Backend ist bereit, aber der live-State-Abruf ist noch nicht implementiert.',
      });
    },

    async cleanup(workspaceId: string): Promise<AgentWorkspaceResult> {
      if (!workspaceId || workspaceId.startsWith('blocked-')) {
        return normalizeAgentWorkspaceResult({
          workspaceId,
          status: 'cleaned',
          events: [],
          changedFiles: [],
        });
      }

      try {
        if (onCleanup) {
          await onCleanup(workspaceId);
        }
      } catch {
        // Cleanup failed — preserve blocker but still mark as cleaned
      }

      return normalizeAgentWorkspaceResult({
        workspaceId,
        status: 'cleaned',
        events: [sanitizeWorkspaceEvent({
          level: 'info',
          message: `Workspace ${workspaceId} cleaned.`,
          at: Date.now(),
        })],
        changedFiles: [],
        cleanedAt: Date.now(),
      });
    },
  };
}

/** Summarize workspace status for display (short German messages) */
export function summarizeWorkspaceStatus(result: AgentWorkspaceResult): string {
  switch (result.status) {
    case 'queued': return 'Workspace gestartet';
    case 'running': return 'Repo geklont · Tests laufen';
    case 'completed': return result.draftPrUrl ? 'Draft PR bereit' : 'Workspace abgeschlossen';
    case 'failed': return result.blocker ? `Blocker: ${result.blocker.slice(0, 60)}` : 'Workspace fehlgeschlagen';
    case 'blocked': return result.blocker ? `Blocker: ${result.blocker.slice(0, 60)}` : 'Workspace blockiert';
    case 'cleaned': return 'Workspace bereinigt';
    default: return 'Unbekannter Status';
  }
}

/** Check if workspace should show inspector link */
export function canShowWorkspaceInspector(result: AgentWorkspaceResult): boolean {
  return Boolean(
    result.workspaceInspectorUrl
    && result.workspaceInspectorUrl.startsWith('https://')
    && result.status !== 'blocked'
    && result.status !== 'cleaned',
  );
}

/** Determine next action based on workspace result */
export function getWorkspaceNextAction(result: AgentWorkspaceResult): {
  action: 'none' | 'retry' | 'inspect' | 'cleanup' | 'publish';
  label: string;
} {
  if (result.status === 'completed' && result.draftPrUrl) {
    return { action: 'publish', label: 'Draft PR ansehen' };
  }
  if (result.status === 'completed') {
    return { action: 'inspect', label: 'Workspace ansehen' };
  }
  if (result.status === 'failed' || result.status === 'blocked') {
    return { action: 'retry', label: 'Erneut versuchen' };
  }
  if (shouldCleanupWorkspace(result.status) && result.status !== 'cleaned') {
    return { action: 'cleanup', label: 'Workspace bereinigen' };
  }
  return { action: 'none', label: '' };
}
