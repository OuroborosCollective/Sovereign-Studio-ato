import { classifyBackendRoute, type ResolvedTransportClass } from './providerRuntimeChecks';
import {
  DEV_CHAT_WORKER_DEFAULT_MODEL,
  DEV_CHAT_WORKER_FALLBACK_MODEL,
  type DevChatWorkerDiagnostic,
  type DevChatWorkerIntentKind,
  type DevChatWorkerInterpretation,
  type DevChatWorkerInterpretationResult,
  type DevChatWorkerMessage,
} from './devChatWorkerBridge';

const BACKEND_BASE = (
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined)?.trim()
  || 'https://sovereign-backend.arelorian.de'
).replace(/\/$/, '');

export const SOVEREIGN_DIRECT_LLM_ROUTES = `${BACKEND_BASE}/api/llm/routes` as const;
export const SOVEREIGN_CODE_ACTION_ROUTES = `${SOVEREIGN_DIRECT_LLM_ROUTES}?purpose=action-contract` as const;
export const SOVEREIGN_DIRECT_LLM_CHAT = `${BACKEND_BASE}/api/llm/chat` as const;
export const SOVEREIGN_CODE_ACTION_CONTRACT_ID = 'sovereign-code-action-v1' as const;
/** @deprecated Compatibility alias. Productive transport: direct OpenRouter/FreeLLM. */
export const SOVEREIGN_LITELLM_ROUTES = SOVEREIGN_DIRECT_LLM_ROUTES;
/** @deprecated Compatibility alias. Productive transport: direct OpenRouter/FreeLLM. */
export const SOVEREIGN_LITELLM_CHAT = SOVEREIGN_DIRECT_LLM_CHAT;
export const SOVEREIGN_INTENT_TIMEOUT_MS = 30_000;

interface DirectLlmRouteDescriptor {
  readonly id?: unknown;
  readonly defaultModelId?: unknown;
  readonly enabled?: unknown;
  readonly provider?: unknown;
  readonly billingCategory?: unknown;
  readonly fundingMode?: unknown;
  readonly capabilities?: unknown;
}

interface DirectLlmRouteCapabilities {
  readonly codeActionContract?: unknown;
}

interface DirectLlmRouteCatalog {
  readonly routes?: unknown;
}

interface SovereignIntentEnvelope {
  readonly mode?: unknown;
  readonly intent?: unknown;
  readonly action_disposition?: unknown;
  readonly clarification_code?: unknown;
  readonly is_startup?: unknown;
  readonly confidence?: unknown;
  readonly language?: unknown;
}

export interface SovereignDirectLlmIntentRequest {
  readonly preferredModel?: string;
  readonly text: string;
  readonly repoContext?: string;
  readonly runtimeContext?: string;
  readonly recentMessages?: readonly DevChatWorkerMessage[];
  readonly signal?: AbortSignal;
  readonly fetchImpl?: typeof fetch;
  readonly requestId?: string;
}

/** @deprecated Compatibility type for callers not migrated yet. */
export type SovereignLiteLlmIntentRequest = SovereignDirectLlmIntentRequest;

const ALLOWED_INTENTS: readonly DevChatWorkerIntentKind[] = [
  'free_chat',
  'status',
  'direct_patch',
  'code_execution',
  'draft_pr',
  'workflow_watch',
  'repair_workflow',
  'load_repo',
  'unknown',
];

const CLARIFICATION_TEXT: Readonly<Record<string, string>> = {
  repo_required: 'Welches Repository soll ich ändern?',
  change_required: 'Welche konkrete Änderung soll ich umsetzen?',
  expected_result_required: 'Welches überprüfbare Ergebnis soll nach der Änderung gelten?',
};

const ACTION_TITLE_BY_INTENT: Readonly<Partial<Record<DevChatWorkerIntentKind, string>>> = {
  direct_patch: 'Codeänderung vorbereiten',
  code_execution: 'Repository-Auftrag ausführen',
  draft_pr: 'Draft PR vorbereiten',
  workflow_watch: 'Workflow prüfen',
  repair_workflow: 'Workflow reparieren',
  load_repo: 'Repository laden',
};

const CODE_ACTION_WIRE_KEYS = new Set([
  'mode',
  'intent',
  'action_disposition',
  'clarification_code',
  'is_startup',
  'confidence',
  'language',
]);

