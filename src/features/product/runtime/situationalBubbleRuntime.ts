import type {
  ChatLine,
  SituationalBubbleBinding,
  SituationalBubbleKind,
  SituationalBubbleSourceKind,
} from './builderContainerTypes';

const SHA256_RE = /^[0-9a-f]{64}$/;
const REVISION_RE = /^[0-9a-f]{40}$/;
const SESSION_RE = /^livechat-[0-9a-f]{24}$/;
const SOURCE_BY_KIND: Readonly<Record<SituationalBubbleKind, SituationalBubbleSourceKind>> = {
  MISSION_INPUT: 'USER_INPUT',
  REQUIRED_QUESTION: 'CANONICAL_WORKFLOW',
  OWNER_CONSENT_REQUEST: 'CONSENT_CONTRACT',
  MATERIAL_BLOCKER: 'CANONICAL_WORKFLOW',
  FINAL_RESULT: 'EFFECT_READBACK',
};
const ALLOWED_KEYS = new Set([
  'schemaVersion',
  'persistenceSchemaVersion',
  'sessionId',
  'clientMessageId',
  'bubbleKind',
  'sourceKind',
  'text',
  'canonicalReferenceHashes',
  'sessionBindingHash',
  'runId',
  'attemptId',
  'workflowState',
  'boundRevision',
  'effectKind',
  'targetHash',
  'consentBindingHash',
  'bubbleHash',
  'recordedAt',
  'authoritative',
]);
const INTERNAL_TEXT_MARKERS = [
  "here's a thinking process",
  'chain-of-thought',
  'reasoning:',
  'system prompt',
  'tool schema',
  'runtime_flags',
  'provider_request_id',
  '"role":"system"',
  '<|system|>',
] as const;
const SECRET_PATTERNS = [
  /gh[pousr]_[A-Za-z0-9_]{8,100}/i,
  /github_pat_[A-Za-z0-9_]{20,200}/i,
  /sk-(?:or-v1-|proj-|ant-)?[A-Za-z0-9_-]{20,}/i,
  /Bearer\s+[A-Za-z0-9._~+/=-]{20,}/i,
  /BEGIN (?:OPENSSH |RSA )?PRIVATE KEY/i,
] as const;

export type BubbleFirewallReason =
  | 'NOT_AN_OBJECT'
  | 'UNKNOWN_FIELD'
  | 'UNSUPPORTED_SCHEMA'
  | 'UNSUPPORTED_CLASS'
  | 'SOURCE_MISMATCH'
  | 'INVALID_IDENTITY'
  | 'INVALID_TEXT'
  | 'INTERNAL_CONTENT'
  | 'SECRET_SHAPED_CONTENT'
  | 'INVALID_REFERENCES'
  | 'MISSING_CANONICAL_BINDING'
  | 'INVALID_WORKFLOW_STATE'
  | 'ROLE_MISMATCH';

export type BubbleFirewallResult =
  | { readonly ok: true; readonly bubble: SituationalBubbleBinding }
  | { readonly ok: false; readonly reason: BubbleFirewallReason };

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function optionalText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function exactHash(value: unknown): string | null {
  const normalized = optionalText(value)?.toLowerCase() ?? null;
  return normalized && SHA256_RE.test(normalized) ? normalized : null;
}

function exactRevision(value: unknown): string | null {
  const normalized = optionalText(value)?.toLowerCase() ?? null;
  return normalized && REVISION_RE.test(normalized) ? normalized : null;
}

function typedKind(value: unknown): SituationalBubbleKind | null {
  return value === 'MISSION_INPUT'
    || value === 'REQUIRED_QUESTION'
    || value === 'OWNER_CONSENT_REQUEST'
    || value === 'MATERIAL_BLOCKER'
    || value === 'FINAL_RESULT'
    ? value
    : null;
}

