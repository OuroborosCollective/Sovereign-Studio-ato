import { summarizeSovereignDependencyLifecycle, type SovereignDependencyLifecycleState } from './sovereignDependencyLifecycle';

export type DependencyCoachLamp = 'green' | 'yellow' | 'red';

export interface SovereignDependencyCoachSignal {
  lamp: DependencyCoachLamp;
  title: string;
  message: string;
  action: string;
  thinking: boolean;
  source: SovereignDependencyLifecycleState['kind'];
  dependencyKey: string;
  dependencyPhase: SovereignDependencyLifecycleState['phase'];
  telemetryLevel: 'info' | 'success' | 'warning' | 'error';
  telemetryLabel: string;
  telemetryMessage: string;
}

function labelForKind(kind: SovereignDependencyLifecycleState['kind']): string {
  switch (kind) {
    case 'github': return 'GitHub';
    case 'workflow': return 'Workflow';
    case 'remote-memory': return 'Remote Memory';
    case 'pattern-memory': return 'Pattern Memory';
    case 'runtime': return 'Runtime';
    case 'telemetry': return 'Telemetry';
    default: return 'Dependency';
  }
}

export function buildSovereignDependencyCoachSignal(
  dependency: SovereignDependencyLifecycleState,
): SovereignDependencyCoachSignal {
  const label = labelForKind(dependency.kind);
  const summary = summarizeSovereignDependencyLifecycle(dependency);

  if (dependency.phase === 'blocked') {
    return {
      lamp: 'red',
      title: `${label} blockiert`,
      message: `${label}: ${dependency.message}`,
      action: 'Ursache prüfen oder später erneut versuchen.',
      thinking: false,
      source: dependency.kind,
      dependencyKey: dependency.key,
      dependencyPhase: dependency.phase,
      telemetryLevel: 'error',
      telemetryLabel: `dependency:${dependency.kind}:blocked`,
      telemetryMessage: summary,
    };
  }

  if (dependency.phase === 'degraded') {
    return {
      lamp: 'yellow',
      title: `${label} instabil`,
      message: `${label}: ${dependency.message}`,
      action: 'Weiter möglich, Ergebnis prüfen.',
      thinking: false,
      source: dependency.kind,
      dependencyKey: dependency.key,
      dependencyPhase: dependency.phase,
      telemetryLevel: 'warning',
      telemetryLabel: `dependency:${dependency.kind}:degraded`,
      telemetryMessage: summary,
    };
  }

  if (dependency.phase === 'checking' || dependency.phase === 'recovering') {
    return {
      lamp: 'green',
      title: `${label} wird geprüft`,
      message: `${label}: ${dependency.message}`,
      action: 'Bitte warten.',
      thinking: true,
      source: dependency.kind,
      dependencyKey: dependency.key,
      dependencyPhase: dependency.phase,
      telemetryLevel: 'info',
      telemetryLabel: `dependency:${dependency.kind}:${dependency.phase}`,
      telemetryMessage: summary,
    };
  }

  return {
    lamp: 'green',
    title: `${label} bereit`,
    message: `${label}: ${dependency.message}`,
    action: 'Weiterarbeiten.',
    thinking: false,
    source: dependency.kind,
    dependencyKey: dependency.key,
    dependencyPhase: dependency.phase,
    telemetryLevel: dependency.phase === 'ready' ? 'success' : 'info',
    telemetryLabel: `dependency:${dependency.kind}:${dependency.phase}`,
    telemetryMessage: summary,
  };
}

export function publishSovereignDependencyCoachSignal(
  dependency: SovereignDependencyLifecycleState,
  nowMs = Date.now(),
): SovereignDependencyCoachSignal {
  const signal = buildSovereignDependencyCoachSignal(dependency);

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('sovereign:dependency-lifecycle-state', { detail: { ...signal, updatedAt: nowMs } }));
    window.dispatchEvent(new CustomEvent('sovereign:dependency-telemetry-event', {
      detail: {
        stage: 'runtime',
        level: signal.telemetryLevel,
        label: signal.telemetryLabel,
        message: signal.telemetryMessage,
        details: {
          dependencyKey: signal.dependencyKey,
          dependencyPhase: signal.dependencyPhase,
          dependencySource: signal.source,
        },
      },
    }));
    window.dispatchEvent(new CustomEvent('sovereign:runtime-coach-state', {
      detail: {
        lamp: signal.lamp,
        title: signal.title,
        message: signal.message,
        action: signal.action,
        thinking: signal.thinking,
        source: signal.source,
        updatedAt: nowMs,
      },
    }));
  }

  return signal;
}
