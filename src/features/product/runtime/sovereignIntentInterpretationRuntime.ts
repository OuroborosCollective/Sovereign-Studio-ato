import {
  classifyIntent,
  determineTaskComplexity,
} from './sovereignCapabilityRouter';
import type {
  IntentClassification,
  SovereignIntentInterpretation,
  TaskComplexity,
} from './sovereignCapabilityTypes';

const API_BASE = (
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined)?.trim()
  || 'https://sovereign-backend.arelorian.de'
).replace(/\/$/, '');

const INTENTS: readonly IntentClassification[] = [
  'free_chat',
  'status_question',
  'load_repo',
  'direct_patch',
  'code_generation',
  'draft_pr',
  'workflow_watch',
  'repair_workflow',
  'unknown',
];

const COMPLEXITIES: readonly TaskComplexity[] = [
  'simple',
  'medium',
  'complex',
  'unknown',
];

interface LlmRouteDescriptor {
  readonly id: string;
  readonly defaultModelId: string;
  readonly enabled: boolean;
}

interface IntentPayload {
  readonly intent?: unknown;
  readonly complexity?: unknown;
  readonly normalizedRequest?: unknown;
  readonly assistantMessage?: unknown;
  readonly requiresWrite?: unknown;
  readonly requiresDraftPr?: unknown;
  readonly confidence?: unknown;
}

export interface ResolveSovereignIntentInput {
  readonly text: string;
  readonly repositoryContext?: string;
  readonly recentMessages?: readonly { readonly role: string; readonly text: string }[];
  readonly modelId?: string;
  readonly requestId?: string;
  readonly fetchImpl?: typeof fetch;
}

function isIntent(value: unknown): value is IntentClassification {
  return typeof value === 'string' && INTENTS.includes(value as IntentClassification);
}

function isComplexity(value: unknown): value is TaskComplexity {
  return typeof value === 'string' && COMPLEXITIES.includes(value as TaskComplexity);
}

function isExactControlInput(text: string): boolean {
  const clean = text.trim();
  return clean.startsWith('/')
    || /^https?:\/\/github\.com\/[\w-]+\/[\w.-]+(?:\/.*)?$/i.test(clean);
}

export function buildOfflineIntentInterpretation(text: string): SovereignIntentInterpretation {
  const intent = classifyIntent(text);
  const complexity = determineTaskComplexity(intent, text);
  return {
    intent,
    complexity,
    normalizedRequest: text.trim(),
    requiresWrite: ['direct_patch', 'code_generation', 'draft_pr', 'repair_workflow'].includes(intent),
    requiresDraftPr: intent === 'draft_pr',
    confidence: intent === 'unknown' ? 0 : 0.35,
    source: 'offline_fallback',
  };
}

function extractJsonObject(content: string): unknown {
  const trimmed = content.trim();
  const unfenced = trimmed
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/i, '')
    .trim();
  const start = unfenced.indexOf('{');
  const end = unfenced.lastIndexOf('}');
  if (start < 0 || end <= start) throw new Error('intent_json_missing');
  return JSON.parse(unfenced.slice(start, end + 1));
}

export function parseOnlineIntentInterpretation(
  content: string,
  context: { readonly text: string; readonly modelId: string; readonly requestId: string },
): SovereignIntentInterpretation {
  const payload = extractJsonObject(content) as IntentPayload;
  if (!isIntent(payload.intent)) throw new Error('intent_invalid');
  if (!isComplexity(payload.complexity)) throw new Error('complexity_invalid');
  if (typeof payload.normalizedRequest !== 'string' || !payload.normalizedRequest.trim()) {
    throw new Error('normalized_request_invalid');
  }
  if (typeof payload.assistantMessage !== 'string' || !payload.assistantMessage.trim()) {
    throw new Error('assistant_message_invalid');
  }
  if (typeof payload.requiresWrite !== 'boolean') throw new Error('requires_write_invalid');
  if (typeof payload.requiresDraftPr !== 'boolean') throw new Error('requires_draft_pr_invalid');
  if (typeof payload.confidence !== 'number' || !Number.isFinite(payload.confidence)) {
    throw new Error('confidence_invalid');
  }

  const confidence = Math.max(0, Math.min(1, payload.confidence));
  const writeIntent = ['direct_patch', 'code_generation', 'draft_pr', 'repair_workflow'].includes(payload.intent);
  if (payload.requiresWrite !== writeIntent) throw new Error('intent_write_contract_mismatch');
  if (payload.requiresDraftPr !== (payload.intent === 'draft_pr')) {
    throw new Error('intent_draft_pr_contract_mismatch');
  }

  return {
    intent: payload.intent,
    complexity: payload.complexity,
    normalizedRequest: payload.normalizedRequest.trim(),
    assistantMessage: payload.assistantMessage.trim(),
    requiresWrite: payload.requiresWrite,
    requiresDraftPr: payload.requiresDraftPr,
    confidence,
    source: 'online_llm',
    modelId: context.modelId,
    requestId: context.requestId,
  };
}

