import { describe, expect, it } from 'vitest';
import type { ChatLine, SituationalBubbleBinding } from './builderContainerTypes';
import {
  commitSituationalBubble,
  minimizeBubbleProjection,
  projectMonitorCommunicationLine,
  projectSituationalChatLine,
  projectSituationalChatLines,
} from './situationalBubbleRuntime';

const HASH_A = 'a'.repeat(64);
const HASH_B = 'b'.repeat(64);
const REVISION = 'c'.repeat(40);

function mission(overrides: Partial<SituationalBubbleBinding> = {}): SituationalBubbleBinding {
  return {
    schemaVersion: 'sovereign.live-workspace-chat-bubble.v1',
    persistenceSchemaVersion: 'sovereign.live-workspace-chat-persistence.v1',
    sessionId: 'livechat-' + 'd'.repeat(24),
    clientMessageId: 'msg-1',
    bubbleKind: 'MISSION_INPUT',
    sourceKind: 'USER_INPUT',
    text: 'Repariere den Login und erstelle einen Draft PR.',
    canonicalReferenceHashes: [],
    workflowState: 'RECORDED',
    bubbleHash: HASH_A,
    authoritative: false,
    ...overrides,
  };
}

function line(bubble: SituationalBubbleBinding, role: ChatLine['role'] = 'user'): ChatLine {
  return { id: bubble.bubbleHash, role, text: bubble.text, createdAt: 1, bubble };
}

describe('situational bubble output firewall', () => {
  it('commits a server-persisted mission and rejects an untyped assistant line', () => {
    expect(commitSituationalBubble(mission()).ok).toBe(true);
    expect(projectSituationalChatLine({ id: 'raw', role: 'assistant', text: 'Tests laufen gerade.' })).toBeNull();
  });

  it('allows only the five typed classes', () => {
    expect(commitSituationalBubble({ ...mission(), bubbleKind: 'STATUS_STREAM' }).ok).toBe(false);
    expect(commitSituationalBubble({ ...mission(), bubbleKind: 'THINKING' }).ok).toBe(false);
  });

  it('blocks the observed reasoning and internal-field regression payloads', () => {
    expect(commitSituationalBubble({ ...mission(), text: "Here's a thinking process about the task." })).toEqual({
      ok: false,
      reason: 'INTERNAL_CONTENT',
    });
    expect(commitSituationalBubble({ ...mission(), providerRequestId: 'provider-internal' })).toEqual({
      ok: false,
      reason: 'UNKNOWN_FIELD',
    });
  });

  it('blocks secret-shaped content before a user-visible commit', () => {
    const secret = ['github', 'pat', 'x'.repeat(40)].join('_');
    expect(commitSituationalBubble({ ...mission(), text: secret })).toEqual({
      ok: false,
      reason: 'SECRET_SHAPED_CONTENT',
    });
  });

  it('requires exact workflow bindings for questions, blockers and final results', () => {
    const question = {
      ...mission(),
      bubbleKind: 'REQUIRED_QUESTION' as const,
      sourceKind: 'CANONICAL_WORKFLOW' as const,
      workflowState: 'WAITING_FOR_USER',
      canonicalReferenceHashes: [HASH_B],
    };
    expect(commitSituationalBubble(question)).toEqual({ ok: false, reason: 'MISSING_CANONICAL_BINDING' });

    const final = {
      ...question,
      bubbleKind: 'FINAL_RESULT' as const,
      sourceKind: 'EFFECT_READBACK' as const,
      sessionBindingHash: HASH_A,
      runId: 'run-1',
      attemptId: 'attempt-1',
      workflowState: 'VERIFIED',
      boundRevision: REVISION,
    };
    expect(commitSituationalBubble(final).ok).toBe(true);
    expect(commitSituationalBubble({ ...final, boundRevision: undefined })).toEqual({
      ok: false,
      reason: 'MISSING_CANONICAL_BINDING',
    });
  });

  it('requires consent to bind the exact effect, target, revision and consent contract', () => {
    const consent = {
      ...mission(),
      bubbleKind: 'OWNER_CONSENT_REQUEST' as const,
      sourceKind: 'CONSENT_CONTRACT' as const,
      canonicalReferenceHashes: [HASH_B],
      sessionBindingHash: HASH_A,
      runId: 'run-1',
      attemptId: 'attempt-1',
      workflowState: 'WAITING_FOR_USER',
      boundRevision: REVISION,
      effectKind: 'DEPLOYMENT',
      targetHash: HASH_B,
      consentBindingHash: HASH_A,
    };
    expect(commitSituationalBubble(consent).ok).toBe(true);
    expect(commitSituationalBubble({ ...consent, consentBindingHash: undefined }).ok).toBe(false);
  });

  it('never turns visual minimization into answer, approval or resume authority', () => {
    expect(minimizeBubbleProjection(mission())).toEqual({
      bubbleHash: HASH_A,
      minimized: true,
      workflowMutation: null,
      permissionDecision: null,
      resumeSignal: null,
    });
  });

  it('projects only role-matched committed bubbles', () => {
    const typedMission = line(mission());
    const wrongRole = line(mission({ bubbleHash: HASH_B }), 'assistant');
    expect(projectMonitorCommunicationLine(typedMission)).toEqual(typedMission);
    expect(projectSituationalChatLines([
      typedMission,
      wrongRole,
      { id: 'system', role: 'system', text: 'Repo verbunden' },
      { id: 'thought', role: 'thought', text: 'Ich prüfe jetzt Dateien.' },
    ])).toEqual([typedMission]);
  });

  it('requires explicit non-authoritative provenance for monitor-only conversation', () => {
    const safe = { id: 'safe', role: 'assistant' as const, text: 'Die Analyse läuft.', createdAt: 1 };
    expect(projectSituationalChatLine(safe)).toBeNull();
    expect(projectMonitorCommunicationLine(safe)).toBeNull();

    const conversation = {
      ...safe,
      monitorProjection: {
        schemaVersion: 'sovereign.monitor-communication-projection.v1' as const,
        sourceKind: 'LLM_RESPONSE' as const,
        authority: 'CONVERSATION_ONLY' as const,
        authoritative: false as const,
      },
    };
    expect(projectMonitorCommunicationLine(conversation)).toEqual(conversation);
    expect(projectMonitorCommunicationLine({ ...conversation, role: 'system' })).toBeNull();
    expect(projectMonitorCommunicationLine({ ...conversation, text: 'Reasoning: hidden provider trace' })).toBeNull();
    expect(projectMonitorCommunicationLine({
      ...conversation,
      text: ['github', 'pat', 'x'.repeat(40)].join('_'),
    })).toBeNull();
  });

  it('never downgrades an invalid typed bubble to ephemeral monitor text', () => {
    const wrongRole = line(mission(), 'assistant');
    expect(projectSituationalChatLine(wrongRole)).toBeNull();
    expect(projectMonitorCommunicationLine(wrongRole)).toBeNull();
    expect(projectMonitorCommunicationLine({
      ...line(mission()),
      text: 'Text does not match the committed bubble.',
    })).toBeNull();
  });
});