export function commitSituationalBubble(candidate: unknown): BubbleFirewallResult {
  if (!isObject(candidate)) return { ok: false, reason: 'NOT_AN_OBJECT' };
  if (Object.keys(candidate).some((key) => !ALLOWED_KEYS.has(key))) {
    return { ok: false, reason: 'UNKNOWN_FIELD' };
  }
  if (candidate.schemaVersion !== 'sovereign.live-workspace-chat-bubble.v1') {
    return { ok: false, reason: 'UNSUPPORTED_SCHEMA' };
  }
  const bubbleKind = typedKind(candidate.bubbleKind);
  if (!bubbleKind) return { ok: false, reason: 'UNSUPPORTED_CLASS' };
  const sourceKind = optionalText(candidate.sourceKind) as SituationalBubbleSourceKind | null;
  if (sourceKind !== SOURCE_BY_KIND[bubbleKind]) {
    return { ok: false, reason: 'SOURCE_MISMATCH' };
  }
  const sessionId = optionalText(candidate.sessionId);
  const bubbleHash = exactHash(candidate.bubbleHash);
  const clientMessageId = optionalText(candidate.clientMessageId);
  if (!sessionId || !SESSION_RE.test(sessionId) || !bubbleHash || !clientMessageId || clientMessageId.length > 120) {
    return { ok: false, reason: 'INVALID_IDENTITY' };
  }
  const text = optionalText(candidate.text);
  if (!text || text.length > 2000) return { ok: false, reason: 'INVALID_TEXT' };
  const folded = text.toLocaleLowerCase('en-US');
  if (INTERNAL_TEXT_MARKERS.some((marker) => folded.includes(marker))) {
    return { ok: false, reason: 'INTERNAL_CONTENT' };
  }
  if (SECRET_PATTERNS.some((pattern) => pattern.test(text))) {
    return { ok: false, reason: 'SECRET_SHAPED_CONTENT' };
  }
  if (!Array.isArray(candidate.canonicalReferenceHashes)) {
    return { ok: false, reason: 'INVALID_REFERENCES' };
  }
  const refs = candidate.canonicalReferenceHashes.map(exactHash);
  if (refs.some((value) => value === null) || refs.length > 32) {
    return { ok: false, reason: 'INVALID_REFERENCES' };
  }

  const sessionBindingHash = exactHash(candidate.sessionBindingHash);
  const runId = optionalText(candidate.runId);
  const attemptId = optionalText(candidate.attemptId);
  const workflowState = optionalText(candidate.workflowState)?.toUpperCase() ?? null;
  const boundRevision = exactRevision(candidate.boundRevision);
  const effectKind = optionalText(candidate.effectKind)?.toUpperCase() ?? null;
  const targetHash = exactHash(candidate.targetHash);
  const consentBindingHash = exactHash(candidate.consentBindingHash);

  if (bubbleKind === 'MISSION_INPUT') {
    if (
      workflowState !== 'RECORDED'
      || refs.length !== 0
      || sessionBindingHash
      || runId
      || attemptId
      || boundRevision
      || effectKind
      || targetHash
      || consentBindingHash
    ) {
      return { ok: false, reason: 'MISSING_CANONICAL_BINDING' };
    }
  } else {
    if (!sessionBindingHash || !runId || !attemptId || refs.length === 0) {
      return { ok: false, reason: 'MISSING_CANONICAL_BINDING' };
    }
    if (bubbleKind === 'REQUIRED_QUESTION' && workflowState !== 'WAITING_FOR_USER') {
      return { ok: false, reason: 'INVALID_WORKFLOW_STATE' };
    }
    if (
      bubbleKind === 'MATERIAL_BLOCKER'
      && !['BLOCKED', 'FAILED', 'UNVERIFIED', 'CONTRADICTED'].includes(workflowState ?? '')
    ) {
      return { ok: false, reason: 'INVALID_WORKFLOW_STATE' };
    }
    if (
      bubbleKind === 'OWNER_CONSENT_REQUEST'
      && (
        workflowState !== 'WAITING_FOR_USER'
        || !boundRevision
        || !effectKind
        || !targetHash
        || !consentBindingHash
      )
    ) {
      return { ok: false, reason: 'MISSING_CANONICAL_BINDING' };
    }
    if (
      bubbleKind === 'FINAL_RESULT'
      && (workflowState !== 'VERIFIED' || !boundRevision || effectKind || consentBindingHash)
    ) {
      return { ok: false, reason: 'MISSING_CANONICAL_BINDING' };
    }
  }

  return {
    ok: true,
    bubble: {
      schemaVersion: 'sovereign.live-workspace-chat-bubble.v1',
      persistenceSchemaVersion: optionalText(candidate.persistenceSchemaVersion) ?? undefined,
      sessionId,
      clientMessageId,
      bubbleKind,
      sourceKind,
      text,
      canonicalReferenceHashes: refs as string[],
      sessionBindingHash: sessionBindingHash ?? undefined,
      runId: runId ?? undefined,
      attemptId: attemptId ?? undefined,
      workflowState: workflowState ?? 'RECORDED',
      boundRevision: boundRevision ?? undefined,
      effectKind: effectKind ?? undefined,
      targetHash: targetHash ?? undefined,
      consentBindingHash: consentBindingHash ?? undefined,
      bubbleHash,
      recordedAt: optionalText(candidate.recordedAt) ?? undefined,
      authoritative: false,
    },
  };
}