async function resolveModelId(fetchImpl: typeof fetch, explicitModelId?: string): Promise<string> {
  if (explicitModelId?.trim()) return explicitModelId.trim();
  const response = await fetchImpl(`${API_BASE}/api/llm/routes`, {
    method: 'GET',
    credentials: 'include',
  });
  if (!response.ok) throw new Error(`intent_route_catalog_http_${response.status}`);
  const payload = await response.json() as { readonly routes?: readonly LlmRouteDescriptor[] };
  const route = payload.routes?.find((candidate) => candidate.enabled && candidate.defaultModelId?.trim());
  if (!route) throw new Error('intent_route_unavailable');
  return route.defaultModelId.trim();
}

function buildIntentMessages(input: ResolveSovereignIntentInput): readonly { role: string; content: string }[] {
  const history = (input.recentMessages ?? [])
    .slice(-6)
    .map((message) => `${message.role}: ${message.text}`)
    .join('\n');
  return [
    {
      role: 'system',
      content: [
        'Du bist ausschließlich der semantische Intent-Interpreter für Sovereign Studio.',
        'Du darfst keine Aktion ausführen und keinen Erfolg behaupten.',
        'Gib exakt ein JSON-Objekt ohne Markdown aus.',
        'Schema: {"intent":"free_chat|status_question|load_repo|direct_patch|code_generation|draft_pr|workflow_watch|repair_workflow|unknown","complexity":"simple|medium|complex|unknown","normalizedRequest":"string","assistantMessage":"string","requiresWrite":boolean,"requiresDraftPr":boolean,"confidence":number}.',
        'Bedeutung: direct_patch nur für eine eindeutig kleine einzelne Docs-/Textänderung; code_generation für Code/Fehlerbehebung; draft_pr sobald das gewünschte Ergebnis ausdrücklich ein Draft PR ist; repair_workflow für CI-/Workflow-Reparatur; workflow_watch nur lesend; free_chat für Beratung/Erklärung.',
        'requiresWrite muss genau bei direct_patch, code_generation, draft_pr oder repair_workflow wahr sein.',
        'requiresDraftPr muss genau bei draft_pr wahr sein.',
        'assistantMessage beantwortet reine Gespräche direkt und bleibt knapp. Bei Aktionsaufträgen bestätigt es nur das Verständnis und behauptet niemals Ausführung, Dateiänderung, Test, Commit oder PR ohne Runtime-Evidence.',
        'normalizedRequest muss exakte Datei-/Repository-Namen, Pfade, Zahlen, Verbote und Zielbedingungen aus dem Usertext erhalten.',
        'Bewerte die Bedeutung des gesamten Satzes, nicht einzelne Schlüsselwörter.',
      ].join('\n'),
    },
    {
      role: 'user',
      content: [
        input.repositoryContext ? `Repository-Kontext: ${input.repositoryContext}` : '',
        history ? `Letzter Chat-Kontext:\n${history}` : '',
        `Aktueller Usertext:\n${input.text}`,
      ].filter(Boolean).join('\n\n'),
    },
  ];
}

export async function resolveSovereignIntent(
  input: ResolveSovereignIntentInput,
): Promise<SovereignIntentInterpretation> {
  const clean = input.text.trim();
  const fallback = buildOfflineIntentInterpretation(clean);
  if (!clean || isExactControlInput(clean)) return fallback;

  const fetchImpl = input.fetchImpl ?? globalThis.fetch;
  if (typeof fetchImpl !== 'function') return fallback;

  try {
    const modelId = await resolveModelId(fetchImpl, input.modelId);
    const requestId = input.requestId
      ?? globalThis.crypto?.randomUUID?.();
    if (!requestId) return fallback;

    const response = await fetchImpl(`${API_BASE}/api/llm/chat`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        requestId,
        model: modelId,
        messages: buildIntentMessages(input),
        max_tokens: 400,
        stream: false,
      }),
    });
    if (!response.ok) return fallback;
    const payload = await response.json() as {
      readonly choices?: readonly { readonly message?: { readonly content?: unknown } }[];
    };
    const content = payload.choices?.[0]?.message?.content;
    if (typeof content !== 'string' || !content.trim()) return fallback;
    return parseOnlineIntentInterpretation(content, { text: clean, modelId, requestId });
  } catch {
    return fallback;
  }
}
