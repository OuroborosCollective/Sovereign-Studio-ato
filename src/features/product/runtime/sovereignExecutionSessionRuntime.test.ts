import { describe, expect, it } from 'vitest';
import {
  createSovereignExecutionSession,
  deriveSovereignExecutionNextAction,
  detectSovereignExecutionStuck,
  observeSovereignExecutionTool,
  startSovereignExecutionSession,
  summarizeSovereignExecutionSession,
} from './sovereignExecutionSessionRuntime';

describe('sovereignExecutionSessionRuntime', () => {
  it('starts only from idle and derives an observe action', () => {
    const session = createSovereignExecutionSession('Bitte Runtime prüfen', 1700000000000);
    const started = startSovereignExecutionSession(session, 1700000000001);

    expect(started.session.status).toBe('running');
    expect(started.nextAllowedAction).toBe('observe_tool');
    expect(started.event.kind).toBe('executor_started');
    expect(started.session.currentStepId).toBeTruthy();

    const blocked = startSovereignExecutionSession(started.session, 1700000000002);
    expect(blocked.session.status).toBe('blocked');
    expect(blocked.nextAllowedAction).toBe('resolve_blocker');
  });

  it('blocks empty requests instead of creating fake work', () => {
    const session = createSovereignExecutionSession('', 1700000000000);
    const transition = startSovereignExecutionSession(session, 1700000000001);

    expect(transition.session.status).toBe('blocked');
    expect(transition.event.kind).toBe('blocked');
    expect(transition.session.blocker).toContain('Empty request');
  });

  it('applies tool observations to plan and session state', () => {
    let transition = startSovereignExecutionSession(
      createSovereignExecutionSession('Bitte Repo prüfen', 1700000000000),
      1700000000001,
    );

    transition = observeSovereignExecutionTool(transition.session, {
      toolName: 'repo_loader',
      route: 'repo',
      phase: 'completed',
      resultSummary: 'Repo snapshot loaded',
      target: 'repo://snapshot',
      createdAt: 1700000000002,
    });

    expect(transition.session.observations).toHaveLength(1);
    expect(transition.session.plan.steps[0].status).toBe('completed');
    expect(transition.nextAllowedAction).toBe('start_step');
  });

  it('blocks the active plan step when a tool is blocked', () => {
    let transition = startSovereignExecutionSession(
      createSovereignExecutionSession('Bitte Draft PR erstellen', 1700000000000),
      1700000000001,
    );

    transition = observeSovereignExecutionTool(transition.session, {
      toolName: 'github_access',
      route: 'github-access',
      phase: 'blocked',
      blocker: 'github_access_missing',
      createdAt: 1700000000002,
    });

    expect(transition.session.status).toBe('blocked');
    expect(transition.session.blocker).toBe('github_access_missing');
    expect(deriveSovereignExecutionNextAction(transition.session)).toBe('resolve_blocker');
  });

  it('detects repeated blockers and recommends strategy change', () => {
    let transition = startSovereignExecutionSession(
      createSovereignExecutionSession('Bitte OpenHands starten', 1700000000000),
      1700000000001,
    );

    for (const createdAt of [1700000000002, 1700000000003, 1700000000004]) {
      transition = observeSovereignExecutionTool(transition.session, {
        toolName: 'openhands',
        route: 'openhands',
        phase: 'blocked',
        blocker: 'github_access_missing',
        createdAt,
      });
    }

    expect(detectSovereignExecutionStuck(transition.session).stuck).toBe(true);
    expect(transition.nextAllowedAction).toBe('change_strategy');
    expect(transition.session.blocker).toContain('Repeated');
  });

  it('redacts secrets in request and summaries', () => {
    const session = createSovereignExecutionSession(
      'Bitte nutze token=ghp_abcdefghijklmnopqrstuvwxyz1234567890',
      1700000000000,
    );

    expect(session.request).not.toContain('ghp_');

    const summary = summarizeSovereignExecutionSession(session);
    expect(summary).not.toContain('ghp_');
    expect(summary).toContain('[redacted-secret]');
  });
});
