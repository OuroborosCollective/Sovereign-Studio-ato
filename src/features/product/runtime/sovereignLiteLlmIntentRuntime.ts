import type {
  DevChatWorkerDiagnostic,
  DevChatWorkerIntentKind,
  DevChatWorkerInterpretation,
  DevChatWorkerInterpretationResult,
  DevChatWorkerMessage,
} from './devChatWorkerBridge';

const BACKEND_BASE = (
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined)?.trim()
  || 'https://sovereign-backend.arelorian.de'
).replace(/\/$/, '');

export const SOVEREIGN_LITELLM_ROUTES = `${BACKEND_BASE}/api/llm/routes` as const;
export const SOVEREIGN_LITELLM_CHAT = `${BACKEND_BASE}/api/llm/chat` as const;
export const SOVEREIGN_INTENT_TIMEOUT_MS = 30_000;

interface LiteLlmRouteDescriptor {
  readonly id?: unknown;
  readonly defaultModelId?: unknown;
  readonly enabled?: unknown;
}

interface LiteLlmRouteCatalog {
  readonly routes?: unknown;
}

interface SovereignIntentEnvelope {
  readonly mode?: unknown;
  readonly intent?: unknown;
  readonly action_disposition?: unknown;
  readonly assistant_text?: unknown;
  readonly action_title?: unknown;
  readonly is_startup?: unknown;
  readonly confidence?: unknown;
  readonly language?: unknown;
}

