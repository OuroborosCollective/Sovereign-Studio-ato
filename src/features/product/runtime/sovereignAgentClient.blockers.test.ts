import { describe, expect, it, vi } from 'vitest';
import {
  SovereignAgentClient,
  SovereignAgentRequestError,
  classifySovereignAgentHttpFailure,
} from './sovereignAgentClient';
import { resolveSovereignAgentConfig } from './sovereignAgentRuntime';

const config = resolveSovereignAgentConfig({ enabled: true, agentApiUrl: 'https://agent.example.test' });

describe('SovereignAgentClient typed HTTP blockers', () => {
  const jsonError = (payload: unknown, status: number) =>
    vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify(payload), { status }));

  it('maps HTTP 503 free_route_revolver_exhausted to an actionable quota error', async () => {
    // Arrange
    const fetcher = jsonError({ error: 'free_route_revolver_exhausted', message: 'free route revolver exhausted', statusCode: 503 }, 503);
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    // Act
    const thrown = await client.startJob({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' })
      .then(() => null, (error: unknown) => error);

    // Assert
    expect(thrown).toBeInstanceOf(SovereignAgentRequestError);
    const typed = thrown as SovereignAgentRequestError;
    expect(typed.status).toBe(503);
    expect(typed.code).toBe('free_route_revolver_exhausted');
    expect(typed.failureKind).toBe('free_route_exhausted');
    expect(typed.message).toContain('Kostenlose Route erschöpft');
    expect(typed.message).toContain('Step-Up');
    expect(typed.message).toContain('kein stiller Wechsel');
  });

  it('maps HTTP 428 step_up_required to a confirmation flow instead of an abort', async () => {
    // Arrange
    const fetcher = jsonError({ error: 'step_up_required', message: 'paid route requires step-up confirmation' }, 428);
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    // Act
    const thrown = await client.startJob({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' })
      .then(() => null, (error: unknown) => error);

    // Assert
    expect(thrown).toBeInstanceOf(SovereignAgentRequestError);
    const typed = thrown as SovereignAgentRequestError;
    expect(typed.status).toBe(428);
    expect(typed.failureKind).toBe('step_up_required');
    expect(typed.message).toContain('Step-Up');
    expect(typed.message).toContain('kein automatischer Wechsel');
  });

  it('keeps unknown failures on the generic path (fail-closed, unchanged message)', async () => {
    // Arrange
    const fetcher = jsonError({}, 500);
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    // Act
    const thrown = await client.startJob({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' })
      .then(() => null, (error: unknown) => error);

    // Assert
    expect(thrown).toBeInstanceOf(SovereignAgentRequestError);
    const typed = thrown as SovereignAgentRequestError;
    expect(typed.failureKind).toBe('generic');
    expect(typed.message).toBe('Sovereign Agent backend returned HTTP 500.');
  });

  it('keeps plain backend blocker messages on the generic path', async () => {
    // Arrange
    const fetcher = jsonError({ blocker: 'workspace unavailable' }, 409);
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    // Act / Assert
    await expect(client.startJob({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' }))
      .rejects.toThrow('workspace unavailable');
  });
});

describe('classifySovereignAgentHttpFailure', () => {
  it('classifies paid requirement codes without implying silent escalation', () => {
    // Arrange / Act
    const credits = classifySovereignAgentHttpFailure(402, 'paid_credits_required');
    const purchase = classifySovereignAgentHttpFailure(403, 'paid_purchase_required');
    const generic = classifySovereignAgentHttpFailure(500, 'boom');

    // Assert
    expect(credits.kind).toBe('paid_credits_required');
    expect(credits.guidance).toContain('kein stiller Wechsel');
    expect(purchase.kind).toBe('paid_purchase_required');
    expect(generic.kind).toBe('generic');
  });

  it('requires HTTP 503 evidence for free-route exhaustion (no false positives on generic 500s)', () => {
    // Arrange / Act / Assert
    expect(classifySovereignAgentHttpFailure(500, 'free_route_revolver_exhausted').kind).toBe('generic');
    expect(classifySovereignAgentHttpFailure(503, 'free_route_revolver_exhausted').kind).toBe('free_route_exhausted');
    expect(classifySovereignAgentHttpFailure(503, undefined, 'upstream timeout').kind).toBe('generic');
  });
});
