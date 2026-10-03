import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { SovereignProductionAdapter } from './adapter/repository-bound-adapter';
import { RuntimeMonitor } from './components/RuntimeMonitor/RuntimeMonitor';

const config = { enabled: true, deploymentMode: 'sovereign-agent-backend' as const,
  agentApiUrl: 'https://agent.example.test', ready: true, reason: 'ready' };
const jobId = 'agent-live-evidence';
const observedAt = '2026-10-02T21:30:00Z';
const eventAt = '2026-10-02T21:10:26Z';
function response() {
  return { job: { jobId, status: 'running', executor: 'sovereign-local-runner', workspaceId: jobId,
    externalRef: 'sovereign-local-runner:claim:submit:fixture', changedFiles: [],
    createdAt: '2026-10-02T21:10:23Z', updatedAt: eventAt, serverObservedAt: observedAt,
    events: [{ at: eventAt, stage: 'sovereign_local_execution_queued', level: 'info', message: 'Queued on server.' }],
    runtimeEvidence: { jobId, readbackState: 'live', events: [{ eventId: 'event-runtime',
      runId: `repo-${jobId}`, evidenceId: 'evidence-runtime', evidenceSha256: 'a'.repeat(64),
      agentId: 'free_single_agent', source: 'agents-sdk', stage: 'single_agent_started', status: 'RUNNING',
      summary: 'Actual persisted runtime phase.', at: eventAt, nextAction: 'WAIT_FOR_AGENT' }] } } };
}
async function read(body = response()) {
  const fetcher = vi.fn(async (url: RequestInfo | URL) => String(url).endsWith(`/${jobId}`)
    ? new Response(JSON.stringify(body)) : new Response('{}', { status: 404 }));
  return new SovereignProductionAdapter(fetcher as typeof fetch, config).getJob(jobId);
}