export function projectSituationalChatLine(line: ChatLine): ChatLine | null {
  if (!line.bubble) return null;
  const committed = commitSituationalBubble(line.bubble);
  if (!committed.ok || line.text !== committed.bubble.text) return null;
  const expectedRole = committed.bubble.bubbleKind === 'MISSION_INPUT' ? 'user' : 'assistant';
  if (line.role !== expectedRole) return null;
  return { ...line, bubble: committed.bubble };
}

export function projectConversationChatLine(line: ChatLine): ChatLine | null {
  // Persisted workflow truth must pass the complete bubble firewall. It shares
  // the same visible chat with safe transient conversation, but never loses its
  // stronger canonical binding.
  if (line.bubble) return projectSituationalChatLine(line);

  // Non-authoritative assistant/runtime conversation is allowed into the chat
  // only through an explicit conversation-only provenance envelope. Raw
  // provider/system text can never opt itself into the visible conversation.
  const projection = line.conversationProjection;
  if (!projection || Object.keys(projection).some((key) => ![
    'schemaVersion',
    'sourceKind',
    'authority',
    'authoritative',
  ].includes(key))) return null;
  if (
    projection.schemaVersion !== 'sovereign.conversation-projection.v1'
    || projection.authority !== 'CONVERSATION_ONLY'
    || projection.authoritative !== false
  ) return null;
  const expectedRole = projection.sourceKind === 'LLM_RESPONSE'
    ? 'assistant'
    : projection.sourceKind === 'RUNTIME_NOTICE'
      ? 'system'
      : null;
  if (!expectedRole || line.role !== expectedRole) return null;
  const text = optionalText(line.text);
  if (!text || text.length > 4000) return null;
  const folded = text.toLocaleLowerCase('en-US');
  if (INTERNAL_TEXT_MARKERS.some((marker) => folded.includes(marker))) return null;
  if (SECRET_PATTERNS.some((pattern) => pattern.test(text))) return null;
  return { ...line, text, conversationProjection: projection };
}

export function projectSituationalChatLines(lines: readonly ChatLine[]): ChatLine[] {
  return lines.map(projectSituationalChatLine).filter((line): line is ChatLine => line !== null);
}

export function bubbleKindLabel(kind: SituationalBubbleKind): string {
  switch (kind) {
    case 'MISSION_INPUT': return 'Mission';
    case 'REQUIRED_QUESTION': return 'Rückfrage';
    case 'OWNER_CONSENT_REQUEST': return 'Freigabe erforderlich';
    case 'MATERIAL_BLOCKER': return 'Blocker';
    case 'FINAL_RESULT': return 'Ergebnis';
  }
}

export function minimizeBubbleProjection(bubble: SituationalBubbleBinding) {
  return {
    bubbleHash: bubble.bubbleHash,
    minimized: true as const,
    workflowMutation: null,
    permissionDecision: null,
    resumeSignal: null,
  };
}
