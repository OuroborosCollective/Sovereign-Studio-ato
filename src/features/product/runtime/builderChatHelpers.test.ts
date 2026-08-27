import { describe, expect, it } from 'vitest';
import {
  isWriteIntent,
  isLocalCompletionStatusQuestion,
  buildLocalStatusAnswer,
  buildChatLines,
  buildWorkerBlockerAnswer,
  sameRecord,
} from './builderChatHelpers';

describe('isWriteIntent', () => {
  it('returns the LLM-declared explicit value when provided', () => {
    // The LLM (Brain) classifies intent; the runtime just passes it through.
    expect(isWriteIntent('Bitte README ändern', true)).toBe(true);
    expect(isWriteIntent('Wie funktioniert React?', false)).toBe(false);
    expect(isWriteIntent('erstelle einen draft pr', true)).toBe(true);
  });

  it('returns false when no explicit classification is provided — LLM must declare intent', () => {
    // Keyword-based pre-classification has been removed. Without LLM input, default is false.
    expect(isWriteIntent('Bitte README ändern und Titel anpassen')).toBe(false);
    expect(isWriteIntent('Erzeuge bitte einen patch')).toBe(false);
    expect(isWriteIntent('mach einen commit')).toBe(false);
    expect(isWriteIntent('erstelle einen draft pr')).toBe(false);
    expect(isWriteIntent('Passe die Datei an das neue Format an')).toBe(false);
  });

  it('returns false for advisory/chat questions regardless of content', () => {
    expect(isWriteIntent('Wie funktioniert React useEffect?')).toBe(false);
    expect(isWriteIntent('Was denkst du über diese Architektur?')).toBe(false);
  });
});

describe('isLocalCompletionStatusQuestion', () => {
  it('returns the LLM-declared explicit value when provided', () => {
    expect(isLocalCompletionStatusQuestion('Bist du fertig?', true)).toBe(true);
    expect(isLocalCompletionStatusQuestion('Baue eine neue Funktion', false)).toBe(false);
  });

  it('returns false when no explicit classification is provided — LLM must declare intent', () => {
    // Keyword-based pre-classification has been removed. Without LLM input, default is false.
    expect(isLocalCompletionStatusQuestion('Bist du fertig?')).toBe(false);
    expect(isLocalCompletionStatusQuestion('Ist das erledigt?')).toBe(false);
    expect(isLocalCompletionStatusQuestion('Wo ist der patch?')).toBe(false);
    expect(isLocalCompletionStatusQuestion('Gibt es einen Draft PR?')).toBe(false);
    expect(isLocalCompletionStatusQuestion('Baue eine neue Funktion')).toBe(false);
  });
});

describe('buildLocalStatusAnswer', () => {
  const base = {
    githubWriteAllowed: true,
    writeIntentBlockedByRepo: false,
    agentRunning: false,
    draftPrUrl: null,
    hasPatch: false,
    hasWorkerResponse: false,
    workerBlocker: null,
  };

  it('reports draft PR ready as the truth', () => {
    expect(buildLocalStatusAnswer({ ...base, draftPrUrl: 'https://github.com/x/y/pull/1' }))
      .toContain('https://github.com/x/y/pull/1');
  });

  it('reports patch generated when no PR yet', () => {
    expect(buildLocalStatusAnswer({ ...base, hasPatch: true })).toMatch(/Patch\/Diff wurde erzeugt/);
  });

  it('reports Sovereign Agent still running', () => {
    expect(buildLocalStatusAnswer({ ...base, agentRunning: true })).toMatch(/Sovereign Agent arbeitet noch/);
  });

  it('reports missing GitHub access honestly instead of claiming done', () => {
    const answer = buildLocalStatusAnswer({ ...base, githubWriteAllowed: false });
    expect(answer).toMatch(/GitHub-Zugang fehlt/);
  });

  it('reports GitHub access validation in progress instead of claiming missing or done', () => {
    const answer = buildLocalStatusAnswer({
      ...base,
      githubWriteAllowed: false,
      githubAccessState: 'validating',
    });

    expect(answer).toMatch(/GitHub-Zugang wird gerade geprüft/);
    expect(answer.toLowerCase()).not.toMatch(/^ja/);
  });

  it('reports format-only GitHub access as not API-validated yet', () => {
    const answer = buildLocalStatusAnswer({
      ...base,
      githubWriteAllowed: false,
      githubAccessState: 'requested',
    });

    expect(answer).toMatch(/echte GitHub-API-Prüfung steht noch aus/);
  });

  it('reports repo-missing block before access-missing', () => {
    const answer = buildLocalStatusAnswer({
      ...base,
      githubWriteAllowed: false,
      writeIntentBlockedByRepo: true,
    });
    expect(answer).toMatch(/GitHub-Repo geladen werden muss/);
  });

  it('never claims done from a mere worker text response', () => {
    const answer = buildLocalStatusAnswer({ ...base, hasWorkerResponse: true });
    expect(answer).toMatch(/nur eine Worker-Antwort/);
    expect(answer.toLowerCase()).not.toMatch(/^ja/);
  });

  it('reports nothing started when runtime is fully idle', () => {
    expect(buildLocalStatusAnswer(base)).toMatch(/kein Auftrag gestartet/);
  });
});