function boundedSnippet(value: string): string | undefined {
  const clean = value.replace(/\s+/g, ' ').trim();
  return clean ? clean.slice(0, 420) : undefined;
}

function readJsonObject(text: string): Record<string, unknown> | null {
  if (!text.trim()) return null;
  try {
    const value = JSON.parse(text) as unknown;
    return value && typeof value === 'object'
      ? value as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
}

function readCompletionContent(payload: Record<string, unknown>): string | undefined {
  const choices = payload.choices;
  if (!Array.isArray(choices)) return undefined;
  for (const choice of choices) {
    if (!choice || typeof choice !== 'object') continue;
    const message = (choice as Record<string, unknown>).message;
    if (!message || typeof message !== 'object') continue;
    const content = (message as Record<string, unknown>).content;
    if (typeof content === 'string' && content.trim()) return content.trim();
  }
  return undefined;
}

function readModel(payload: Record<string, unknown>, fallback: string): string {
  return typeof payload.model === 'string' && payload.model.trim()
    ? payload.model.trim()
    : fallback;
}

function parseIntentEnvelope(
  content: string,
  model: string,
  fallbackUsed: boolean,
): DevChatWorkerInterpretation | null {
  const clean = content
    .trim()
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/i, '');
  const payload = readJsonObject(clean) as SovereignIntentEnvelope | null;
  if (
    !payload
    || Object.keys(payload).length !== CODE_ACTION_WIRE_KEYS.size
    || Object.keys(payload).some((key) => !CODE_ACTION_WIRE_KEYS.has(key))
  ) {
    return null;
  }

  const wireMode = payload.mode;
  const mode = wireMode === 'clarify' ? 'chat' : wireMode;
  const intent = payload.intent;
  if (mode !== 'chat' && mode !== 'action') return null;
  if (
    payload.action_disposition !== 'review'
    || typeof intent !== 'string'
    || !ALLOWED_INTENTS.includes(intent as DevChatWorkerIntentKind)
  ) {
    return null;
  }

  // The compiler can describe an action but can never authorize it.
  // Every write remains review-gated until the owner confirms the visible draft.
  const actionDisposition = 'review' as const;
  const clarificationCode = typeof payload.clarification_code === 'string'
    ? payload.clarification_code
    : '';
  const assistantText = CLARIFICATION_TEXT[clarificationCode] ?? '';
  const actionTitle = typeof intent === 'string'
    ? ACTION_TITLE_BY_INTENT[intent as DevChatWorkerIntentKind] ?? ''
    : '';
  if (typeof payload.is_startup !== 'boolean') return null;
  const isStartup = payload.is_startup;
  const confidence = typeof payload.confidence === 'number'
    && Number.isFinite(payload.confidence)
    && payload.confidence >= 0
    && payload.confidence <= 1
    ? payload.confidence
    : -1;
  const language = typeof payload.language === 'string'
    ? payload.language.trim()
    : '';

  if (confidence < 0 || !language || language.length > 16) return null;
  if (mode === 'chat' && (
    !assistantText
    || intent !== 'unknown'
    || clarificationCode === 'none'
  )) return null;
  if (mode === 'action' && (
    !actionTitle
    || clarificationCode !== 'none'
    || confidence < 0.5
    || intent === 'free_chat'
    || intent === 'unknown'
    || intent === 'status'
  )) return null;

  return {
    mode,
    intent: intent as DevChatWorkerIntentKind,
    actionDisposition,
    assistantText,
    actionTitle,
    confidence,
    language,
    model,
    fallbackUsed,
    isStartup,
  };
}

