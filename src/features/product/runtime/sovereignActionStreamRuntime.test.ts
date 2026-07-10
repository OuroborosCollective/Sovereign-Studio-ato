import {
  appendSovereignActionEvent,
  appendSovereignActionEvents,
  buildAgentEvidenceEvent,
  buildAgentJobCreatedEvent,
  buildAgentPatternCandidateEvent,
  buildAgentToolFinishedEvent,
  buildBlockedActionEvent,
  buildInputReceivedEvent,
  buildRepoLoadedEvent,
  buildRouteSelectionEvent,
  buildWorkerRequestEvent,
  buildWorkerResponseEvent,
  createSovereignActionStreamState,
  latestSovereignActionByRoute,
} from './sovereignActionStreamRuntime';

describe('sovereignActionStreamRuntime', () => {
  it('records every route as runtime events instead of binding the stream to Sovereign Agent only', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      buildInputReceivedEvent('Baue die UX-Verbesserung ein'),
      buildRepoLoadedEvent('Sovereign-Studio-ato · main · 500 files'),
      buildRouteSelectionEvent({ route: 'code-llm', reason: 'Patch-Erzeugung durch Code-Modell.', state: 'running' }),
      buildWorkerRequestEvent('DeepSeek R1'),
      buildWorkerResponseEvent(),
    ]);

    expect(stream.events.map((event) => event.route)).toEqual([
      'runtime',
      'repo',
      'code-llm',
      'worker',
      'worker',
      'github-access',
    ]);
    expect(stream.lastEvent).toMatchObject({
      kind: 'github_access_required',
      route: 'github-access',
      state: 'blocked',
    });
    expect(stream.lastEvent?.detail).toContain('Patch/Diff');
    expect(stream.activeRoute).toBeNull();
  });

  it('does not add result gates to normal worker chat', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      buildInputReceivedEvent('Was ist Sovereign Studio?'),
      buildWorkerRequestEvent('Mistral 7B'),
      buildWorkerResponseEvent(),
    ]);

    expect(stream.events.map((event) => event.kind)).not.toContain('github_access_required');
    expect(stream.lastEvent?.kind).toBe('llm_response_received');
    expect(stream.activeRoute).toBeNull();
  });

  it('keeps the active route while a route is running', () => {
    const stream = appendSovereignActionEvent(
      createSovereignActionStreamState(),
      buildWorkerRequestEvent('Mistral Code'),
    );

    expect(stream.activeRoute).toBe('worker');
    expect(stream.lastEvent?.state).toBe('running');
  });

  it('labels blocked route-selection events as blocked instead of chosen', () => {
    const stream = appendSovereignActionEvent(
      createSovereignActionStreamState(),
      buildRouteSelectionEvent({ route: 'sovereign-agent', reason: 'Executor fehlt.', state: 'blocked' }),
    );

    expect(stream.lastEvent?.kind).toBe('blocked');
    expect(stream.lastEvent?.label).toBe('Route blockiert: sovereign-agent');
    expect(stream.lastEvent?.label).not.toContain('gewählt');
  });

  it('turns blockers into terminal state without fabricating progress', () => {
    const stream = appendSovereignActionEvent(
      createSovereignActionStreamState(),
      buildBlockedActionEvent({
        route: 'github-access',
        label: 'GitHub-Zugang erforderlich',
        detail: 'Draft PR braucht bestätigten Schreibzugang.',
      }),
    );

    expect(stream.activeRoute).toBeNull();
    expect(stream.lastEvent?.state).toBe('blocked');
    expect(stream.lastEvent?.detail).not.toContain('%');
  });

  it('stores compact shortcut results under their exact route identities', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      { kind: 'done', route: 'files', label: 'Dateien geöffnet', state: 'done' },
      { kind: 'done', route: 'diff', label: 'Diff geöffnet', state: 'done' },
      { kind: 'done', route: 'runtime-logs', label: 'Logs geöffnet', state: 'done' },
      { kind: 'done', route: 'health', label: 'Health geprüft', state: 'done' },
      { kind: 'done', route: 'memory', label: 'Memory geprüft', state: 'done' },
      { kind: 'done', route: 'coverage', label: 'Coverage geprüft', state: 'done' },
      { kind: 'done', route: 'settings', label: 'Settings geprüft', state: 'done' },
    ]);

    const latest = latestSovereignActionByRoute(stream);
    expect(latest.files?.label).toBe('Dateien geöffnet');
    expect(latest.diff?.label).toBe('Diff geöffnet');
    expect(latest['runtime-logs']?.label).toBe('Logs geöffnet');
    expect(latest.health?.label).toBe('Health geprüft');
    expect(latest.memory?.label).toBe('Memory geprüft');
    expect(latest.coverage?.label).toBe('Coverage geprüft');
    expect(latest.settings?.label).toBe('Settings geprüft');
  });

  it('keeps latest truth per route', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      buildWorkerRequestEvent('free route'),
      buildBlockedActionEvent({
        route: 'worker',
        label: 'Worker blockiert',
        detail: 'HTTP 500',
      }),
    ]);

    expect(latestSovereignActionByRoute(stream).worker?.label).toBe('Worker blockiert');
  });

  it('worker timeout produces a terminal blocked event with activeRoute null', () => {
    const stream = appendSovereignActionEvent(
      createSovereignActionStreamState(),
      buildBlockedActionEvent({
        route: 'worker',
        label: 'Worker blockiert',
        detail: 'Worker-Timeout als Runtime-Blocker behandeln; Worker Health prüfen und nicht blind erneut senden.',
        kind: 'failed',
      }),
    );

    expect(stream.lastEvent?.state).toBe('blocked');
    expect(stream.activeRoute).toBeNull();
    expect(stream.lastEvent?.detail).not.toContain('%');
    expect(stream.lastEvent?.label).not.toBe('done');
  });

  it('activeRoute is null after any terminal event — all routes behave equally', () => {
    const routes = ['worker', 'code-llm', 'sovereign-agent', 'free-chat', 'github-patch'] as const;
    for (const route of routes) {
      const stream = appendSovereignActionEvent(
        createSovereignActionStreamState(),
        buildBlockedActionEvent({ route, label: `${route} blockiert`, detail: 'timeout' }),
      );
      expect(stream.activeRoute).toBeNull();
      expect(stream.lastEvent?.state).toBe('blocked');
    }
  });

  it('never marks a timed-out request as done', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      buildWorkerRequestEvent('DeepSeek R1'),
      buildBlockedActionEvent({
        route: 'worker',
        label: 'Worker Timeout',
        detail: 'Keine Antwort nach 30 Sekunden.',
        kind: 'failed',
      }),
    ]);

    expect(stream.lastEvent?.state).toBe('blocked');
    expect(stream.lastEvent?.state).not.toBe('done');
    expect(stream.activeRoute).toBeNull();
  });

  it('caps the event list', () => {
    const stream = appendSovereignActionEvents(
      createSovereignActionStreamState(),
      [
        buildInputReceivedEvent('eins'),
        buildInputReceivedEvent('zwei'),
        buildInputReceivedEvent('drei'),
      ],
      2,
    );

    expect(stream.events).toHaveLength(2);
    expect(stream.events[0].detail).toBe('zwei');
  });
});