describe('buildWorkerBlockerAnswer', () => {
  it('routes 502 diagnostics to direct FreeLLM/OpenRouter evidence instead of the retired Cloudflare bridge', () => {
    const answer = buildWorkerBlockerAnswer({
      blocker: {
        diagnostic: {
          route: 'https://sovereign-backend.arelorian.de/api/llm/chat',
          model: 'revolver-test',
          messageCount: 3,
          status: 502,
          scope: 'upstream_provider',
          canClientFix: false,
          nextAction: 'Direkten OpenRouter-/FreeLLM-Transport und dessen Upstream-Evidence prüfen.',
        },
      } as any,
      repoReady: true,
      chatRepoSnapshot: null,
      agentReady: true,
    });

    expect(answer).toContain('FreeLLMAPI-Revolver');
    expect(answer).toContain('OpenRouter-Evidence');
    expect(answer).not.toContain('Cloudflare/Bridge-Diagnose');
  });
});

describe('buildChatLines', () => {
  const baseArgs = {
    repoReady: true,
    repoReason: 'Repo is ready',
    runtimeThinkingActive: false,
    cuteThinkingLabel: '',
    sovereignSummary: '',
    chatRepoSnapshot: null,
    chatRepoError: null,
    chatHistory: [],
  };

  const mission = {
    id: 'mission',
    role: 'user' as const,
    text: 'Repariere den Login.',
    bubble: {
      schemaVersion: 'sovereign.live-workspace-chat-bubble.v1' as const,
      persistenceSchemaVersion: 'sovereign.live-workspace-chat-persistence.v1',
      sessionId: 'livechat-' + 'a'.repeat(24),
      clientMessageId: 'mission-1',
      bubbleKind: 'MISSION_INPUT' as const,
      sourceKind: 'USER_INPUT' as const,
      text: 'Repariere den Login.',
      canonicalReferenceHashes: [],
      workflowState: 'RECORDED',
      bubbleHash: 'b'.repeat(64),
      recordedAt: '2026-08-23T01:00:00+00:00',
      authoritative: false as const,
    },
  };

  it('renders only committed typed situational bubbles', () => {
    const lines = buildChatLines({
      ...baseArgs,
      restoredSessionAge: '2m',
      sovereignSummary: 'Tests laufen gerade.',
      cuteThinkingLabel: 'Ich denke nach.',
      runtimeThinkingActive: true,
      chatHistory: [
        mission,
        { id: 'raw-assistant', role: 'assistant', text: 'Tests laufen gerade.' },
        { id: 'system', role: 'system', text: 'Repo verbunden.' },
        { id: 'thought', role: 'thought', text: 'Ich öffne jetzt Datei X.' },
      ],
    });
    expect(lines).toEqual([mission]);
  });

  it('does not turn repo, restore age or disabled state into primary chat messages', () => {
    const lines = buildChatLines({
      ...baseArgs,
      restoredSessionAge: '2m',
      disabledReason: 'Worker blockiert',
    });
    expect(lines).toEqual([]);
  });
});

describe('sameRecord', () => {
  it('returns true for identical records', () => {
    const a = { chat: 'idle', init: 'active', sync: 'processing' };
    const b = { chat: 'idle', init: 'active', sync: 'processing' };
    expect(sameRecord(a, b)).toBe(true);
  });

  it('returns true for empty records', () => {
    expect(sameRecord({}, {})).toBe(true);
  });

  it('returns false when key counts differ', () => {
    const a = { chat: 'idle' };
    const b = { chat: 'idle', init: 'active' };
    expect(sameRecord(a, b)).toBe(false);
    expect(sameRecord(b, a)).toBe(false);
  });

  it('returns false when values for the same key differ', () => {
    const a = { chat: 'idle', init: 'active' };
    const b = { chat: 'idle', init: 'idle' };
    expect(sameRecord(a, b)).toBe(false);
  });

  it('returns false when keys differ even if total key count matches', () => {
    const a = { chat: 'idle', init: 'active' };
    const b = { chat: 'idle', sync: 'active' };
    expect(sameRecord(a, b)).toBe(false);
  });
});
