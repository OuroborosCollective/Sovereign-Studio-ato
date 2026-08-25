import type { ChatLine, SituationalBubbleBinding } from './builderContainerTypes';
import { commitSituationalBubble } from './situationalBubbleRuntime';

export type SessionMessageRole = 'user' | 'assistant';

export interface SessionMessage {
  readonly id: string;
  readonly role: SessionMessageRole;
  readonly content: string;
  readonly timestamp: number;
  readonly bubble: SituationalBubbleBinding;
}

export interface PersistedSession {
  readonly version: 3;
  readonly persistence: 'postgresql';
  readonly sessionId: string;
  readonly repoUrl: string;
  readonly repoBranch: string;
  readonly messages: readonly SessionMessage[];
  readonly createdAt: number;
  readonly updatedAt: number;
  readonly messageCount: number;
}

type FetchLike = typeof fetch;

const SECRET_PATTERNS = [
  /gh[pousr]_[\w]{8,100}/gi,
  /github_pat_[\w]{20,200}/gi,
  /AIza[\w-]{26,60}/gi,
  /sk-(?:or-v1-|proj-|ant-)?[\w-]{20,}/gi,
  /Bearer\s+[\w._~+/=-]{20,}/gi,
] as const;

let fallbackMessageSequence = 0;

export class SessionPersistenceError extends Error {
  readonly status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = 'SessionPersistenceError';
    this.status = status;
  }
}

function stripSecrets(text: string): string {
  return SECRET_PATTERNS.reduce((value, pattern) => value.replace(pattern, '[REDACTED]'), text);
}

function apiUrl(base: string, path: string): string {
  const normalizedBase = base.trim().replace(/\/+$/, '');
  return normalizedBase ? `${normalizedBase}${path}` : path;
}

async function requestJson(
  fetchImpl: FetchLike,
  url: string,
  init: RequestInit,
): Promise<Record<string, unknown>> {
  const response = await fetchImpl(url, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  });
  const payload = await response.json().catch(() => null) as unknown;
  if (!response.ok || !payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new SessionPersistenceError('PostgreSQL chat persistence is unavailable', response.status);
  }
  return payload as Record<string, unknown>;
}

function timestamp(value: unknown, field: string): number {
  if (typeof value !== 'string') throw new SessionPersistenceError(`${field} is missing`);
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) throw new SessionPersistenceError(`${field} is invalid`);
  return parsed;
}

function sessionFromApi(value: unknown, messages: readonly SessionMessage[] = []): PersistedSession {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new SessionPersistenceError('PostgreSQL chat session payload is invalid');
  }
  const session = value as Record<string, unknown>;
  if (
    session.schemaVersion !== 'sovereign.live-workspace-chat-session.v1'
    || session.persistence !== 'postgresql'
    || typeof session.sessionId !== 'string'
    || typeof session.repositoryIdentity !== 'string'
    || typeof session.repositoryBranch !== 'string'
  ) {
    throw new SessionPersistenceError('PostgreSQL chat session contract is invalid');
  }
  const createdAt = timestamp(session.recordedAt, 'session.recordedAt');
  const updatedAt = messages.at(-1)?.timestamp ?? createdAt;
  return {
    version: 3,
    persistence: 'postgresql',
    sessionId: session.sessionId,
    repoUrl: session.repositoryIdentity,
    repoBranch: session.repositoryBranch,
    messages,
    createdAt,
    updatedAt,
    messageCount: messages.length,
  };
}

function messageFromApi(value: unknown): SessionMessage {
  const committed = commitSituationalBubble(value);
  if (!committed.ok) {
    const reason = (committed as { reason: string }).reason;
    throw new SessionPersistenceError(`Bubble output firewall blocked persisted payload: ${reason}`);
  }
  const bubble = (committed as { bubble: import('./builderContainerTypes').SituationalBubbleBinding }).bubble;
  return {
    id: bubble.bubbleHash,
    role: bubble.bubbleKind === 'MISSION_INPUT' ? 'user' : 'assistant',
    content: bubble.text,
    timestamp: timestamp(bubble.recordedAt, 'bubble.recordedAt'),
    bubble,
  };
}

export function sessionMessageToChatLine(message: SessionMessage): ChatLine {
  return {
    id: message.id,
    role: message.role,
    text: message.content,
    createdAt: message.timestamp,
    bubble: message.bubble,
  };
}

function fetchRuntime(fetchImpl?: FetchLike): FetchLike {
  const runtime = fetchImpl ?? globalThis.fetch;
  if (typeof runtime !== 'function') {
    throw new SessionPersistenceError('Fetch runtime is unavailable');
  }
  return runtime;
}

export async function getOrCreateCurrentSession(
  backendBase: string,
  repoUrl: string,
  repoBranch: string,
  fetchImpl?: FetchLike,
): Promise<PersistedSession> {
  const payload = await requestJson(
    fetchRuntime(fetchImpl),
    apiUrl(backendBase, '/api/user/agent/live-workspace/chat-session'),
    {
      method: 'POST',
      body: JSON.stringify({
        repositoryIdentity: repoUrl || 'UNBOUND',
        repositoryBranch: repoBranch || 'main',
      }),
    },
  );
  return sessionFromApi(payload.session);
}

