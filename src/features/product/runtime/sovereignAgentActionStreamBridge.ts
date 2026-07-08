import type { SovereignActionEventInput } from './sovereignActionStreamRuntime';
import {
  buildAgentEvidenceEvent,
  buildAgentJobCreatedEvent,
  buildAgentPatternCandidateEvent,
  buildAgentToolFinishedEvent,
} from './sovereignActionStreamRuntime';

export interface SovereignAgentJobApiState {
  readonly jobId: string;
  readonly status: string;
  readonly blocker?: string | null;
  readonly workspaceId?: string | null;
  readonly changedFiles?: readonly string[];
  readonly diffSummary?: string | null;
  readonly testSummary?: string | null;
  readonly prState?: string | null;
}

export interface SovereignAgentToolApiState {
  readonly tool?: string | null;
  readonly status?: string | null;
  readonly blocker?: string | null;
  readonly changedFiles?: readonly string[];
  readonly diffSummary?: string | null;
  readonly testSummary?: string | null;
  readonly evidenceGate?: {
    readonly passed?: boolean;
    readonly allowed?: boolean;
    readonly canPrepareDraftPr?: boolean;
    readonly reason?: string;
    readonly summary?: string;
  } | null;
}

export interface SovereignAgentPatternApiState {
  readonly allowed: boolean;
  readonly kind?: 'solution' | 'blocker' | null;
  readonly summary?: string | null;
  readonly remoteMemoryAllowed?: boolean;
}

function hasEvidence(tool: SovereignAgentToolApiState): boolean {
  return Boolean(
    tool.changedFiles?.length
      || tool.diffSummary?.trim()
      || tool.testSummary?.trim()
      || tool.blocker?.trim(),
  );
}

export function mapAgentJobToActionEvent(job: SovereignAgentJobApiState): SovereignActionEventInput {
  return buildAgentJobCreatedEvent({
    jobId: job.jobId,
    status: job.status,
    detail: job.blocker
      ? `Agent Job ${job.jobId} blockiert: ${job.blocker}`
      : `Agent Job ${job.jobId} Status: ${job.status}${job.workspaceId ? ` · Workspace: ${job.workspaceId}` : ''}`,
  });
}

export function mapAgentToolToActionEvents(
  jobId: string,
  tool: SovereignAgentToolApiState,
): readonly SovereignActionEventInput[] {
  const status = tool.status === 'done' ? 'done' : tool.status === 'blocked' ? 'blocked' : tool.status === 'failed' ? 'failed' : 'error';
  const events: SovereignActionEventInput[] = [
    buildAgentToolFinishedEvent({
      jobId,
      tool: tool.tool ?? 'unknown',
      status,
      detail: tool.blocker
        ? `Agent Tool blockiert: ${tool.blocker}`
        : `Agent Tool ${tool.tool ?? 'unknown'} Status: ${status}`,
    }),
  ];

  const hasGate = Boolean(tool.evidenceGate);
  const gateAllowed = tool.evidenceGate?.allowed ?? tool.evidenceGate?.passed ?? false;
  if (hasGate || hasEvidence(tool)) {
    events.push(buildAgentEvidenceEvent({
      jobId,
      allowed: hasGate ? gateAllowed : hasEvidence(tool),
      canPrepareDraftPr: tool.evidenceGate?.canPrepareDraftPr,
      detail: tool.evidenceGate?.summary ?? tool.evidenceGate?.reason ?? (hasEvidence(tool)
        ? 'Agent Tool lieferte Runtime-Evidence.'
        : 'Agent Tool lieferte keine Runtime-Evidence.'),
    }));
  }

  return events;
}

export function mapAgentPatternToActionEvent(
  jobId: string,
  pattern: SovereignAgentPatternApiState,
): SovereignActionEventInput {
  return buildAgentPatternCandidateEvent({
    jobId,
    allowed: pattern.allowed,
    kind: pattern.kind,
    detail: pattern.summary ?? (pattern.allowed
      ? `Pattern Gateway akzeptiert Kandidat. Remote Memory erlaubt: ${pattern.remoteMemoryAllowed ? 'ja' : 'nein'}.`
      : 'Pattern Gateway blockiert Kandidat.'),
  });
}
