import { afterEach, describe, expect, it, vi } from 'vitest';
import { SovereignAgentClient } from './sovereignAgentClient';
import { resolveSovereignAgentConfig } from './sovereignAgentRuntime';

const config = resolveSovereignAgentConfig({ enabled: true, agentApiUrl: 'https://agent.example.test' });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('SovereignAgentClient', () => {
  it('binds the default global fetch receiver before starting repository execution', async () => {
    let callCount = 0;
    vi.stubGlobal('fetch', async function receiverSensitiveFetch(
      this: typeof globalThis,
      _url: RequestInfo | URL,
      _init?: RequestInit,
    ): Promise<Response> {
      if (this !== globalThis) throw new TypeError('Illegal invocation');
      callCount += 1;
      if (callCount === 1) {
        return new Response(JSON.stringify({
          ok: true,
          status: 'COMPLETED',
          jobId: 'job-bound-fetch',
          workspaceId: 'ws-bound-fetch',
        }), { status: 200 });
      }
      return new Response(JSON.stringify({
        job: {
          id: 'job-bound-fetch',
          workspaceId: 'ws-bound-fetch',
          status: 'completed',
          repoUrl: 'https://github.com/acme/repo',
          branch: 'main',
          changedFiles: [],
          events: [],
        },
      }), { status: 200 });
    });

    const client = new SovereignAgentClient({ config });
    const snapshot = await client.startRepositoryExecution({
      repoUrl: 'https://github.com/acme/repo',
      mission: 'Repair the runtime transport.',
    });

    expect(callCount).toBe(2);
    expect(snapshot).toMatchObject({ jobId: 'job-bound-fetch', workspaceId: 'ws-bound-fetch', status: 'completed' });
  });
  it('starts jobs only through /api/user/agent/jobs', async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ job: { id: 'job-1', workspaceId: 'ws-1', status: 'queued', changedFiles: [], events: [] } }), { status: 201 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch, now: () => 10 });
    const snapshot = await client.startJob({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' });
    expect(fetcher).toHaveBeenCalledWith('https://agent.example.test/api/user/agent/jobs', expect.objectContaining({ method: 'POST', credentials: 'include' }));
    expect(snapshot).toMatchObject({ jobId: 'job-1', runtimeId: 'ws-1', workspaceId: 'ws-1' });
  });
  it('polls and cancels through the same internal route family', async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ id: 'job-1', status: 'running', changedFiles: [], events: [] }), { status: 200 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });
    await client.getJob('job-1');
    await client.cancelJob('job-1');
    expect(fetcher.mock.calls[0][0]).toBe('https://agent.example.test/api/user/agent/jobs/job-1');
    expect(fetcher.mock.calls[1][0]).toBe('https://agent.example.test/api/user/agent/jobs/job-1/cancel');
  });
  it('surfaces backend blockers without compatibility aliases', async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ blocker: 'workspace unavailable' }), { status: 409 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });
    await expect(client.startJob({ repoUrl: 'https://github.com/acme/repo', mission: 'Fix tests' })).rejects.toThrow('workspace unavailable');
  });
  it('carries staged changes and ephemeral GitHub access through the real Draft-PR route family', async () => {
    const calls: string[] = [];
    const requestInits: RequestInit[] = [];
    const githubAccessToken = 'not-a-real-github-token';
    const responses = [
      {
        ok: true,
        job: {
          id: 'job-flow',
          workspaceId: 'ws-flow',
          status: 'completed',
          repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
          branch: 'main',
          changedFiles: ['src/App.tsx'],
          events: [],
        },
        toolchain: {
          evidenceHash: 'a'.repeat(64),
          failureFamilies: [{
            code: 'typescript_contract_mismatch',
            title: 'TypeScript contract mismatch',
            severity: 'high',
            score: 3,
            checks: ['run targeted typecheck'],
          }],
          nextLogicalFailures: [1, 2, 3, 4].map(index => ({
            fromFamily: 'typescript_contract_mismatch',
            prediction: `Neighbouring runtime risk ${index}`,
            checkNext: `check ${index}`,
          })),
        },
      },
      {
        ok: true,
        jobId: 'job-flow',
        draftPrPreparation: {
          allowed: true,
          decision: 'ready',
          canCreateDraftPr: true,
          blockers: [],
        },
        candidateId: 'candidate-1',
        candidateCreated: true,
        patternLearning: {
          allowed: true,
          decision: 'accepted',
        },
        vectorMemory: {
          stored: true,
          storage: 'pgvector',
        },
      },
      {
        ok: true,
        jobId: 'job-flow',
        draftPrCreate: {
          allowed: true,
          status: 'created',
          prUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/999',
          headSha: 'd'.repeat(40),
          publishedHeadSha: 'd'.repeat(40),
          readbackHeadSha: 'd'.repeat(40),
          prNumber: 999,
          draftVerified: true,
          prStateVerified: 'open',
          headBranch: 'sovereign/job-flow',
          baseBranch: 'main',
          readbackVerified: true,
          checksReadbackVerified: true,
          ciState: 'success',
          checkRunCount: 2,
          checksPendingCount: 0,
          checksSuccessCount: 2,
          checksFailureCount: 0,
          statusContextCount: 1,
        },
      },
      {
        id: 'job-flow',
        workspaceId: 'ws-flow',
        status: 'completed',
        repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
        branch: 'main',
        draftPrUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/999',
        changedFiles: ['src/App.tsx'],
        events: [],
      },
    ];
    const fetcher = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      calls.push(String(url));
      requestInits.push(init || {});
      return new Response(JSON.stringify(responses.shift()), { status: 200 });
    });
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch, now: () => 10 });

    const job = await client.startToolchainJob({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      expectedHeadSha: 'b'.repeat(40),
      mission: 'Fix TypeScript and create a Draft PR.',
      evidenceText: 'TS2339 Property paymentMethods does not exist',
      stagedFiles: [{ path: 'README.md', content: '# Updated\n', baseContent: '# Original\n' }],
      testCommand: '  git diff --check  ',
      githubAccessToken: `  ${githubAccessToken}  `,
    });
    const preparation = await client.prepareDraftPr(job.jobId || '');
    const creation = await client.createDraftPr(job.jobId || '', `  ${githubAccessToken}  `);
    const finalJob = await client.getJob(job.jobId || '');

    expect(job.events.filter(event => event.stage === 'toolchain_predictive_handoff')).toHaveLength(4);
    expect(preparation.draftPrPreparation.allowed).toBe(true);
    expect(preparation.learningEvidence).toEqual({
      candidateId: 'candidate-1',
      candidateCreated: true,
      allowed: true,
      decision: 'accepted',
      vectorStored: true,
      vectorStorage: 'pgvector',
    });
    expect(creation.draftPrCreate.prUrl).toContain('/pull/999');
    expect(finalJob.draftPrUrl).toContain('/pull/999');
    expect(JSON.parse(String(requestInits[0].body))).toMatchObject({
      stagedFiles: [{ path: 'README.md', content: '# Updated\n', baseContent: '# Original\n' }],
      testCommand: 'git diff --check',
      githubAccessToken,
      cloneRepo: true,
      provisionWorkspace: true,
      expectedHeadSha: 'b'.repeat(40),
    });
    expect(JSON.parse(String(requestInits[2].body))).toEqual({ githubAccessToken });
    expect(calls).toEqual([
      'https://agent.example.test/api/user/agent/toolchain/handoff',
      'https://agent.example.test/api/user/agent/jobs/job-flow/draft-pr/prepare',
      'https://agent.example.test/api/user/agent/jobs/job-flow/draft-pr/create',
      'https://agent.example.test/api/user/agent/jobs/job-flow',
    ]);
  });

  it('starts repository repair through the executable swarm route and reads the linked job', async () => {
    const requestInits: RequestInit[] = [];
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      requestInits.push(init || {});
      if (requestInits.length === 1) {
        return new Response(JSON.stringify({
          ok: true,
          status: 'COMPLETED',
          jobId: 'job-repository',
          workspaceId: 'ws-repository',
        }), { status: 200 });
      }
      return new Response(JSON.stringify({
        job: {
          id: 'job-repository',
          workspaceId: 'ws-repository',
          status: 'completed',
          repoUrl: 'https://github.com/acme/repo',
          branch: 'main',
          changedFiles: ['src/App.tsx'],
          events: [],
        },
      }), { status: 200 });
    });
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    const snapshot = await client.startRepositoryExecution({
      repoUrl: 'https://github.com/acme/repo',
      branch: 'main',
      expectedHeadSha: 'c'.repeat(40),
      mission: 'Repair one causal failure and stop at Draft PR.',
      evidenceText: 'Observed runtime blocker.',
      githubAccessToken: 'not-a-real-github-token',
    });

    expect(fetcher.mock.calls[0][0]).toBe('https://agent.example.test/api/user/agent/swarm/run');
    expect(fetcher.mock.calls[1][0]).toBe('https://agent.example.test/api/user/agent/jobs/job-repository');
    expect(JSON.parse(String(requestInits[0].body))).toMatchObject({
      mode: 'auto',
      intentMode: 'repository_execution',
      repositoryUrl: 'https://github.com/acme/repo',
      repositoryBranch: 'main',
      expectedHeadSha: 'c'.repeat(40),
      githubAccessToken: 'not-a-real-github-token',
    });
    expect(snapshot).toMatchObject({
      jobId: 'job-repository',
      workspaceId: 'ws-repository',
      status: 'completed',
      changedFiles: ['src/App.tsx'],
    });
  });

  it('lists persisted jobs for app reinstall recovery', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({
      jobs: [{ id: 'job-latest', workspaceId: 'ws-latest', status: 'running', changedFiles: [], events: [] }],
    }), { status: 200 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    const jobs = await client.listJobs();

    expect(fetcher).toHaveBeenCalledWith(
      'https://agent.example.test/api/user/agent/jobs?limit=20',
      expect.objectContaining({ method: 'GET', credentials: 'include' }),
    );
    expect(jobs).toMatchObject([{ jobId: 'job-latest', workspaceId: 'ws-latest', status: 'running' }]);
  });

  it('reads only canonical session-bound visual projections from the owned job route', async () => {
    const canonical = {
      schemaVersion: 'sovereign.visual-projection-event.v1',
      projectionId: 'visual-1',
      eventId: 'visual-1',
      eventType: 'TERMINAL_VIEW_PROJECTED',
      sessionId: 'livews-1234567890abcdef12345678',
      sessionBindingHash: 'a'.repeat(64),
      attemptId: 'attempt-1234567890abcdef12345678',
      runId: 'run-1',
      taskId: 'task-1',
      workspaceId: 'ws-1',
      actionId: 'action-1',
      sourceKind: 'PROCESS',
      projectionKind: 'TERMINAL',
      projectionState: 'REQUESTED',
      repositoryHead: 'b'.repeat(40),
      sourceReceiptRef: 'c'.repeat(64),
      sourceIdentityHash: 'd'.repeat(64),
      payload: { chunk: '1 failed', exitCode: 1, processState: 'EXITED' },
      projectionHash: 'e'.repeat(64),
      authoritative: false,
      claim: 'OBSERVED',
    };
    const legacy = { ...canonical, schemaVersion: 'sovereign.live-workspace-projection.v1', projectionId: 'legacy-1' };
    const fetcher = vi.fn(async () => new Response(JSON.stringify({
      jobId: 'job-1',
      workspaceId: 'ws-1',
      sessionBindingHash: 'a'.repeat(64),
      attemptId: 'attempt-1234567890abcdef12345678',
      projections: [legacy, canonical],
    }), { status: 200 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    const projections = await client.getProjections('job-1');

    expect(fetcher).toHaveBeenCalledWith(
      'https://agent.example.test/api/user/agent/jobs/job-1/projections?limit=100',
      expect.objectContaining({ method: 'GET', credentials: 'include' }),
    );
    expect(projections).toHaveLength(1);
    expect(projections[0]).toMatchObject({
      projectionId: 'visual-1',
      jobId: 'job-1',
      workspaceId: 'ws-1',
      sessionBindingHash: 'a'.repeat(64),
      attemptId: 'attempt-1234567890abcdef12345678',
      projectionKind: 'TERMINAL',
      projectionState: 'REQUESTED',
      payload: { exitCode: 1 },
      authoritative: false,
      claim: 'OBSERVED',
    });

    const driftFetcher = vi.fn(async () => new Response(JSON.stringify({
      jobId: 'job-1',
      workspaceId: 'ws-1',
      sessionBindingHash: 'a'.repeat(64),
      attemptId: 'attempt-1234567890abcdef12345678',
      projections: [
        { ...canonical, projectionId: 'foreign-job', jobId: 'job-other' },
        { ...canonical, projectionId: 'foreign-workspace', workspaceId: 'ws-other' },
        { ...canonical, projectionId: 'foreign-session', sessionBindingHash: '8'.repeat(64) },
        { ...canonical, projectionId: 'foreign-attempt', attemptId: 'attempt-other' },
      ],
    }), { status: 200 }));
    const driftClient = new SovereignAgentClient({
      config,
      fetcher: driftFetcher as unknown as typeof fetch,
    });

    expect(await driftClient.getProjections('job-1')).toEqual([]);
  });

  it('rejects a projection response whose authenticated envelope belongs to another job', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({
      jobId: 'job-other',
      workspaceId: 'ws-1',
      projections: [],
    }), { status: 200 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    await expect(client.getProjections('job-1')).rejects.toThrow(
      'Sovereign Live Workspace projections returned no exact job/workspace envelope binding.',
    );
  });

  it('reads a desktop frame only with OBSERVED PNG and SHA-256 evidence', async () => {
    const frameHash = '9'.repeat(64);
    const fetcher = vi.fn(async () => new Response(new Uint8Array([137, 80, 78, 71]), {
      status: 200,
      headers: {
        'Content-Type': 'image/png',
        'X-Sovereign-Observation': 'OBSERVED',
        'X-Sovereign-Frame-Hash': frameHash,
      },
    }));
    const client = new SovereignAgentClient({
      config,
      fetcher: fetcher as unknown as typeof fetch,
      now: () => 42,
    });

    const frame = await client.getDesktopFrame('job-1');

    expect(fetcher).toHaveBeenCalledWith(
      'https://agent.example.test/api/user/agent/jobs/job-1/live-workspace/desktop/frame',
      expect.objectContaining({ method: 'GET', credentials: 'include', cache: 'no-store' }),
    );
    expect(frame.frameHash).toBe(frameHash);
    expect(frame.observedAt).toBe(42);
    expect(frame.blob.size).toBeGreaterThan(0);
  });

  it('rejects a desktop response that lacks observation/hash evidence', async () => {
    const fetcher = vi.fn(async () => new Response(new Uint8Array([137, 80, 78, 71]), {
      status: 200,
      headers: { 'Content-Type': 'image/png' },
    }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    await expect(client.getDesktopFrame('job-1')).rejects.toThrow(/OBSERVED PNG\/hash evidence/);
  });

  it('reads only typed claim-granular evidence anchors and rejects frame-based verified claims', async () => {
    const canonical = {
      schemaVersion: 'sovereign.workspace-evidence-anchor.v1',
      anchorId: `evidence-${'a'.repeat(24)}`,
      claimKind: 'TEST_EXECUTION_RECEIPT_MATCH',
      verdict: 'VERIFIED',
      sourceVerdict: 'VERIFIED',
      sessionBindingHash: 'b'.repeat(64),
      runId: 'run-1',
      taskId: 'task-1',
      attemptId: 'attempt-1',
      actionId: 'tool-call-1',
      scope: `tool=test;input=${'c'.repeat(64)};effect=read`,
      sourceKind: 'AGENT_RUN_RECEIPT',
      sourceRefs: ['d'.repeat(64)],
      repositoryRevision: 'e'.repeat(40),
      observedAt: '2026-08-23T03:30:00Z',
      freshnessReasons: [],
      evidenceHash: 'f'.repeat(64),
      authoritative: false,
    };
    const frameClaim = { ...canonical, anchorId: `evidence-${'1'.repeat(24)}`, sourceKind: 'FRAME_OBSERVATION' };
    const generic = { ...canonical, anchorId: `evidence-${'2'.repeat(24)}`, claimKind: 'EVERYTHING_WORKS' };
    const fetcher = vi.fn(async () => new Response(JSON.stringify({
      jobId: 'job-1',
      workspaceId: 'ws-1',
      active: true,
      sessionBindingHash: 'b'.repeat(64),
      attemptId: 'attempt-1',
      evidenceAnchors: [frameClaim, generic, canonical],
    }), { status: 200 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });

    const anchors = await client.getEvidenceAnchors('job-1');

    expect(fetcher).toHaveBeenCalledWith(
      'https://agent.example.test/api/user/agent/jobs/job-1/evidence-anchors?limit=100',
      expect.objectContaining({ method: 'GET', credentials: 'include' }),
    );
    expect(anchors).toHaveLength(1);
    expect(anchors[0]).toMatchObject({
      jobId: 'job-1',
      workspaceId: 'ws-1',
      claimKind: 'TEST_EXECUTION_RECEIPT_MATCH',
      verdict: 'VERIFIED',
      sourceKind: 'AGENT_RUN_RECEIPT',
      repositoryRevision: 'e'.repeat(40),
      authoritative: false,
    });

    const driftFetcher = vi.fn(async () => new Response(JSON.stringify({
      jobId: 'job-1',
      workspaceId: 'ws-1',
      active: true,
      sessionBindingHash: 'b'.repeat(64),
      attemptId: 'attempt-1',
      evidenceAnchors: [
        { ...canonical, anchorId: `evidence-${'3'.repeat(24)}`, jobId: 'job-other' },
        { ...canonical, anchorId: `evidence-${'4'.repeat(24)}`, workspaceId: 'ws-other' },
        { ...canonical, anchorId: `evidence-${'5'.repeat(24)}`, sessionBindingHash: '6'.repeat(64) },
        { ...canonical, anchorId: `evidence-${'7'.repeat(24)}`, attemptId: 'attempt-other' },
      ],
    }), { status: 200 }));
    const driftClient = new SovereignAgentClient({ config, fetcher: driftFetcher as unknown as typeof fetch });
    expect(await driftClient.getEvidenceAnchors('job-1')).toEqual([]);

    const wrongEnvelopeFetcher = vi.fn(async () => new Response(JSON.stringify({
      jobId: 'job-old',
      workspaceId: 'ws-1',
      active: true,
      sessionBindingHash: 'b'.repeat(64),
      attemptId: 'attempt-1',
      evidenceAnchors: [canonical],
    }), { status: 200 }));
    const wrongEnvelopeClient = new SovereignAgentClient({
      config,
      fetcher: wrongEnvelopeFetcher as unknown as typeof fetch,
    });
    await expect(wrongEnvelopeClient.getEvidenceAnchors('job-1')).rejects.toThrow(
      'Sovereign Live Workspace evidence returned no exact job/workspace envelope binding.',
    );

    const inactiveFetcher = vi.fn(async () => new Response(JSON.stringify({
      jobId: 'job-1',
      workspaceId: 'ws-1',
      active: false,
      sessionBindingHash: 'b'.repeat(64),
      attemptId: 'attempt-1',
      evidenceAnchors: [{
        ...canonical,
        anchorId: `evidence-${'8'.repeat(24)}`,
        verdict: 'STALE',
        freshnessReasons: ['SESSION_NOT_ACTIVE'],
      }],
    }), { status: 200 }));
    const inactiveClient = new SovereignAgentClient({ config, fetcher: inactiveFetcher as unknown as typeof fetch });
    expect(await inactiveClient.getEvidenceAnchors('job-1')).toMatchObject([{
      jobId: 'job-1',
      workspaceId: 'ws-1',
      verdict: 'STALE',
      freshnessReasons: ['SESSION_NOT_ACTIVE'],
    }]);
  });

  it('runs the deterministic janitor only through the owned job tool route', async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({
      ok: true,
      jobId: 'job-1',
      tool: {
        status: 'done',
        stdout: 'Janitor scan completed: 1 finding(s). No files were changed.',
        changedFiles: [],
        metadata: { findings: [{ ruleId: 'PY-UNSAFE-SHELL' }], writeAction: false },
      },
    }), { status: 200 }));
    const client = new SovereignAgentClient({ config, fetcher: fetcher as unknown as typeof fetch });
    const response = await client.runJanitor('job-1', { mode: 'scan', maxFindings: 10 });
    expect(fetcher).toHaveBeenCalledWith(
      'https://agent.example.test/api/user/agent/jobs/job-1/tools/janitor',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    );
    expect(response).toMatchObject({ ok: true, jobId: 'job-1', tool: { status: 'done', changedFiles: [] } });
  });
});
