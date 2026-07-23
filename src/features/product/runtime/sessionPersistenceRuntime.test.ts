import { beforeEach, describe, expect, it } from 'vitest';
import { appendMessage, buildShareUrl, deleteSession, exportSessionAsMarkdown, extractSessionIdFromUrl, getOrCreateCurrentSession, listSessions, loadSession, saveSession } from './sessionPersistenceRuntime';

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
