import {
  appendSovereignActionEvent,
  appendSovereignActionEvents,
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
  it('records every route as runtime events instead of binding the stream to OpenHands only', () => {
    const stream = appendSovereignActionEvents(createSovereignActionStreamState(), [
      buildInputReceivedEvent('Baue die UX-Verbesserung ein'),
      buildRepoLoadedEvent('Sovereign-Studio-ato · main · 500 files'),
      buildRouteSelectionEvent({ route: 'code-llm', reason: 'Patch-Erzeugung durch Code-Modell.' }),
      buildWorkerRequestEvent('DeepSeek R1'),
      buildWorkerResponseEvent(),
    ]);

    expect(stream.events.map((event) => event.route)).toEqual([
      'runtime',
      'repo',
      'code-llm',
      'worker',
      'worker',
    ]);
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
