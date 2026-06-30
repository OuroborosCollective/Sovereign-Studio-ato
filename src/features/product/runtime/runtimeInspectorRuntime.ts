import type { DevChatRepoSnapshot } from './devChatWorkerBridge';

export interface RoutingDecisionSnapshot {
  readonly tier: string;
  readonly modelLabel: string;
}

export interface RuntimeInspectorState {
  readonly patternLine: string;
  readonly routingLine: string;
  readonly repoLine: string;
}

export function buildRuntimeInspectorState(args: {
  readonly repoSnapshot: DevChatRepoSnapshot | null;
  readonly routingDecisions: readonly RoutingDecisionSnapshot[];
  readonly workerBlocked: boolean;
}): RuntimeInspectorState {
  const routingCounts = args.routingDecisions.reduce<Record<string, number>>((acc, decision) => {
    acc[decision.tier] = (acc[decision.tier] ?? 0) + 1;
    return acc;
  }, {});
  const routingLine = Object.keys(routingCounts).length
    ? Object.entries(routingCounts).map(([tier, count]) => `${tier}:${count}`).join(' · ')
    : 'Keine Routing-Entscheidung.';
  const repoLine = args.repoSnapshot
    ? `${args.repoSnapshot.owner}/${args.repoSnapshot.repo} · ${args.repoSnapshot.branch} · ${args.repoSnapshot.fileCount} Einträge${args.repoSnapshot.truncated ? ' · truncated' : ''}`
    : 'Repo-Snapshot fehlt.';
  return {
    patternLine: args.workerBlocked ? 'Worker blockiert · Pattern bleibt Anzeige-State.' : 'Kein Pattern-Memory-Snapshot im lokalen Chat-State.',
    routingLine,
    repoLine,
  };
}
