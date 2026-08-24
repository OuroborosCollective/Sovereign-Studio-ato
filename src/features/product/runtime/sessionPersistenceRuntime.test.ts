import { describe, expect, it, vi } from 'vitest';
import type { SituationalBubbleBinding } from './builderContainerTypes';
import {
  appendMissionInput,
  buildShareUrl,
  exportSessionAsMarkdown,
  extractSessionIdFromUrl,
  formatPersistedSessionAge,
  generateClientMessageId,
  getOrCreateCurrentSession,
  loadSession,
  sessionMessageToChatLine,
  type PersistedSession,
} from './sessionPersistenceRuntime';

const SESSION_ID = 'livechat-' + 'a'.repeat(24);
const BUBBLE_HASH = 'b'.repeat(64);
const RECORDED_AT = '2026-08-23T01:00:00+00:00';

const sessionPayload = {
  schemaVersion: 'sovereign.live-workspace-chat-session.v1',
  sessionId: SESSION_ID,
  repositoryIdentity: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
  repositoryBranch: 'main',
  recordedAt: RECORDED_AT,
  persistence: 'postgresql',
  authoritative: false,
};

const missionBubble = {
  schemaVersion: 'sovereign.live-workspace-chat-bubble.v1',
  persistenceSchemaVersion: 'sovereign.live-workspace-chat-persistence.v1',
  sessionId: SESSION_ID,
  clientMessageId: 'mission-test',
  bubbleKind: 'MISSION_INPUT',
  sourceKind: 'USER_INPUT',
  text: 'Repariere den Login.',
  canonicalReferenceHashes: [],
  sessionBindingHash: null,
  runId: null,
  attemptId: null,
  workflowState: 'RECORDED',
  boundRevision: null,
  effectKind: null,
  targetHash: null,
  consentBindingHash: null,
  bubbleHash: BUBBLE_HASH,
  recordedAt: RECORDED_AT,
  authoritative: false,
};

