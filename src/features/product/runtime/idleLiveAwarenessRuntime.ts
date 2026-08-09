import { createSovereignAgentClient, type SovereignAgentClient } from './sovereignAgentClient';
import { resolveSovereignAgentConfig, type SovereignAgentJobSnapshot } from './sovereignAgentRuntime';
import { createTelemetryEvent, type SovereignTelemetryLevel } from './sovereignTelemetry';
import {
  idleAwarenessTargetFromPullRequestUrl,
  readIdleLiveAwarenessMode,
  readIdleLiveAwarenessPrUrl,
  startIdleLiveAwareness,
  type IdleLiveAwarenessController,
  type IdleLiveAwarenessObservation,
  type IdleLiveAwarenessTransition,
} from './idleLiveAwareness';

const ACTIVE_AGENT_STATUSES = new Set<SovereignAgentJobSnapshot['status']>([
  'queued',
  'provisioning',
  'running',
  'validating',
]);
const AGENT_STATE_POLL_MS = 15_000;

type IdleAwarenessAgentReader = Pick<SovereignAgentClient, 'listJobs'>;

type IdleAwarenessWindow = Window & typeof globalThis & {
  __sovereignIdleLiveAwarenessRuntimeInstalled?: boolean;
};

export function isAgentRuntimeIdleForAwareness(jobs: SovereignAgentJobSnapshot[]): boolean {
  const latest = jobs[0];
  return !latest || !ACTIVE_AGENT_STATUSES.has(latest.status);
}

function publishTelemetry(
  level: SovereignTelemetryLevel,
  label: string,
  message: string,
  details?: Record<string, string | number | boolean | null>,
): void {
  if (typeof window === 'undefined') return;
  try {
    const event = createTelemetryEvent('workflow', level, label, message, details);
    window.dispatchEvent(new CustomEvent('sovereign:telemetry-event', { detail: event }));
  } catch {
    // Awareness must never destabilize the product shell.
  }
}

function observationMessage(
  observation: IdleLiveAwarenessObservation,
  transition: IdleLiveAwarenessTransition,
): { level: SovereignTelemetryLevel; label: string; message: string } {
  if (observation.terminalGreen) {
    return {
      level: 'success',
      label: `PR #${observation.prNumber} vollständig grün`,
      message: `Head ${observation.headSha.slice(0, 12)} · ${observation.workflow.checks.length} terminale Checks · ${transition.reason}`,
    };
  }
  if (transition.reason === 'left-green') {
    return {
      level: 'warning',
      label: `PR #${observation.prNumber} nicht mehr grün`,
      message: `Head ${observation.headSha.slice(0, 12)} · Status ${observation.workflow.status}. Keine Aktion wurde ausgeführt.`,
    };
  }
  return {
    level: observation.workflow.status === 'red' ? 'error' : 'info',
    label: `PR #${observation.prNumber} beobachtet`,
    message: `Head ${observation.headSha.slice(0, 12)} · Status ${observation.workflow.status} · ${observation.workflow.checks.length} Checks.`,
  };
}

export function installIdleLiveAwarenessRuntime(): void {
  if (typeof window === 'undefined') return;
  const win = window as IdleAwarenessWindow;
  if (win.__sovereignIdleLiveAwarenessRuntimeInstalled) return;
  win.__sovereignIdleLiveAwarenessRuntimeInstalled = true;

  const config = resolveSovereignAgentConfig();
  const agentReader: IdleAwarenessAgentReader = createSovereignAgentClient({ config });
  let controller: IdleLiveAwarenessController | null = null;
  let controllerKey = '';
  let agentIdle = false;
  let syncing = false;
  let lastError = '';

  const stopWatch = (): void => {
    controller?.stop();
    controller = null;
    controllerKey = '';
  };

  const reportErrorOnce = (message: string): void => {
    if (!message || message === lastError) return;
    lastError = message;
    publishTelemetry('warning', 'Idle Live Awareness pausiert', `${message} Keine Mutation wurde ausgeführt.`);
  };

  const sync = async (): Promise<void> => {
    if (syncing) return;
    syncing = true;
    try {
      const mode = readIdleLiveAwarenessMode();
      const prUrl = readIdleLiveAwarenessPrUrl();
      const target = idleAwarenessTargetFromPullRequestUrl(prUrl);

      if (mode === 'off' || !target) {
        agentIdle = false;
        lastError = '';
        stopWatch();
        return;
      }

      if (!config.ready) {
        agentIdle = false;
        stopWatch();
        reportErrorOnce(config.reason);
        return;
      }

      let jobs: SovereignAgentJobSnapshot[];
      try {
        jobs = await agentReader.listJobs();
      } catch (error) {
        agentIdle = false;
        stopWatch();
        reportErrorOnce(error instanceof Error ? error.message : 'Agent-Status konnte nicht gelesen werden.');
        return;
      }

      agentIdle = isAgentRuntimeIdleForAwareness(jobs);
      if (!agentIdle) {
        stopWatch();
        lastError = '';
        return;
      }

      const nextKey = `${mode}:${target.prUrl}`;
      if (controller && controllerKey === nextKey) return;
      stopWatch();
      controllerKey = nextKey;
      lastError = '';
      controller = startIdleLiveAwareness({
        mode,
        target,
        isIdle: () => agentIdle,
        onObservation: (observation, transition) => {
          if (!transition.changed) return;
          const summary = observationMessage(observation, transition);
          publishTelemetry(summary.level, summary.label, summary.message, {
            prNumber: observation.prNumber,
            headSha: observation.headSha,
            terminalGreen: observation.terminalGreen,
            checkCount: observation.workflow.checks.length,
            transition: transition.reason,
          });
        },
        onError: (error) => reportErrorOnce(error.message),
      });
    } finally {
      syncing = false;
    }
  };

  const resync = (): void => { void sync(); };
  window.addEventListener('sovereign:idle-awareness-mode', resync);
  window.addEventListener('sovereign:idle-awareness-target', resync);
  window.addEventListener('storage', resync);

  void sync();
  window.setInterval(resync, AGENT_STATE_POLL_MS);
}
