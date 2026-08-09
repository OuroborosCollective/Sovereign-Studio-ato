import { beforeEach, describe, expect, it } from 'vitest';
import { appendMessage, buildShareUrl, deleteSession, exportSessionAsMarkdown, extractSessionIdFromUrl, formatPersistedSessionAge, getOrCreateCurrentSession, listSessions, loadSession, saveSession } from './sessionPersistenceRuntime';

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return Array.from(this.values.keys())[index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

describe('sessionPersistenceRuntime', () => {
  let storage: Storage;
  beforeEach(() => { storage = new MemoryStorage(); });
  it('creates a repo-bound session', () => { const session = getOrCreateCurrentSession(storage, 'repo-a', 'main'); expect(session.repoBranch).toBe('main'); expect(session.sessionId).toBeTruthy(); });
  it('saves and reloads a session', () => { const base = getOrCreateCurrentSession(storage, 'repo', 'main'); const saved = saveSession(storage, { sessionId: base.sessionId, repoUrl: base.repoUrl, repoBranch: base.repoBranch, messages: [], createdAt: base.createdAt }); expect(loadSession(storage, saved.sessionId)?.sessionId).toBe(saved.sessionId); });
  it('reuses the latest matching repo session', () => { const base = getOrCreateCurrentSession(storage, 'repo', 'main'); saveSession(storage, { sessionId: base.sessionId, repoUrl: 'repo', repoBranch: 'main', messages: [], createdAt: base.createdAt }); expect(getOrCreateCurrentSession(storage, 'repo', 'main').sessionId).toBe(base.sessionId); });
  it('keeps branches separate', () => { const main = getOrCreateCurrentSession(storage, 'repo', 'main'); saveSession(storage, { sessionId: main.sessionId, repoUrl: 'repo', repoBranch: 'main', messages: [], createdAt: main.createdAt }); expect(getOrCreateCurrentSession(storage, 'repo', 'dev').sessionId).not.toBe(main.sessionId); });
  it('appends a message', () => { const base = getOrCreateCurrentSession(storage, 'repo', 'main'); const next = appendMessage(base, { role: 'user', content: 'hello' }); expect(next.messages[0].content).toBe('hello'); expect(next.messageCount).toBe(1); });
  it('lists persisted sessions', () => { saveSession(storage, { sessionId: 'a', repoUrl: 'a', repoBranch: 'main', messages: [], createdAt: 1 }); saveSession(storage, { sessionId: 'b', repoUrl: 'b', repoBranch: 'main', messages: [], createdAt: 2 }); expect(listSessions(storage)).toHaveLength(2); });
  it('deletes a session and index entry', () => { const saved = saveSession(storage, { sessionId: 'a', repoUrl: 'a', repoBranch: 'main', messages: [], createdAt: 1 }); deleteSession(storage, saved.sessionId); expect(loadSession(storage, saved.sessionId)).toBeNull(); expect(listSessions(storage)).toHaveLength(0); });
  it('returns null for corrupt session data', () => { storage.setItem('sovereign-studio.chat-session.v1:a', '{'); expect(loadSession(storage, 'a')).toBeNull(); });
  it('extracts a shared session id', () => expect(extractSessionIdFromUrl('#session=abc-123')).toBe('abc-123'));
  it('returns null without a session hash', () => expect(extractSessionIdFromUrl('#other=x')).toBeNull());
  it('builds a share URL containing the session id', () => expect(buildShareUrl('abc')).toContain('session=abc'));
  it('exports markdown with roles and repository', () => { const session = appendMessage(getOrCreateCurrentSession(storage, 'repo', 'main'), { role: 'assistant', content: 'done' }); const markdown = exportSessionAsMarkdown(session); expect(markdown).toContain('**Sovereign**'); expect(markdown).toContain('repo'); });
  it('redacts a generated GitHub credential pattern in export', () => { const credential = ['github', 'pat', 'x'.repeat(40)].join('_'); const session = appendMessage(getOrCreateCurrentSession(storage, 'repo', 'main'), { role: 'user', content: credential }); const markdown = exportSessionAsMarkdown(session); expect(markdown).not.toContain(credential); expect(markdown).toContain('[REDACTED]'); });
  it('redacts a generated bearer credential in export', () => { const credential = ['Bear', 'er ', 'a'.repeat(32)].join(''); const session = appendMessage(getOrCreateCurrentSession(storage, 'repo', 'main'), { role: 'user', content: credential }); expect(exportSessionAsMarkdown(session)).toContain('[REDACTED]'); });
});

describe('formatPersistedSessionAge', () => {
  const now = 1700000000000;
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const makeSession = (updatedAt: number) => ({
    version: 2 as const,
    sessionId: 'test',
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