function response(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

describe('real PostgreSQL session persistence runtime', () => {
  it('resolves a repo-bound server session with credentialed fetch', async () => {
    const fetchImpl = vi.fn(async () => response({ session: sessionPayload })) as unknown as typeof fetch;
    const session = await getOrCreateCurrentSession(
      'https://sovereign-backend.example',
      sessionPayload.repositoryIdentity,
      'main',
      fetchImpl,
    );
    expect(session.persistence).toBe('postgresql');
    expect(session.sessionId).toBe(SESSION_ID);
    expect(fetchImpl).toHaveBeenCalledWith(
      'https://sovereign-backend.example/api/user/agent/live-workspace/chat-session',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    );
  });

  it('loads only committed typed bubbles from the backend', async () => {
    const fetchImpl = vi.fn(async () => response({
      session: sessionPayload,
      bubbles: [missionBubble],
    })) as unknown as typeof fetch;
    const session = await loadSession('', SESSION_ID, fetchImpl);
    expect(session.messages).toHaveLength(1);
    expect(sessionMessageToChatLine(session.messages[0]).bubble?.bubbleKind).toBe('MISSION_INPUT');
  });

  it('fails closed when a persisted payload contains internal reasoning', async () => {
    const fetchImpl = vi.fn(async () => response({
      session: sessionPayload,
      bubbles: [{ ...missionBubble, text: "Here's a thinking process." }],
    })) as unknown as typeof fetch;
    await expect(loadSession('', SESSION_ID, fetchImpl)).rejects.toThrow('output firewall');
  });

  it('appends a mission through the server and never local storage', async () => {
    const session = {
      version: 3,
      persistence: 'postgresql',
      sessionId: SESSION_ID,
      repoUrl: sessionPayload.repositoryIdentity,
      repoBranch: 'main',
      messages: [],
      createdAt: Date.parse(RECORDED_AT),
      updatedAt: Date.parse(RECORDED_AT),
      messageCount: 0,
    } satisfies PersistedSession;
    const fetchImpl = vi.fn(async () => response({ bubble: missionBubble }, 201)) as unknown as typeof fetch;
    const saved = await appendMissionInput('', session, missionBubble.text, fetchImpl, 'mission-test');
    expect(saved.messages).toHaveLength(1);
    expect(saved.messages[0].bubble.sourceKind).toBe('USER_INPUT');
    expect(fetchImpl).toHaveBeenCalledWith(
      `/api/user/agent/live-workspace/chat-session/${SESSION_ID}/mission`,
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    );
  });

  it('creates bounded message ids and share links only for canonical session ids', () => {
    expect(generateClientMessageId()).toMatch(/^mission-/);
    expect(buildShareUrl(SESSION_ID)).toContain(`session=${SESSION_ID}`);
    expect(extractSessionIdFromUrl(`#session=${SESSION_ID}`)).toBe(SESSION_ID);
    expect(extractSessionIdFromUrl('#session=legacy-local-id')).toBeNull();
  });

  it('exports only typed persisted messages and redacts credentials defensively', () => {
    const credential = ['github', 'pat', 'x'.repeat(40)].join('_');
    const bubble = {
      schemaVersion: 'sovereign.live-workspace-chat-bubble.v1',
      persistenceSchemaVersion: 'sovereign.live-workspace-chat-persistence.v1',
      sessionId: SESSION_ID,
      clientMessageId: 'mission-export',
      bubbleKind: 'MISSION_INPUT',
      sourceKind: 'USER_INPUT',
      text: credential,
      canonicalReferenceHashes: [],
      workflowState: 'RECORDED',
      bubbleHash: BUBBLE_HASH,
      recordedAt: RECORDED_AT,
      authoritative: false,
    } satisfies SituationalBubbleBinding;
    const message = {
      id: BUBBLE_HASH,
      role: 'user' as const,
      content: credential,
      timestamp: Date.parse(RECORDED_AT),
      bubble,
    };
    const session: PersistedSession = {
      version: 3,
      persistence: 'postgresql',
      sessionId: SESSION_ID,
      repoUrl: sessionPayload.repositoryIdentity,
      repoBranch: 'main',
      messages: [message],
      createdAt: Date.parse(RECORDED_AT),
      updatedAt: Date.parse(RECORDED_AT),
      messageCount: 1,
    };
    const markdown = exportSessionAsMarkdown(session);
    expect(markdown).toContain('PostgreSQL');
    expect(markdown).toContain('[REDACTED]');
    expect(markdown).not.toContain(credential);
  });

  it('surfaces backend persistence failure instead of fabricating a saved session', async () => {
    const fetchImpl = vi.fn(async () => response({ error: 'blocked' }, 503)) as unknown as typeof fetch;
    await expect(getOrCreateCurrentSession('', 'UNBOUND', 'main', fetchImpl)).rejects.toThrow(
      'PostgreSQL chat persistence is unavailable',
    );
  });
});

describe('formatPersistedSessionAge', () => {
  const now = 1700000000000;
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const makeSession = (updatedAt: number) => ({
    version: 3 as const,
    persistence: 'postgresql' as const,
    sessionId: 'livechat-' + 'f'.repeat(24),
    repoUrl: 'r',
    repoBranch: 'b',
    messages: [],
    createdAt: updatedAt - 1000,
    updatedAt,
    messageCount: 0,
  });

  it('describes recent and future timestamps as wenige Sekunden', () => {
    expect(formatPersistedSessionAge(makeSession(now - 30000), now)).toEqual({
      text: 'wenige Sekunden',
      isStale: false,
    });
    expect(formatPersistedSessionAge(makeSession(now + minute), now).text).toBe('wenige Sekunden');
  });

  it('uses completed minutes and hours without crossing unit boundaries', () => {
    expect(formatPersistedSessionAge(makeSession(now - 90 * 1000), now).text).toBe('1 Minute');
    expect(formatPersistedSessionAge(makeSession(now - 5 * minute), now).text).toBe('5 Minuten');
    expect(formatPersistedSessionAge(makeSession(now - hour), now).text).toBe('1 Stunde');
    expect(formatPersistedSessionAge(makeSession(now - 3 * hour), now).text).toBe('3 Stunden');
    expect(formatPersistedSessionAge(makeSession(now - (day - minute)), now).text).toBe('23 Stunden');
  });

  it('uses correct German singular and plural day labels', () => {
    expect(formatPersistedSessionAge(makeSession(now - day), now).text).toBe('1 Tag');
    expect(formatPersistedSessionAge(makeSession(now - 2 * day), now).text).toBe('2 Tage');
  });

  it('marks only sessions older than three full days as stale', () => {
    expect(formatPersistedSessionAge(makeSession(now - 3 * day), now)).toEqual({
      text: '3 Tage',
      isStale: false,
    });
    expect(formatPersistedSessionAge(makeSession(now - 3 * day - 1), now).isStale).toBe(true);
  });

  it('fails visibly closed for an invalid timestamp', () => {
    expect(formatPersistedSessionAge(makeSession(Number.NaN), now)).toEqual({
      text: 'unbekannt',
      isStale: true,
    });
  });
});