export interface SovereignLiteLlmIntentRequest {
  readonly preferredModel?: string;
  readonly text: string;
  readonly repoContext?: string;
  readonly runtimeContext?: string;
  readonly recentMessages?: readonly DevChatWorkerMessage[];
  readonly signal?: AbortSignal;
  readonly fetchImpl?: typeof fetch;
  readonly requestId?: string;
}

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
  if (!payload) return null;

  const mode = payload.mode;
  const intent = payload.intent;
  if (mode !== 'chat' && mode !== 'action') return null;
  if (typeof intent !== 'string' || !ALLOWED_INTENTS.includes(intent as DevChatWorkerIntentKind)) {
    return null;
  }

  const actionDisposition = payload.action_disposition === 'execute'
    ? 'execute'
    : 'review';
  const assistantText = typeof payload.assistant_text === 'string'
    ? payload.assistant_text.trim()
    : '';
  const actionTitle = typeof payload.action_title === 'string'
    ? payload.action_title.trim()
    : '';
  const isStartup = payload.is_startup === true;
  const confidenceValue = typeof payload.confidence === 'number'
    ? payload.confidence
    : Number(payload.confidence);
  const confidence = Number.isFinite(confidenceValue)
    ? Math.max(0, Math.min(1, confidenceValue))
    : 0;
  const language = typeof payload.language === 'string' && payload.language.trim()
    ? payload.language.trim()
    : 'und';

  if (mode === 'chat' && !assistantText) return null;
  if (mode === 'action' && (!actionTitle || confidence < 0.5)) return null;

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
  if (status === 401 || status === 403) {
    return {
      route: args.route,
      model: args.model,
      messageCount: args.messageCount,
      status,
      statusText: args.statusText,
      bodySnippet: boundedSnippet(body),
      scope: 'worker_config',
      canClientFix: false,
      nextAction: 'Backend-Session und Authentifizierung prüfen; keine Provider-Secrets im Client verwenden.',
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
      nextAction: 'OpenRouter-/FreeLLM-Route und Rate-Limit prüfen; lokal nur den Offline-Fallback verwenden.',
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
    nextAction: 'Backend-Erreichbarkeit, CORS oder Netzwerk prüfen; lokal nur den Offline-Fallback verwenden.',
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

function chooseRoute(
  payload: LiteLlmRouteCatalog,
  preferredModel: string | undefined,
): { readonly routeId: string; readonly modelId: string } | null {
  if (!Array.isArray(payload.routes)) return null;
  const enabled = payload.routes.flatMap((candidate): Array<{ routeId: string; modelId: string }> => {
    if (!candidate || typeof candidate !== 'object') return [];
    const route = candidate as LiteLlmRouteDescriptor;
    if (route.enabled !== true) return [];
    const routeId = typeof route.id === 'string' ? route.id.trim() : '';
    const modelId = typeof route.defaultModelId === 'string' ? route.defaultModelId.trim() : '';
    return routeId && modelId ? [{ routeId, modelId }] : [];
  });
  if (enabled.length === 0) return null;
  const cleanPreferred = preferredModel?.trim();
  return enabled.find((route) =>
    cleanPreferred && (route.routeId === cleanPreferred || route.modelId === cleanPreferred)
  ) ?? enabled[0];
}

function buildMessages(args: SovereignLiteLlmIntentRequest): readonly DevChatWorkerMessage[] {
  const systemPrompt = [
    'Du bist ausschließlich der Natural-Language-Interpreter von Sovereign Studio.',
    'Verstehe Sprache, Absicht, Kontext und implizite Verweise des Users.',
    'Du führst selbst keine Aktion aus und behauptest niemals Erfolg.',
    'Die Runtime entscheidet separat über Repo-, GitHub-, Workspace-, Tool-, Test- und Draft-PR-Gates.',
    'Antworte ausschließlich als einzelnes JSON-Objekt ohne Markdown.',
    'Schema:',
    '{"mode":"chat|action","intent":"free_chat|status|direct_patch|code_execution|draft_pr|workflow_watch|repair_workflow|load_repo|unknown","action_disposition":"review|execute","assistant_text":"Antwort in Sprache des Users oder kurze Verständnisbestätigung","action_title":"konkreter Aktionsauftrag oder leer","is_startup":false,"confidence":0.0,"language":"de|en|..."}',
    'Nutze mode=action nur, wenn der User tatsächlich etwas verändern, ausführen, reparieren, erstellen, prüfen oder als Draft PR vorbereiten lassen will.',
    'Nutze action_disposition=execute nur bei einem ausdrücklichen sofortigen Ausführungsauftrag. Nutze review, wenn der erkannte Änderungsauftrag zuerst als Integrationsentwurf bestätigt werden soll.',
    'Nutze mode=chat für Fragen, Erklärungen, Diskussionen und Beratung.',
    'Bei intent=status setze is_startup=true nur wenn gefragt wird, ob eine Ausführung begonnen hat oder aktuell läuft; für fertig/abgeschlossen/Fortschritt bleibt is_startup=false.',
    'Bei Unsicherheit: mode=chat, intent=unknown, is_startup=false, keine erfundene Aktion.',
    'Bewerte die Gesamtbedeutung, nicht einzelne Schlüsselwörter.',
    args.repoContext ? `Runtime-Repo-Kontext: ${args.repoContext}` : 'Runtime-Repo-Kontext: nicht geladen.',
    args.runtimeContext ? `Belegte Runtime-Fakten (nur Fakten, keine Sprachdeutung):\n${args.runtimeContext}` : 'Belegte Runtime-Fakten (nur Fakten, keine Sprachdeutung): keine zusätzlichen Fakten.',
  ].join('\n');
  const recentMessages = (args.recentMessages ?? [])
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .slice(-6);
  return [
    { role: 'system', content: systemPrompt },
    ...recentMessages,
    { role: 'user', content: args.text },
  ];
}

export async function fetchSovereignLiteLlmInterpretation(
  args: SovereignLiteLlmIntentRequest,
): Promise<DevChatWorkerInterpretationResult> {
  const fetchImpl = args.fetchImpl ?? globalThis.fetch;
  const messages = buildMessages(args);
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), SOVEREIGN_INTENT_TIMEOUT_MS);
  const signal = args.signal
    ? AbortSignal.any([args.signal, timeoutController.signal])
    : timeoutController.signal;
  const fallbackModel = args.preferredModel?.trim() || 'route-catalog';

  try {
    const routeResponse = await fetchImpl(SOVEREIGN_LITELLM_ROUTES, {
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

    const routePayload = readJsonObject(routeText) as LiteLlmRouteCatalog | null;
    const selected = routePayload ? chooseRoute(routePayload, args.preferredModel) : null;
    if (!selected) {
      return {
        ok: false,
        error: 'Keine aktivierte OpenRouter- oder FreeLLM-Route mit Default-Modell gefunden.',
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

    const chatResponse = await fetchImpl(SOVEREIGN_LITELLM_CHAT, {
      method: 'POST',
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        requestId,
        model: selected.modelId,
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
      selected.modelId !== (args.preferredModel?.trim() || selected.modelId),
    );
    if (!interpretation) {
      return {
        ok: false,
        error: 'Die Sovereign LLM-Intent-Antwort verletzte das erlaubte Schema.',
        rawContent: content,
        diagnostic: {
          route: SOVEREIGN_LITELLM_CHAT,
          model: actualModel,
          messageCount: messages.length,
          status: chatResponse.status,
          statusText: chatResponse.statusText,
          bodySnippet: boundedSnippet(content),
          scope: 'worker_runtime',
          canClientFix: false,
          nextAction: 'Ungültige Intent-Evidence verwerfen und ausschließlich den Offline-Fallback verwenden.',
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