function createDiagnostic(args: {
  readonly route: string;
  readonly model: string;
  readonly messageCount: number;
  readonly status?: number;
  readonly statusText?: string;
  readonly body?: string;
  readonly error?: unknown;
}): DevChatWorkerDiagnostic {
  const status = args.status;
  const body = args.body ?? (args.error instanceof Error ? args.error.message : '');
  let blocker: unknown;
  try {
    const payload: unknown = JSON.parse(body);
    if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
      blocker = (payload as { blocker?: unknown }).blocker;
    }
  } catch {
    // A non-JSON response carries no typed backend blocker.
  }
  if (status === 502 && blocker === 'llm_output_contract_violation') {
    return {
      route: args.route,
      model: args.model,
      messageCount: args.messageCount,
      status,
      statusText: args.statusText,
      scope: 'worker_runtime',
      canClientFix: false,
      nextAction: 'Backend-Ausgabevertrag prüfen: vollständiges Schema an den Provider senden und die Antwort vor Erfolgsmeldung validieren; keine lokale Sprachdeutung starten.',
    };
  }
  if (status === 402) {
    return {
      route: args.route,
      model: args.model,
      messageCount: args.messageCount,
      status,
      statusText: args.statusText,
      bodySnippet: boundedSnippet(body),
      scope: 'client_request',
      canClientFix: false,
      nextAction: 'Backend-Credit-Gate prüfen oder Credits aufladen; keine zweite Frontend-Abbuchung ausführen.',
    };
  }
  if (status === 401) {
    return {
      route: args.route,
      model: args.model,
      messageCount: args.messageCount,
      status,
      statusText: args.statusText,
      bodySnippet: boundedSnippet(body),
      scope: 'authentication',
      canClientFix: true,
      nextAction: 'Backend-Session erneut bestätigen oder anmelden; keine Provider-Secrets im Client verwenden.',
    };
  }
  if (status === 403) {
    return {
      route: args.route,
      model: args.model,
      messageCount: args.messageCount,
      status,
      statusText: args.statusText,
      bodySnippet: boundedSnippet(body),
      scope: 'authentication',
      canClientFix: false,
      nextAction: 'Berechtigung der bestätigten Backend-Session prüfen; erneutes Anmelden darf nicht als automatische Lösung angeboten werden.',
    };
  }
  if (status === 400 || status === 404 || status === 405 || status === 428) {
    return {
      route: args.route,
      model: args.model,
      messageCount: args.messageCount,
      status,
      statusText: args.statusText,
      bodySnippet: boundedSnippet(body),
      scope: 'client_request',
      canClientFix: true,
      nextAction: 'Sovereign LLM-Routenvertrag, Transport, Modell-ID, Request-ID und Nachrichtenformat prüfen.',
    };
  }
  if (status === 429 || status === 502 || status === 503 || status === 504) {
    return {
      route: args.route,
      model: args.model,
      messageCount: args.messageCount,
      status,
      statusText: args.statusText,
      bodySnippet: boundedSnippet(body),
      scope: 'upstream_provider',
      canClientFix: false,
      nextAction: 'OpenRouter-/FreeLLM-Route und Rate-Limit prüfen; keine lokale Sprachdeutung starten.',
    };
  }
  if (status && status >= 500) {
    return {
      route: args.route,
      model: args.model,
      messageCount: args.messageCount,
      status,
      statusText: args.statusText,
      bodySnippet: boundedSnippet(body),
      scope: 'worker_runtime',
      canClientFix: false,
      nextAction: 'Backend- und Direkttransport-Evidence prüfen; den Call nicht blind als erfolgreich behandeln.',
    };
  }
  return {
    route: args.route,
    model: args.model,
    messageCount: args.messageCount,
    status,
    statusText: args.statusText,
    bodySnippet: boundedSnippet(body),
    scope: 'network',
    canClientFix: false,
    nextAction: 'Backend-Erreichbarkeit, CORS oder Netzwerk prüfen; keine lokale Sprachdeutung starten.',
  };
}

