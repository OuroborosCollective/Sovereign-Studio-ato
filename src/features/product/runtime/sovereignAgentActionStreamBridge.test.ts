import { describe, expect, it } from 'vitest';
import {
  mapAgentJobToActionEvent,
  mapAgentPatternToActionEvent,
  mapAgentToolToActionEvents,
} from './sovereignAgentActionStreamBridge';
import { appendSovereignActionEvents, createSovereignActionStreamState } from './sovereignActionStreamRuntime';

describe('sovereignAgentActionStreamBridge', () => {
  it('maps backend agent job state to action stream event', () => {
    const event = mapAgentJobToActionEvent({
      jobId: 'agent-1',
      status: 'provisioning',
      workspaceId: 'agent-1',
    });

    expect(event.kind).toBe('agent_job_created');
    expect(event.route).toBe('agent-job');
    expect(event.sourceId).toBe('agent-1');
    expect(event.detail).toContain('Workspace');
  });

  it('maps tool result plus evidence gate to checked events', () => {
    const events = mapAgentToolToActionEvents('agent-2', {
      tool: 'git-status',
      status: 'done',
      changedFiles: ['README.md'],
      evidenceGate: {
        allowed: true,
        canPrepareDraftPr: false,
        summary: 'Changed files require diff.',
      },
    });

    expect(events.map((event) => event.kind)).toEqual(['agent_tool_finished', 'agent_result_ready']);
    expect(events[1]?.route).toBe('agent-evidence');
    expect(events[1]?.state).toBe('done');
  });

  it('maps blocked pattern gateway result without pretending remote memory wrote anything', () => {
    const event = mapAgentPatternToActionEvent('agent-3', {
      allowed: false,
      kind: null,
      summary: 'Pattern payload contains secret-like material.',
      remoteMemoryAllowed: false,
    });

    expect(event.kind).toBe('agent_pattern_candidate_ready');
    expect(event.route).toBe('agent-pattern');
    expect(event.state).toBe('blocked');
    expect(event.detail).toContain('secret-like');
  });

  it('feeds mapped events into the normal action stream', () => {
    const events = [
      mapAgentJobToActionEvent({ jobId: 'agent-4', status: 'running' }),
      ...mapAgentToolToActionEvents('agent-4', {
        tool: 'test',
        status: 'done',
        testSummary: '12 passed, 0 failed',
        evidenceGate: { allowed: true, canPrepareDraftPr: true, summary: 'Tests passed.' },
      }),
      mapAgentPatternToActionEvent('agent-4', { allowed: true, kind: 'solution', remoteMemoryAllowed: true }),
    ];

    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), events);

    expect(stream.events).toHaveLength(4);
    expect(stream.lastEvent?.route).toBe('agent-pattern');
    expect(stream.activeRoute).toBeNull();
  });
});