describe('sovereignActionStreamRuntime hardening', () => {
  it('deduplicates a repeated identical active blocker instead of spamming events', async () => {
    const blocked = buildBlockedActionEvent({
      route: 'worker',
      label: 'Worker blockiert',
      detail: 'HTTP 500',
      kind: 'failed',
    });

    const once = appendSovereignActionEvent(createSovereignActionStreamState(), blocked);
    const twice = appendSovereignActionEvent(once, blocked);

    expect(twice.events).toHaveLength(1);
    expect(twice.lastEvent?.detail).toBe('HTTP 500');
  });

  it('does not mark allowed patch routes as done when no patch output exists', () => {
    const stream = appendSovereignActionEvent(createSovereignActionStreamState(), {
      kind: 'done',
      route: 'github-patch',
      label: 'Patch/Draft-PR Route geprüft',
      detail: 'Route erlaubt; Patchplan wartet auf Zielpfad oder Executor.',
      state: 'done',
    });

    expect(stream.lastEvent).toMatchObject({
      kind: 'patch_blocked',
      route: 'github-patch',
      state: 'blocked',
    });
    expect(stream.lastEvent?.detail).toContain('Kein terminales Done');
    expect(stream.activeRoute).toBeNull();
  });

  it('can answer local status from an active blocker without another route call', async () => {
    const { buildLocalStatusAnswerFromActionStream } = await import('./sovereignActionStreamRuntime');
    const stream = appendSovereignActionEvent(
      createSovereignActionStreamState(),
      buildBlockedActionEvent({ route: 'worker', label: 'Worker blockiert', detail: 'HTTP 500', kind: 'failed' }),
    );

    const answer = buildLocalStatusAnswerFromActionStream(stream);

    expect(answer).toContain('Status: blockiert');
    expect(answer).toContain('HTTP 500');
    expect(answer).toContain('keinen kaputten');
  });

  it('records agent lifecycle events as checked runtime state', () => {
    const started = appendSovereignActionEvent(
      createSovereignActionStreamState(),
      buildAgentJobCreatedEvent({ jobId: 'agent-1', status: 'provisioning' }),
    );

    expect(started.lastEvent).toMatchObject({
      kind: 'agent_job_created',
      route: 'agent-job',
      state: 'running',
    });
    expect(started.lastEvent?.label).toBe('Agent Job läuft');
    expect(started.activeRoute).toBe('agent-job');

    const stream = appendSovereignActionEvents(started, [
      buildAgentToolFinishedEvent({ jobId: 'agent-1', tool: 'git-status', status: 'done', detail: 'README.md changed' }),
      buildAgentEvidenceEvent({ jobId: 'agent-1', allowed: true, canPrepareDraftPr: true }),
      buildAgentPatternCandidateEvent({ jobId: 'agent-1', allowed: true, kind: 'solution' }),
    ]);

    expect(stream.events.map((event) => event.route)).toEqual([
      'agent-job',
      'agent-tool',
      'agent-evidence',
      'agent-pattern',
    ]);
    expect(stream.lastEvent?.kind).toBe('agent_pattern_candidate_ready');
    expect(stream.activeRoute).toBeNull();
  });

  it('keeps queued agent jobs waiting instead of reporting work as running', async () => {
    const { buildLocalStatusAnswerFromActionStream } = await import('./sovereignActionStreamRuntime');
    const stream = appendSovereignActionEvent(
      createSovereignActionStreamState(),
      buildAgentJobCreatedEvent({ jobId: 'agent-queued', status: 'queued' }),
    );

    expect(stream.lastEvent).toMatchObject({
      kind: 'agent_job_created',
      route: 'agent-job',
      state: 'queued',
    });
    expect(stream.activeRoute).toBe('agent-job');
    expect(buildLocalStatusAnswerFromActionStream(stream)).toContain('wartet auf bestätigte Runtime-Evidence');
    expect(buildLocalStatusAnswerFromActionStream(stream)).not.toContain('läuft');
  });

  it('keeps failed agent jobs as failed instead of downgrading them to generic blocked', () => {
    const stream = appendSovereignActionEvent(
      createSovereignActionStreamState(),
      buildAgentJobCreatedEvent({ jobId: 'agent-failed', status: 'failed', detail: 'Backend returned 500' }),
    );

    expect(stream.lastEvent).toMatchObject({
      kind: 'agent_job_created',
      route: 'agent-job',
      label: 'Agent Job fehlgeschlagen',
      state: 'failed',
    });
    expect(stream.activeRoute).toBeNull();
  });

  it('sanitizes secret-like text before it reaches the action stream', () => {
    const fakeToken = 'ghp_' + '1234567890SECRETSECRETSECRET';
    const stream = appendSovereignActionEvent(createSovereignActionStreamState(), buildAgentToolFinishedEvent({
      jobId: 'agent-secret',
      tool: 'test',
      status: 'failed',
      detail: `Authorization: Bearer ${fakeToken} should not survive`,
    }));

    expect(stream.lastEvent?.detail).toContain('[redacted]');
    expect(stream.lastEvent?.detail).not.toContain(fakeToken);
  });
});