function createRequestId(): string | null {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  if (typeof globalThis.crypto?.getRandomValues !== 'function') return null;
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function isAbstractSovereignRouteAlias(value: string | undefined): boolean {
  const clean = value?.trim();
  return clean === DEV_CHAT_WORKER_DEFAULT_MODEL || clean === DEV_CHAT_WORKER_FALLBACK_MODEL;
}

function chooseRoute(
  payload: DirectLlmRouteCatalog,
  preferredModel: string | undefined,
): {
  readonly routeId: string;
  readonly modelId: string;
  readonly resolvedTransportClass: Exclude<ResolvedTransportClass, 'UNRESOLVED'>;
  readonly billingCategory: 'free' | 'standard' | 'premium';
  readonly pricingDisplay: string;
} | null {
  if (!Array.isArray(payload.routes)) return null;
  const enabled = payload.routes.flatMap((candidate) => {
    if (!candidate || typeof candidate !== 'object') return [];
    const route = candidate as DirectLlmRouteDescriptor;
    if (route.enabled !== true) return [];
    const classification = classifyBackendRoute(route);
    if (!classification) return [];
    const routeId = typeof route.id === 'string' ? route.id.trim() : '';
    const modelId = typeof route.defaultModelId === 'string' ? route.defaultModelId.trim() : '';
    const capabilities = route.capabilities && typeof route.capabilities === 'object'
      ? route.capabilities as DirectLlmRouteCapabilities
      : null;
    return routeId && modelId && capabilities?.codeActionContract === true ? [{
      routeId,
      modelId,
      resolvedTransportClass: classification.resolvedTransportClass,
      billingCategory: classification.billingCategory,
      pricingDisplay: classification.pricingDisplay,
    }] : [];
  });
  if (enabled.length === 0) return null;
  const cleanPreferred = preferredModel?.trim();
  if (!cleanPreferred || isAbstractSovereignRouteAlias(cleanPreferred)) {
    // Auto may use only a verified zero-cost structured route. Selecting a paid
    // compiler here would create spend without the owner's explicit route pin
    // and step-up approval.
    return enabled.find((route) => route.billingCategory === 'free') ?? null;
  }

  // A manual concrete route/model pin is a hard user-visible contract. If it
  // is no longer present in the backend catalog, intent interpretation must
  // fail closed instead of silently executing a different route.
  return enabled.find((route) =>
    route.routeId === cleanPreferred || route.modelId === cleanPreferred
  ) ?? null;
}

function buildMessages(args: SovereignDirectLlmIntentRequest): readonly DevChatWorkerMessage[] {
  const systemPrompt = [
    'Du bist ausschließlich der strukturierte Codeauftrags-Compiler von Sovereign Studio.',
    'Kein Smalltalk, keine Erzählung, keine Ratschläge und keine Erfolgsbehauptung.',
    'Du führst selbst nichts aus. Die Runtime prüft Repo, GitHub-Zugang, Workspace, Tests, Freigabe und Draft-PR-Evidence.',
    'Antworte ausschließlich im serverseitig erzwungenen JSON-Schema.',
    'mode=action gilt für konkrete Code-, Repository-, Test-, Workflow- oder Draft-PR-Aufträge.',
    'Jede Aktion bleibt action_disposition=review, damit vor jeder schreibenden Ausführung eine sichtbare Freigabe erfolgt.',
    'mode=clarify ist ausschließlich für genau eine Gegenfrage erlaubt; intent ist dann unknown.',
    'Nutze nur clarification_code: repo_required, change_required oder expected_result_required.',
    'Bei mode=action ist clarification_code=none. Nie freie Antworttexte oder allgemeine Unterhaltung.',
    'Bewerte nur den aktuellen Auftrag, nicht frühere Chatnachrichten und nicht einzelne Schlüsselwörter.',
    args.repoContext ? `Runtime-Repo-Kontext: ${args.repoContext}` : 'Runtime-Repo-Kontext: nicht geladen.',
    args.runtimeContext ? `Belegte Runtime-Fakten (nur Fakten, keine Sprachdeutung):\n${args.runtimeContext}` : 'Belegte Runtime-Fakten (nur Fakten, keine Sprachdeutung): keine zusätzlichen Fakten.',
  ].join('\n');
  return [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: args.text },
  ];
}