export async function loadSession(
  backendBase: string,
  sessionId: string,
  fetchImpl?: FetchLike,
): Promise<PersistedSession> {
  const payload = await requestJson(
    fetchRuntime(fetchImpl),
    apiUrl(backendBase, `/api/user/agent/live-workspace/chat-session/${encodeURIComponent(sessionId)}/bubbles`),
    { method: 'GET' },
  );
  if (!Array.isArray(payload.bubbles)) {
    throw new SessionPersistenceError('PostgreSQL chat bubble list is invalid');
  }
  const messages = payload.bubbles.map(messageFromApi);
  return sessionFromApi(payload.session, messages);
}

export function generateClientMessageId(): string {
  const runtimeCrypto = globalThis.crypto;
  if (typeof runtimeCrypto?.randomUUID === 'function') {
    return `mission-${runtimeCrypto.randomUUID()}`;
  }
  fallbackMessageSequence += 1;
  return `mission-${Date.now().toString(36)}-${fallbackMessageSequence.toString(36)}`;
}

export async function appendMissionInput(
  backendBase: string,
  session: PersistedSession,
  text: string,
  fetchImpl?: FetchLike,
  clientMessageId = generateClientMessageId(),
): Promise<PersistedSession> {
  const payload = await requestJson(
    fetchRuntime(fetchImpl),
    apiUrl(
      backendBase,
      `/api/user/agent/live-workspace/chat-session/${encodeURIComponent(session.sessionId)}/mission`,
    ),
    {
      method: 'POST',
      body: JSON.stringify({ text, clientMessageId }),
    },
  );
  const message = messageFromApi(payload.bubble);
  const existing = session.messages.find((item) => item.bubble.clientMessageId === message.bubble.clientMessageId);
  const messages = existing ? session.messages : [...session.messages, message];
  return {
    ...session,
    messages,
    updatedAt: messages.at(-1)?.timestamp ?? session.updatedAt,
    messageCount: messages.length,
  };
}

export function buildShareUrl(sessionId: string): string {
  if (typeof window === 'undefined') return `#session=${sessionId}`;
  const url = new URL(window.location.href);
  url.hash = `session=${sessionId}`;
  return url.toString();
}

export function extractSessionIdFromUrl(hash: string): string | null {
  return hash.match(/[#&]?session=(livechat-[0-9a-f]{24})/i)?.[1] ?? null;
}

export function exportSessionAsMarkdown(session: PersistedSession): string {
  const lines = [
    '# Sovereign Studio — Situational-Bubble-Export',
    '',
    `**Session:** \`${session.sessionId}\`  `,
    `**Persistenz:** PostgreSQL  `,
    `**Repository:** ${session.repoUrl || '–'}  `,
    `**Branch:** ${session.repoBranch || '–'}  `,
    `**Nachrichten:** ${session.messages.length}`,
    '',
    '---',
    '',
  ];
  for (const message of session.messages) {
    const role = message.role === 'user' ? '**Du · Mission**' : `**Sovereign · ${message.bubble.bubbleKind}**`;
    lines.push(role + ':', '', stripSecrets(message.content), '', '---', '');
  }
  return lines.join('\n');
}

export function downloadSessionMarkdown(session: PersistedSession): 'downloaded' | 'failed' {
  if (typeof document === 'undefined') return 'failed';
  try {
    const url = URL.createObjectURL(new Blob([exportSessionAsMarkdown(session)], { type: 'text/markdown;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `sovereign-export-${session.sessionId}.md`;
    anchor.rel = 'noopener';
    anchor.click();
    URL.revokeObjectURL(url);
    return 'downloaded';
  } catch {
    return 'failed';
  }
}

const ONE_MINUTE_MS = 60 * 1000;
const ONE_HOUR_MS = 60 * ONE_MINUTE_MS;
const ONE_DAY_MS = 24 * ONE_HOUR_MS;
const THREE_DAYS_MS = 3 * ONE_DAY_MS;

export function formatPersistedSessionAge(
  session: PersistedSession,
  now = Date.now(),
): { text: string; isStale: boolean } {
  if (!Number.isFinite(session.updatedAt) || !Number.isFinite(now)) {
    return { text: 'unbekannt', isStale: true };
  }

  const ageMs = Math.max(0, now - session.updatedAt);
  let text: string;
  if (ageMs < ONE_MINUTE_MS) {
    text = 'wenige Sekunden';
  } else if (ageMs < ONE_HOUR_MS) {
    const minutes = Math.floor(ageMs / ONE_MINUTE_MS);
    text = `${minutes} Minute${minutes === 1 ? '' : 'n'}`;
  } else if (ageMs < ONE_DAY_MS) {
    const hours = Math.floor(ageMs / ONE_HOUR_MS);
    text = `${hours} Stunde${hours === 1 ? '' : 'n'}`;
  } else {
    const days = Math.floor(ageMs / ONE_DAY_MS);
    text = `${days} Tag${days === 1 ? '' : 'e'}`;
  }

  return { text, isStale: ageMs > THREE_DAYS_MS };
}
