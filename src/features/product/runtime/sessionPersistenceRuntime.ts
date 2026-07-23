export type SessionMessageRole = 'user' | 'assistant' | 'system';
export interface SessionMessage { readonly id: string; readonly role: SessionMessageRole; readonly content: string; readonly timestamp: number; readonly fileRef?: string; }
export interface PersistedSession { readonly version: 2; readonly sessionId: string; readonly repoUrl: string; readonly repoBranch: string; readonly messages: readonly SessionMessage[]; readonly createdAt: number; readonly updatedAt: number; readonly messageCount: number; }
export interface SessionIndex { readonly version: 1; readonly sessions: readonly string[]; readonly updatedAt: number; }
export const SESSION_STORAGE_KEY = 'sovereign-studio.chat-session.v1';
export const SESSION_INDEX_KEY = 'sovereign-studio.session-index.v1';
export const MAX_MESSAGES_PER_SESSION = 500;
export const MAX_SESSIONS_IN_INDEX = 20;
const SECRET_PATTERNS = [/gh[pousr]_[\w]{8,100}/gi, /github_pat_[\w]{20,200}/gi, /AIza[\w-]{26,60}/gi, /sk-(?:or-v1-|proj-|ant-)?[\w-]{20,}/gi, /Bearer\s+[\w._~+/=-]{20,}/gi] as const;
let monotonicSessionSequence = 0;
function stripSecrets(text: string): string { return SECRET_PATTERNS.reduce((value, pattern) => value.replace(pattern, '[REDACTED]'), text); }
function createSessionSuffix(): string {
  const runtimeCrypto = globalThis.crypto;
  if (typeof runtimeCrypto?.randomUUID === 'function') return runtimeCrypto.randomUUID().replace(/-/g, '').slice(0, 16);
  if (typeof runtimeCrypto?.getRandomValues === 'function') {
    const bytes = new Uint8Array(8);
    runtimeCrypto.getRandomValues(bytes);
    return Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  }
  monotonicSessionSequence += 1;
  return `seq-${monotonicSessionSequence.toString(36)}`;
}
export function generateSessionId(): string { return `${Date.now().toString(36)}-${createSessionSuffix()}`; }
function validSession(value: unknown): value is PersistedSession { if (!value || typeof value !== 'object') return false; const item = value as Record<string, unknown>; return item.version === 2 && typeof item.sessionId === 'string' && Array.isArray(item.messages) && typeof item.createdAt === 'number' && typeof item.updatedAt === 'number'; }
function loadIndex(storage: Storage): SessionIndex { try { const raw = storage.getItem(SESSION_INDEX_KEY); const parsed = raw ? JSON.parse(raw) as unknown : null; if (parsed && typeof parsed === 'object' && (parsed as Record<string, unknown>).version === 1 && Array.isArray((parsed as Record<string, unknown>).sessions)) return parsed as SessionIndex; } catch { /* fail closed */ } return { version: 1, sessions: [], updatedAt: Date.now() }; }
function saveIndex(storage: Storage, sessionId: string): void { const current = loadIndex(storage); const sessions = [sessionId, ...current.sessions.filter((id) => id !== sessionId)].slice(0, MAX_SESSIONS_IN_INDEX); storage.setItem(SESSION_INDEX_KEY, JSON.stringify({ version: 1, sessions, updatedAt: Date.now() })); }
export function loadSession(storage: Storage, sessionId: string): PersistedSession | null { try { const raw = storage.getItem(`${SESSION_STORAGE_KEY}:${sessionId}`); if (!raw) return null; const parsed = JSON.parse(raw) as unknown; return validSession(parsed) ? parsed : null; } catch { return null; } }
export function listSessions(storage: Storage): readonly PersistedSession[] { return loadIndex(storage).sessions.map((id) => loadSession(storage, id)).filter((item): item is PersistedSession => Boolean(item)).sort((left, right) => right.updatedAt - left.updatedAt); }
export function getOrCreateCurrentSession(storage: Storage, repoUrl: string, repoBranch: string): PersistedSession { return listSessions(storage).find((item) => item.repoUrl === repoUrl && item.repoBranch === repoBranch) ?? { version: 2, sessionId: generateSessionId(), repoUrl, repoBranch, messages: [], createdAt: Date.now(), updatedAt: Date.now(), messageCount: 0 }; }
export function saveSession(storage: Storage, session: Omit<PersistedSession, 'version' | 'updatedAt' | 'messageCount'>): PersistedSession { const messages = session.messages.slice(-MAX_MESSAGES_PER_SESSION); const saved: PersistedSession = { ...session, version: 2, messages, updatedAt: Date.now(), messageCount: messages.length }; storage.setItem(`${SESSION_STORAGE_KEY}:${saved.sessionId}`, JSON.stringify(saved)); saveIndex(storage, saved.sessionId); return saved; }
export function deleteSession(storage: Storage, sessionId: string): void { storage.removeItem(`${SESSION_STORAGE_KEY}:${sessionId}`); const index = loadIndex(storage); storage.setItem(SESSION_INDEX_KEY, JSON.stringify({ version: 1, sessions: index.sessions.filter((id) => id !== sessionId), updatedAt: Date.now() })); }
export function appendMessage(session: PersistedSession, message: Omit<SessionMessage, 'id' | 'timestamp'> & { id?: string; timestamp?: number }): PersistedSession { const next: SessionMessage = { id: message.id ?? `msg-${generateSessionId()}`, role: message.role, content: message.content, timestamp: message.timestamp ?? Date.now(), ...(message.fileRef ? { fileRef: message.fileRef } : {}) }; const messages = [...session.messages, next].slice(-MAX_MESSAGES_PER_SESSION); return { ...session, messages, updatedAt: Date.now(), messageCount: messages.length }; }
export function buildShareUrl(sessionId: string): string { if (typeof window === 'undefined') return `#session=${sessionId}`; const url = new URL(window.location.href); url.hash = `session=${sessionId}`; return url.toString(); }
export function extractSessionIdFromUrl(hash: string): string | null { return hash.match(/[#&]?session=([a-z0-9-]+)/i)?.[1] ?? null; }
export function exportSessionAsMarkdown(session: PersistedSession): string { const lines = ['# Sovereign Studio — Chat-Export', '', `**Session:** \`${session.sessionId}\`  `, `**Repository:** ${session.repoUrl || '–'}  `, `**Branch:** ${session.repoBranch || '–'}  `, `**Nachrichten:** ${session.messages.length}`, '', '---', '']; for (const message of session.messages) { const role = message.role === 'user' ? '**Du**' : message.role === 'assistant' ? '**Sovereign**' : '**System**'; lines.push(`${role}:`, '', stripSecrets(message.content), message.fileRef ? `\n> 📎 ${message.fileRef}` : '', '', '---', ''); } return lines.filter((line) => line !== undefined).join('\n'); }
export function downloadSessionMarkdown(session: PersistedSession): 'downloaded' | 'failed' { if (typeof document === 'undefined') return 'failed'; try { const url = URL.createObjectURL(new Blob([exportSessionAsMarkdown(session)], { type: 'text/markdown;charset=utf-8' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `sovereign-export-${session.sessionId}.md`; anchor.rel = 'noopener'; anchor.click(); URL.revokeObjectURL(url); return 'downloaded'; } catch { return 'failed'; } }