export async function fetchSovereignDirectLlmInterpretation(
  args: SovereignDirectLlmIntentRequest,
): Promise<DevChatWorkerInterpretationResult> {
  const fetchImpl = args.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const messages = buildMessages(args);
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), SOVEREIGN_INTENT_TIMEOUT_MS);
  const signal = args.signal
    ? AbortSignal.any([args.signal, timeoutController.signal])
    : timeoutController.signal;
  const fallbackModel = args.preferredModel?.trim() || 'route-catalog';

  try {
    const routeResponse = await fetchImpl(SOVEREIGN_CODE_ACTION_ROUTES, {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' },
      signal,
    });
    const routeText = await routeResponse.text();
    if (!routeResponse.ok) {
      return {
        ok: false,
        error: `Sovereign LLM-Routenkatalog HTTP ${routeResponse.status}`,
        diagnostic: createDiagnostic({
          route: SOVEREIGN_LITELLM_ROUTES,
          model: fallbackModel,
          messageCount: messages.length,
          status: routeResponse.status,
          statusText: routeResponse.statusText,
          body: routeText,
        }),
      };
    }

    const routePayload = readJsonObject(routeText) as DirectLlmRouteCatalog | null;
    const selected = routePayload ? chooseRoute(routePayload, args.preferredModel) : null;
    if (!selected) {
      return {
        ok: false,
        error: 'Keine explizit freigegebene Route erfüllt den strukturierten Codeauftragsvertrag.',
        diagnostic: {
          route: SOVEREIGN_LITELLM_ROUTES,
          model: fallbackModel,
          messageCount: messages.length,
          scope: 'worker_config',
          canClientFix: false,
          bodySnippet: boundedSnippet(routeText),
          nextAction: 'Aktivierte Backend-Route, Direkttransport und Default-Modell prüfen.',
        },
      };
    }

    const requestId = args.requestId ?? createRequestId();
    if (!requestId) {
      return {
        ok: false,
        error: 'Sichere Request-ID konnte nicht erzeugt werden.',
        diagnostic: {
          route: SOVEREIGN_LITELLM_CHAT,
          model: selected.modelId,
          messageCount: messages.length,
          scope: 'client_request',
          canClientFix: true,
          nextAction: 'WebView-Crypto-Unterstützung prüfen; keine nicht korrelierbare LLM-Anfrage senden.',
        },
      };
    }

    const routeSelectionMode = !args.preferredModel?.trim()
      || isAbstractSovereignRouteAlias(args.preferredModel)
      ? 'auto'
      : 'pinned';
    const chatResponse = await fetchImpl(SOVEREIGN_LITELLM_CHAT, {
      method: 'POST',
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        requestId,
        outputContractId: SOVEREIGN_CODE_ACTION_CONTRACT_ID,
        routeSelectionMode,
        // Send the immutable route UUID to the backend. `defaultModelId` is
        // provider-facing metadata and can become stale after a verified
        // FreeLLM catalog refresh; the backend resolves the current provider
        // model from the persisted route.
        model: selected.routeId,
        messages,
        max_tokens: 700,
        stream: false,
      }),
      signal,
    });
    const chatText = await chatResponse.text();
    if (!chatResponse.ok) {
      return {
        ok: false,
        error: `Sovereign LLM Intent HTTP ${chatResponse.status}`,
        diagnostic: createDiagnostic({
          route: SOVEREIGN_LITELLM_CHAT,
          model: selected.modelId,
          messageCount: messages.length,
          status: chatResponse.status,
          statusText: chatResponse.statusText,
          body: chatText,
        }),
      };
    }

    const payload = readJsonObject(chatText);
    const content = payload ? readCompletionContent(payload) : undefined;
    if (!payload || !content) {
      return {
        ok: false,
        error: 'Die Sovereign LLM-Direktruntime lieferte keine auswertbare Intent-Antwort.',
        diagnostic: {
          route: SOVEREIGN_LITELLM_CHAT,
          model: selected.modelId,
          messageCount: messages.length,
          status: chatResponse.status,
          statusText: chatResponse.statusText,
          bodySnippet: boundedSnippet(chatText),
          scope: 'worker_runtime',
          canClientFix: false,
          nextAction: 'Direkttransport-Antwortformat prüfen; die Antwort nicht als Aktions-Evidence akzeptieren.',
        },
      };
    }

    const actualModel = readModel(payload, selected.modelId);
    const interpretation = parseIntentEnvelope(
      content,
      actualModel,
      actualModel !== selected.modelId,
    );
    if (!interpretation) {
      return {
        ok: false,
        error: 'Der strukturierte Codeauftragsvertrag wurde verletzt.',
        diagnostic: {
          route: SOVEREIGN_LITELLM_CHAT,
          model: actualModel,
          messageCount: messages.length,
          status: chatResponse.status,
          statusText: chatResponse.statusText,
          scope: 'worker_runtime',
          canClientFix: false,
          nextAction: 'Modellantwort verwerfen und eine knappe konkrete Gegenfrage anzeigen; keine Offline-Deutung starten.',
        },
      };
    }

    return { ok: true, interpretation };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Sovereign LLM-Intent-Anfrage fehlgeschlagen.',
      diagnostic: createDiagnostic({
        route: SOVEREIGN_LITELLM_CHAT,
        model: fallbackModel,
        messageCount: messages.length,
        error,
      }),
    };
  } finally {
    clearTimeout(timeoutId);
  }
}

/** @deprecated Compatibility export for callers not migrated yet. */
export const fetchSovereignLiteLlmInterpretation = fetchSovereignDirectLlmInterpretation;