describe('Runtime Monitor canonical runtime evidence', () => {
  beforeAll(() => { Element.prototype.scrollIntoView = vi.fn(); });
  it('preserves server timestamps instead of moving persisted progress forward on every poll', async () => {
    const job = await read();
    expect(job.createdAt).toBe('2026-10-02T21:10:23Z');
    expect(job.updatedAt).toBe(eventAt);
    expect(job.logs.join('\n')).toContain(eventAt.replace('Z', '.000Z'));
  });

  it('shows persisted SDK telemetry with exact event, evidence and hash provenance', async () => {
    const job = await read();
    render(<RuntimeMonitor job={job} />);
    expect(screen.getByText(/Actual persisted runtime phase/)).toBeVisible();
    fireEvent.click(screen.getByText(/event event-runtime/));
    expect(screen.getByText(/evidence-runtime/)).toBeVisible();
    expect(screen.getByText(/a{64}/)).toBeVisible();
    expect(screen.getByText(/event-runtime/)).toBeVisible();
  });

  it('distinguishes a successful poll from recent runtime activity and exposes a claimed submit', async () => {
    const job = await read();
    render(<RuntimeMonitor job={job} isPolling />);
    expect(screen.getByText(/FETCHING READBACK/)).toBeVisible();
    expect(screen.queryByText('LIVE READBACK')).toBeNull();
    expect(screen.getByText(/1174s without a persisted event/)).toBeVisible();
    expect(screen.getByText(/SUBMIT CLAIMED/)).toBeVisible();
  });

  it('retains the last evidence and marks it unavailable when polling fails', async () => {
    const job = await read();
    render(<RuntimeMonitor job={job} readbackError="HTTP 503" />);
    expect(screen.getByRole('alert')).toHaveTextContent('HTTP 503');
    expect(screen.getByText(/Actual persisted runtime phase/)).toBeVisible();
  });

  it('does not manufacture missing events or silently label unavailable SDK evidence live', async () => {
    const body = response();
    body.job.events = [{ stage: 'missing_timestamp', message: 'Must not gain a fake timestamp.' } as never];
    body.job.runtimeEvidence = { jobId, readbackState: 'unavailable', error: 'Runtime evidence readback failed (DatabaseError).', events: [] } as never;
    const job = await read(body);
    render(<RuntimeMonitor job={job} />);
    expect(job.logs.join('\n')).not.toContain('Must not gain a fake timestamp');
    expect(screen.getByRole('alert')).toHaveTextContent('DatabaseError');
    expect(screen.queryByText(/Actual persisted runtime phase/)).toBeNull();
  });

  it('rejects a different job rather than attaching its runtime telemetry', async () => {
    const body = response();
    body.job.jobId = 'agent-other';
    await expect(read(body)).rejects.toThrow(/identity mismatch/i);
  });

  it('observes real worker heartbeats without counting them as progress or duplicating status lines', async () => {
    const body = response();
    body.job.runtimeEvidence.events.push({ ...body.job.runtimeEvidence.events[0],
      eventId: 'event-heartbeat', evidenceId: 'evidence-heartbeat', stage: 'sovereign_executor_heartbeat',
      at: '2026-10-02T21:29:59Z', summary: 'Invocation active; no progress implied.', heartbeatCurrent: true } as never);
    const job = await read(body);
    render(<RuntimeMonitor job={job} />);
    expect(job.lastEventAt).toBe(eventAt.replace('Z', '.000Z'));
    expect(job.persistedEventCount).toBe(2);
    expect(screen.getByText(/Worker heartbeat:.*1s old/)).toBeVisible();
    expect(screen.getByText(/1174s without a persisted event/)).toBeVisible();
    expect(screen.queryByText(/Invocation active/)).toBeNull();
  });

  it('does not attach a heartbeat from a previous claim to current executor liveness', async () => {
    const body = response();
    body.job.runtimeEvidence.events.push({ ...body.job.runtimeEvidence.events[0],
      eventId: 'event-old-heartbeat', stage: 'sovereign_executor_heartbeat', heartbeatCurrent: false } as never);
    const job = await read(body);
    render(<RuntimeMonitor job={job} />);
    expect(job.lastHeartbeatAt).toBeUndefined();
    expect(screen.getByText(/Worker heartbeat: UNOBSERVED/)).toBeVisible();
  });

  it('flags stale worker heartbeats without changing the backend job phase', async () => {
    const body = response();
    body.job.runtimeEvidence.events.push({ ...body.job.runtimeEvidence.events[0],
      eventId: 'event-stale-heartbeat', stage: 'sovereign_executor_heartbeat', heartbeatCurrent: true } as never);
    const job = await read(body);
    render(<RuntimeMonitor job={job} />);
    expect(screen.getByText(/Worker heartbeat is stale/)).toBeVisible();
    expect(job.phase).toBe('EXECUTING');
  });

  it.each(['evidenceSha256', 'at', 'source'])('marks contradicted %s evidence unavailable', async (field) => {
    const body = response();
    (body.job.runtimeEvidence.events[0] as Record<string, unknown>)[field] = 'invalid';
    const job = await read(body);
    render(<RuntimeMonitor job={job} />);
    expect(screen.getByRole('alert')).toHaveTextContent(/incomplete identity, hash or timestamp/);
    expect(screen.queryByText(/Actual persisted runtime phase/)).toBeNull();
  });

  it('ages heartbeat freshness even when no further readback arrives', async () => {
    const clock = vi.spyOn(performance, 'now').mockReturnValue(200000);
    try {
      const body = response();
      body.job.runtimeEvidence.events.push({ ...body.job.runtimeEvidence.events[0],
        eventId: 'event-heartbeat', stage: 'sovereign_executor_heartbeat', at: '2026-10-02T21:29:59Z', heartbeatCurrent: true } as never);
      const job = await read(body);
      const view = render(<RuntimeMonitor job={job} />);
      expect(screen.getByText(/Worker heartbeat:.*1s old/)).toBeVisible();
      clock.mockReturnValue(330000);
      view.rerender(<RuntimeMonitor job={job} readbackError="HTTP 503" />);
      expect(screen.getByText(/Worker heartbeat:.*131s old/)).toBeVisible();
      expect(screen.getByText(/Worker heartbeat is stale/)).toBeVisible();
      expect(job.serverObservedAt).toBe(observedAt);
      expect(job.updatedAt).toBe(eventAt);
    } finally { clock.mockRestore(); }
  });
});
