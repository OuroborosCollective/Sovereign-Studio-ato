/**
 * DevChat Worker Bridge
 *
 * Typed runtime helpers extracted from the approved DevChat reference.
 * This module owns Cloudflare route constants, real GitHub URL parsing,
 * Worker health diagnostics and the standard hosted LLM bridge request shape.
 * It contains no demo messages and no simulated model responses.
 */

export const SOVEREIGN_WORKER_BASE = 'https://sovereign-llm-proxy.projectouroboroscollective.workers.dev' as const;
export const SOVEREIGN_WORKER_CHAT = `${SOVEREIGN_WORKER_BASE}/v1/chat/completions` as const;
export const SOVEREIGN_WORKER_HEALTH = `${SOVEREIGN_WORKER_BASE}/health` as const;
export const SOVEREIGN_WORKER_KV = `${SOVEREIGN_WORKER_BASE}/kv` as const;
export const SOVEREIGN_SESSION_KEY = 'sovereign-session-v1' as const;
// Verified live against the Worker /v1/models endpoint 2026-07-02:
//   OK:   deepseek-r1, mistral-7b, llama-3.1-8b
//   DEAD: cerebras/gpt-oss-120b (no route), cerebras/zai-glm-4.7 (no route),
//         qwen-14b (no route), gemma-7b (no route), llama-3-8b (deprecated 2026-05-30)
export const DEV_CHAT_WORKER_DEFAULT_MODEL = 'deepseek-r1' as const;
export const DEV_CHAT_WORKER_FALLBACK_MODEL = 'llama-3.1-8b' as const;

// Models that no longer route correctly on the Worker — normalised to default.
const LEGACY_WORKER_MODEL_ALIASES = new Set([
  'cerebras/gpt-oss-120b',
  'cerebras/zai-glm-4.7',
  'llama-3-8b',   // deprecated by Cloudflare 2026-05-30
  'gemma-7b',     // no route as of 2026-07-02
  'qwen-14b',     // no route as of 2026-07-02
]);

export type DevChatWorkerModelTier = 'fast' | 'smart' | 'power';

export interface DevChatWorkerModel {
  readonly id: string;
  readonly label: string;
  readonly tier: DevChatWorkerModelTier;
  readonly thinking: boolean;
}

/**
 * Active models verified against the deployed Worker on 2026-07-02.
 * Keep this list in sync with the Worker's /v1/models response.
 */
export const DEV_CHAT_WORKER_MODELS: readonly DevChatWorkerModel[] = [
  { id: 'deepseek-r1',   label: 'DeepSeek R1',    tier: 'power', thinking: true  },
  { id: 'mistral-7b',    label: 'Mistral 7B',      tier: 'smart', thinking: false },
  { id: 'llama-3.1-8b',  label: 'Llama 3.1 8B',   tier: 'fast',  thinking: false },
];

export function normalizeDevChatWorkerModel(model: string | undefined): string {
  const clean = model?.trim();
  if (!clean) return DEV_CHAT_WORKER_DEFAULT_MODEL;
  if (LEGACY_WORKER_MODEL_ALIASES.has(clean)) return DEV_CHAT_WORKER_DEFAULT_MODEL;
  return clean;
}

export interface DevChatWorkerMessage {
  readonly role: 'system' | 'user' | 'assistant';
  readonly content: string;
}

export interface DevChatWorkerReplyRequest {
  readonly model: string;
  readonly messages: readonly DevChatWorkerMessage[];
  readonly signal?: AbortSignal;
}

export type DevChatWorkerFailureScope =
  | 'client_request'
  | 'worker_config'
  | 'worker_runtime'
  | 'upstream_provider'
  | 'network'
  | 'unknown';

export interface DevChatWorkerDiagnostic {
  /** Concrete runtime route that produced the evidence. Legacy Worker and
   * LiteLLM-backed backend diagnostics share this envelope. */
  readonly route: string;
  readonly model: string;
  readonly messageCount: number;
  readonly status?: number;
  readonly statusText?: string;
  readonly errorType?: string;
  readonly errorCode?: string;
  readonly bodySnippet?: string;
  readonly scope: DevChatWorkerFailureScope;
  readonly canClientFix: boolean;
  readonly nextAction: string;
}

export interface DevChatWorkerHealthResult {
  readonly ok: boolean;
  readonly route: typeof SOVEREIGN_WORKER_HEALTH;
  readonly status?: number;
  readonly error?: string;
  readonly provider?: string;
  readonly gateway?: string;
  readonly model?: string;
  readonly upstreamConfigured?: boolean;
  readonly secretConfigured?: boolean;
  readonly configured?: boolean;
  readonly bodySnippet?: string;
}

export interface DevChatWorkerReplyResult {
  readonly ok: boolean;
  readonly content?: string;
  readonly error?: string;
  readonly route: typeof SOVEREIGN_WORKER_CHAT;
  readonly diagnostic?: DevChatWorkerDiagnostic;
  readonly fallbackUsed?: boolean;
  readonly preferredModel?: string;
  readonly actualModel?: string;
  readonly fallbackReason?: string;
}

export type DevChatWorkerIntentKind =
  | 'free_chat'
  | 'status'
  | 'direct_patch'
  | 'code_execution'
  | 'draft_pr'
  | 'workflow_watch'
  | 'repair_workflow'
  | 'load_repo'
  | 'unknown';

export interface DevChatWorkerInterpretation {
  readonly mode: 'chat' | 'action';
  readonly intent: DevChatWorkerIntentKind;
  readonly assistantText: string;
  readonly actionTitle: string;
  readonly confidence: number;
  readonly language: string;
  readonly model: string;
  readonly fallbackUsed: boolean;
}

export interface DevChatWorkerInterpretationResult {
  readonly ok: boolean;
  readonly interpretation?: DevChatWorkerInterpretation;
  readonly diagnostic?: DevChatWorkerDiagnostic;
  readonly error?: string;
  /** Provider text retained only as a degraded chat fallback when it did not
   *  satisfy the intent schema. It is never accepted as action evidence. */
  readonly rawContent?: string;
}

export interface ParsedDevChatGithubUrl {
  readonly owner: string;
  readonly repo: string;
  readonly branch: string;
  readonly path: string;
  readonly name: string;
  readonly repoUrl: string;
}

export interface DevChatRepoTreeFile {
  readonly path: string;
  readonly type: 'blob' | 'tree';
  readonly size?: number;
  readonly sha?: string;
}

export interface DevChatRepoSnapshot {
  readonly owner: string;
  readonly repo: string;
  readonly branch: string;
  readonly name: string;
  readonly repoUrl: string;
  readonly treeSha?: string;
  readonly fileCount: number;
  readonly files: readonly DevChatRepoTreeFile[];
  readonly filePaths: readonly string[];
  readonly dirs: readonly string[];
  readonly lastFile?: string;
  readonly lastPath?: string;
  readonly truncated?: boolean;
}

export interface DevChatRepoLoadResult {
  readonly ok: boolean;
  readonly snapshot?: DevChatRepoSnapshot;
  readonly error?: string;
}

/**
 * Hard timeout for GitHub repo tree loading. The UI must never stay in
 * "repo läuft" forever when GitHub, DNS, CORS, or the browser network stalls.
 */
export const REPO_TREE_TIMEOUT_MS = 15_000;

const GITHUB_URL_PATTERN = /https?:\/\/github\.com\/([^/\s]+)\/([^/\s#?]+)(?:\/tree\/([^/\s#?]+))?(?:\/([^\s#?]*))?/i;

export function parseDevChatGithubUrl(text: string): ParsedDevChatGithubUrl | null {
  const match = text.match(GITHUB_URL_PATTERN);
  if (!match) return null;
  const owner = match[1];
  const repo = match[2].replace(/\.git$/i, '');
  const branch = match[3] || 'main';
  const path = match[4] || '';

  return {
    owner,
    repo,
    branch,
    path,
    name: repo,
    repoUrl: `https://github.com/${owner}/${repo}`,
  };
}

export function devChatGithubUrlToRepoRequest(text: string): { repoUrl: string; repoBranch: string } | null {
  const parsed = parseDevChatGithubUrl(text);
  if (!parsed) return null;
  return { repoUrl: parsed.repoUrl, repoBranch: parsed.branch };
}

export function summarizeDevChatRepoSnapshot(snapshot: DevChatRepoSnapshot): string {
  const truncated = snapshot.truncated ? ' · GitHub API truncated' : '';
  return `${snapshot.owner}/${snapshot.repo} geladen · ${snapshot.branch} · ${snapshot.fileCount} files${truncated}`;
}

function lastPreferredSourcePath(paths: string[]): string | undefined {
  for (let index = paths.length - 1; index >= 0; index -= 1) {
    if (paths[index].startsWith('src/')) return paths[index];
  }
  return paths.length ? paths[paths.length - 1] : undefined;
}

export async function fetchDevChatRepoTree(parsed: ParsedDevChatGithubUrl): Promise<DevChatRepoLoadResult> {
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), REPO_TREE_TIMEOUT_MS);

  try {
    const response = await fetch(
      `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/trees/${encodeURIComponent(parsed.branch)}?recursive=1`,
      {
        headers: { Accept: 'application/vnd.github+json' },
        signal: timeoutController.signal,
      },
    );
    clearTimeout(timeoutId);

    if (!response.ok) return { ok: false, error: `GitHub API ${response.status}` };

    const data = await response.json();
    const tree = Array.isArray(data.tree) ? data.tree : [];
    const files = tree
      .filter((entry: { type?: string }) => entry.type === 'blob' || entry.type === 'tree')
      .slice(0, 500)
      .map((entry: { path: string; type: 'blob' | 'tree'; size?: number; sha?: string }) => ({
        path: entry.path,
        type: entry.type,
        size: entry.size,
        sha: typeof entry.sha === 'string' ? entry.sha : undefined,
      }));

    const blobPaths = files.filter((file: DevChatRepoTreeFile) => file.type === 'blob').map((file: DevChatRepoTreeFile) => file.path);
    const topLevelDirs = blobPaths.map((path: string) => path.split('/')[0]).filter((dir: string): dir is string => Boolean(dir));
    const dirs = Array.from(new Set<string>(topLevelDirs)).slice(0, 12);
    const lastPath = lastPreferredSourcePath(blobPaths);
    const slash = lastPath ? lastPath.lastIndexOf('/') : -1;

    return {
      ok: true,
      snapshot: {
        owner: parsed.owner,
        repo: parsed.repo,
        branch: parsed.branch,
        name: parsed.name,
        repoUrl: parsed.repoUrl,
        treeSha: typeof data.sha === 'string' ? data.sha : undefined,
        fileCount: files.length,
        files,
        filePaths: blobPaths,
        dirs,
        lastFile: lastPath ? lastPath.slice(slash + 1) : undefined,
        lastPath: lastPath && slash >= 0 ? lastPath.slice(0, slash + 1) : undefined,
        truncated: Boolean(data.truncated),
      },
    };
  } catch (error) {
    clearTimeout(timeoutId);
    if (isWorkerTimeoutError(error)) {
      return { ok: false, error: 'GitHub Repo Timeout: keine Antwort von der GitHub Tree API.' };
    }
    return { ok: false, error: error instanceof Error ? error.message : 'GitHub repo load failed' };
  }
}

function readWorkerContent(payload: unknown): string | undefined {
  if (!payload || typeof payload !== 'object') return undefined;
  const root = payload as Record<string, unknown>;

  const direct = root.content ?? root.reply ?? root.text ?? root.response ?? root.output_text;
  if (typeof direct === 'string' && direct.trim()) return direct.trim();

  const message = root.message;
  if (message && typeof message === 'object') {
    const content = (message as Record<string, unknown>).content;
    if (typeof content === 'string' && content.trim()) return content.trim();
  }

  const choices = root.choices;
  if (Array.isArray(choices)) {
    for (const choice of choices) {
      if (!choice || typeof choice !== 'object') continue;
      const choiceRecord = choice as Record<string, unknown>;
      const choiceText = choiceRecord.text;
      if (typeof choiceText === 'string' && choiceText.trim()) return choiceText.trim();

      const choiceMessage = choiceRecord.message;
      if (!choiceMessage || typeof choiceMessage !== 'object') continue;
      const content = (choiceMessage as Record<string, unknown>).content;
      if (typeof content === 'string' && content.trim()) return content.trim();
    }
  }

  return undefined;
}

function readOptionalStringField(value: unknown, key: string): string | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const field = (value as Record<string, unknown>)[key];
  return typeof field === 'string' && field.trim() ? field.trim() : undefined;
}

function bodySnippet(text: string): string | undefined {
  const clean = text.replace(/\s+/g, ' ').trim();
  return clean ? clean.slice(0, 420) : undefined;
}

function extractErrorPayload(text: string): { message?: string; type?: string; code?: string; snippet?: string } {
  const snippet = bodySnippet(text);
  if (!text.trim()) return { snippet };
  try {
    const parsed = JSON.parse(text) as unknown;
    if (!parsed || typeof parsed !== 'object') return { snippet };
    const root = parsed as Record<string, unknown>;
    const error = root.error;
    if (typeof error === 'string') return { message: error, snippet };
    if (error && typeof error === 'object') {
      const record = error as Record<string, unknown>;
      return {
        message: typeof record.message === 'string' ? record.message : undefined,
        type: typeof record.type === 'string' ? record.type : undefined,
        code: typeof record.code === 'string' ? record.code : undefined,
        snippet,
      };
    }
    return {
      message: typeof root.message === 'string' ? root.message : undefined,
      type: typeof root.type === 'string' ? root.type : undefined,
      code: typeof root.code === 'string' ? root.code : undefined,
      snippet,
    };
  } catch {
    return { snippet };
  }
}

function createWorkerHttpDiagnostic(args: {
  readonly response: Response;
  readonly text: string;
  readonly model: string;
  readonly messageCount: number;
}): { readonly diagnostic: DevChatWorkerDiagnostic; readonly errorMessage: string } {
  const payload = extractErrorPayload(args.text);
  const classification = classifyWorkerFailure({
    status: args.response.status,
    errorType: payload.type,
    errorCode: payload.code,
    bodySnippet: payload.snippet,
  });
  const diagnostic: DevChatWorkerDiagnostic = {
    route: SOVEREIGN_WORKER_CHAT,
    model: args.model,
    messageCount: args.messageCount,
    status: args.response.status,
    statusText: args.response.statusText,
    errorType: payload.type,
    errorCode: payload.code,
    bodySnippet: payload.snippet,
    ...classification,
  };
  return { diagnostic, errorMessage: payload.message || `Worker Chat HTTP ${args.response.status}` };
}

function createWorkerRuntimeError(args: {
  readonly message: string;
  readonly diagnostic: DevChatWorkerDiagnostic;
}): Error & { readonly diagnostic: DevChatWorkerDiagnostic; readonly status?: number; readonly statusText?: string; readonly bodySnippet?: string } {
  const error = new Error(args.message) as Error & { diagnostic: DevChatWorkerDiagnostic; status?: number; statusText?: string; bodySnippet?: string };
  error.diagnostic = args.diagnostic;
  error.status = args.diagnostic.status;
  error.statusText = args.diagnostic.statusText;
  error.bodySnippet = args.diagnostic.bodySnippet;
  return error;
}

function readWorkerContentFromText(text: string): string | undefined {
  if (!text.trim()) return undefined;
  try {
    return readWorkerContent(JSON.parse(text));
  } catch {
    return readWorkerContent({ response: text });
  }
}

function classifyWorkerFailure(args: {
  readonly status?: number;
  readonly errorType?: string;
  readonly errorCode?: string;
  readonly bodySnippet?: string;
}): Pick<DevChatWorkerDiagnostic, 'scope' | 'canClientFix' | 'nextAction'> {
  const text = `${args.errorType ?? ''} ${args.errorCode ?? ''} ${args.bodySnippet ?? ''}`.toLowerCase();
  if (!args.status) {
    return { scope: 'network', canClientFix: false, nextAction: 'Netzwerk, CORS oder Worker-Erreichbarkeit prüfen.' };
  }
  if (args.status === 400) {
    return { scope: 'client_request', canClientFix: true, nextAction: 'Request-Payload, Modellname und Nachrichtenformat im App-Code prüfen.' };
  }
  if (args.status === 401 || args.status === 403) {
    return { scope: 'worker_config', canClientFix: false, nextAction: 'Worker/API-Key-Konfiguration oder Cloudflare Secret prüfen.' };
  }
  if (args.status === 404 || args.status === 405) {
    return { scope: 'client_request', canClientFix: true, nextAction: 'Worker-Route und HTTP-Methode im App-Code prüfen.' };
  }
  if (args.status === 429) {
    return { scope: 'upstream_provider', canClientFix: false, nextAction: 'Rate Limit abwarten oder Cloudflare Gateway-Limits prüfen.' };
  }
  if (args.status === 502 || args.status === 503 || args.status === 504) {
    return { scope: 'upstream_provider', canClientFix: false, nextAction: 'Cloudflare AI Gateway/Upstream-Provider prüfen.' };
  }
  if (args.status >= 500) {
    const looksLikeConfig = text.includes('secret') || text.includes('token') || text.includes('not configured') || text.includes('unauthorized');
    return looksLikeConfig
      ? { scope: 'worker_config', canClientFix: false, nextAction: 'Cloudflare Worker Secrets und AI-Gateway-Konfiguration prüfen.' }
      : { scope: 'worker_runtime', canClientFix: false, nextAction: 'Cloudflare Worker Logs und Deploy-Bridge prüfen; App darf nicht blind erneut senden.' };
  }
  return { scope: 'unknown', canClientFix: false, nextAction: 'Worker-Antwort im Runtime-Diagnosepfad prüfen.' };
}

export function explainDevChatWorkerDiagnostic(diagnostic: DevChatWorkerDiagnostic): string {
  const status = diagnostic.status ? `HTTP ${diagnostic.status}` : 'Netzwerkfehler';
  const origin = diagnostic.canClientFix ? 'wahrscheinlich im App-Request korrigierbar' : 'nicht sicher im App-Code behebbar';
  return [
    `Cloudflare Worker blockiert: ${status}.`,
    `Route: ${diagnostic.route}.`,
    `Modell: ${diagnostic.model} · Nachrichten: ${diagnostic.messageCount}.`,
    `Einschätzung: ${diagnostic.scope} · ${origin}.`,
    `Nächste erlaubte Aktion: ${diagnostic.nextAction}`,
    diagnostic.bodySnippet ? `Antwortauszug: ${diagnostic.bodySnippet}` : '',
  ].filter(Boolean).join('\n');
}

export async function fetchDevChatWorkerHealth(signal?: AbortSignal): Promise<DevChatWorkerHealthResult> {
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), WORKER_REPLY_TIMEOUT_MS);
  const combinedSignal = signal
    ? AbortSignal.any([signal, timeoutController.signal])
    : timeoutController.signal;

  try {
    const response = await fetch(SOVEREIGN_WORKER_HEALTH, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: combinedSignal,
    });
    clearTimeout(timeoutId);
    const text = await response.text();
    const snippet = bodySnippet(text);
    let payload: Record<string, unknown> = {};
    try {
      payload = text ? JSON.parse(text) as Record<string, unknown> : {};
    } catch {
      payload = {};
    }

    const classification = classifyWorkerFailure({
      status: response.status,
      bodySnippet: snippet,
    });

    return {
      ok: response.ok,
      route: SOVEREIGN_WORKER_HEALTH,
      status: response.status,
      error: response.ok ? undefined : (typeof payload.error === 'string' ? payload.error : response.statusText || `HTTP ${response.status} (${classification.scope})`),
      provider: typeof payload.provider === 'string' ? payload.provider : undefined,
      gateway: typeof payload.gateway === 'string' ? payload.gateway : undefined,
      model: typeof payload.model === 'string' ? payload.model : undefined,
      upstreamConfigured: typeof payload.upstreamConfigured === 'boolean' ? payload.upstreamConfigured : undefined,
      secretConfigured: typeof payload.secretConfigured === 'boolean' ? payload.secretConfigured : undefined,
      configured: typeof payload.configured === 'boolean' ? payload.configured : undefined,
      bodySnippet: snippet,
    };
  } catch (error) {
    clearTimeout(timeoutId);
    if (isWorkerTimeoutError(error)) {
      return {
        ok: false,
        route: SOVEREIGN_WORKER_HEALTH,
        status: 408,
        error: 'Worker Health Timeout: keine Antwort vom Worker (network).',
      };
    }
    return {
      ok: false,
      route: SOVEREIGN_WORKER_HEALTH,
      error: `${error instanceof Error ? error.message : 'Worker Health Anfrage fehlgeschlagen'} (network)`,
    };
  }
}

export async function fetchDevChatWorkerReply(
  request: DevChatWorkerReplyRequest,
  options: { maxRetries?: number; retryDelayMs?: number } = {},
): Promise<DevChatWorkerReplyResult> {
  const { maxRetries = 1, retryDelayMs = 1000 } = options;
  const messages = request.messages
    .map((message) => ({ role: message.role, content: message.content.trim() }))
    .filter((message) => message.content.length > 0);
  const model = normalizeDevChatWorkerModel(request.model);

  if (messages.length === 0) {
    const diagnostic: DevChatWorkerDiagnostic = {
      route: SOVEREIGN_WORKER_CHAT,
      model,
      messageCount: 0,
      scope: 'client_request',
      canClientFix: true,
      nextAction: 'Vor dem Senden mindestens eine echte Nachricht erzeugen.',
    };
    return { ok: false, error: 'Worker Chat blockiert: keine gültige Nachricht.', route: SOVEREIGN_WORKER_CHAT, diagnostic };
  }

  let lastError: any = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (attempt > 0) {
      await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
    }

    const timeoutController = new AbortController();
    const timeoutId = setTimeout(() => timeoutController.abort(), WORKER_REPLY_TIMEOUT_MS);
    const combinedSignal = request.signal
      ? AbortSignal.any([request.signal, timeoutController.signal])
      : timeoutController.signal;

    try {
      const response = await fetch(SOVEREIGN_WORKER_CHAT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-Sovereign-Client': 'android-webview',
        },
        body: JSON.stringify({
          model,
          messages,
          temperature: 0.2,
          max_tokens: 4096,
          reasoning_format: 'parsed',
          stream: false,
        }),
        signal: combinedSignal,
      });
      clearTimeout(timeoutId);

      const text = await response.text();
      if (!response.ok) {
        const payload = extractErrorPayload(text);
        const classification = classifyWorkerFailure({
          status: response.status,
          errorType: payload.type,
          errorCode: payload.code,
          bodySnippet: payload.snippet,
        });

        // Only retry on transient upstream or network issues
        const isTransient = response.status === 429 || response.status >= 500;
        if (isTransient && attempt < maxRetries) {
          lastError = { status: response.status, text };
          continue;
        }

        const diagnostic: DevChatWorkerDiagnostic = {
          route: SOVEREIGN_WORKER_CHAT,
          model,
          messageCount: messages.length,
          status: response.status,
          statusText: response.statusText,
          errorType: payload.type,
          errorCode: payload.code,
          bodySnippet: payload.snippet,
          ...classification,
        };
        return {
          ok: false,
          error: payload.message || `Worker Chat HTTP ${response.status}`,
          route: SOVEREIGN_WORKER_CHAT,
          diagnostic,
        };
      }

      let payload: unknown = {};
      try {
        payload = text ? JSON.parse(text) : {};
      } catch {
        payload = { response: text };
      }

      const content = readWorkerContent(payload);
      if (!content) {
        const diagnostic: DevChatWorkerDiagnostic = {
          route: SOVEREIGN_WORKER_CHAT,
          model,
          messageCount: messages.length,
          status: response.status,
          statusText: response.statusText,
          bodySnippet: bodySnippet(text),
          scope: 'worker_runtime',
          canClientFix: false,
          nextAction: 'Worker-Antwortformat im Bridge-Adapter prüfen.',
        };
        return { ok: false, error: 'Worker Chat lieferte keine auswertbare Antwort.', route: SOVEREIGN_WORKER_CHAT, diagnostic };
      }

      const actualModel = readOptionalStringField(payload, 'model') || model;
      return { 
        ok: true, 
        content, 
        route: SOVEREIGN_WORKER_CHAT,
        fallbackUsed: actualModel !== model,
        preferredModel: model,
        actualModel,
        fallbackReason: readOptionalStringField(payload, 'fallback_reason'),
      };
    } catch (error) {
      clearTimeout(timeoutId);
      
      // Retry on network/timeout errors
      if (attempt < maxRetries) {
        lastError = error;
        continue;
      }

      if (isWorkerTimeoutError(error)) {
        const diagnostic = createWorkerTimeoutDiagnostic({ model, messageCount: messages.length, error });
        return {
          ok: false,
          error: 'Worker Chat Timeout: keine Antwort vom Worker.',
          route: SOVEREIGN_WORKER_CHAT,
          diagnostic,
        };
      }
      const diagnostic: DevChatWorkerDiagnostic = {
        route: SOVEREIGN_WORKER_CHAT,
        model,
        messageCount: messages.length,
        scope: 'network',
        canClientFix: false,
        nextAction: 'Netzwerk, CORS oder Worker-Erreichbarkeit prüfen.',
        bodySnippet: error instanceof Error ? error.message : undefined,
      };
      return {
        ok: false,
        error: error instanceof Error ? error.message : 'Worker Chat Anfrage fehlgeschlagen.',
        route: SOVEREIGN_WORKER_CHAT,
        diagnostic,
      };
    }
  }

  // Should not be reachable due to returns above, but for TS:
  return { ok: false, error: 'Retry-Limit erreicht.', route: SOVEREIGN_WORKER_CHAT };
}

function extractSseChatText(content: string): string {
  if (!content.includes('data:')) return content.trim();
  let combined = '';
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('data:')) continue;
    const data = trimmed.slice(5).trim();
    if (!data || data === '[DONE]') continue;
    try {
      const payload = JSON.parse(data) as Record<string, unknown>;
      const choices = payload.choices;
      if (!Array.isArray(choices) || choices.length === 0) continue;
      const choice = choices[0] as Record<string, unknown>;
      const delta = choice.delta;
      if (delta && typeof delta === 'object') {
        const chunk = (delta as Record<string, unknown>).content;
        if (typeof chunk === 'string') combined += chunk;
      }
      const message = choice.message;
      if (message && typeof message === 'object') {
        const text = (message as Record<string, unknown>).content;
        if (typeof text === 'string') combined += text;
      }
    } catch {
      // Malformed SSE fragments are ignored; they never become action evidence.
    }
  }
  return combined.trim() || content.trim();
}

/** Parse and validate the model-produced intent envelope. */
function parseWorkerInterpretationContent(
  content: string,
  model: string,
  fallbackUsed: boolean,
): DevChatWorkerInterpretation | null {
  const clean = content
    .trim()
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/i, '');

  let payload: unknown;
  try {
    payload = JSON.parse(clean);
  } catch {
    return null;
  }
  if (!payload || typeof payload !== 'object') return null;
  const record = payload as Record<string, unknown>;
  const mode = record.mode;
  const intent = record.intent;
  const allowedIntents: readonly DevChatWorkerIntentKind[] = [
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
  if (mode !== 'chat' && mode !== 'action') return null;
  if (typeof intent !== 'string' || !allowedIntents.includes(intent as DevChatWorkerIntentKind)) return null;

  const assistantText = typeof record.assistant_text === 'string'
    ? record.assistant_text.trim()
    : '';
  const actionTitle = typeof record.action_title === 'string'
    ? record.action_title.trim()
    : '';
  const confidenceValue = typeof record.confidence === 'number'
    ? record.confidence
    : Number(record.confidence);
  const confidence = Number.isFinite(confidenceValue)
    ? Math.max(0, Math.min(1, confidenceValue))
    : 0;
  const language = typeof record.language === 'string' && record.language.trim()
    ? record.language.trim()
    : 'und';

  if (mode === 'chat' && !assistantText) return null;
  if (mode === 'action' && (!actionTitle || confidence < 0.5)) return null;

  return {
    mode,
    intent: intent as DevChatWorkerIntentKind,
    assistantText,
    actionTitle,
    confidence,
    language,
    model,
    fallbackUsed,
  };
}

/**
 * Uses the online LLM as the natural-language interpreter. The result is only
 * intent evidence: the application still owns authorization, tool execution,
 * repository scope and success truth. Local keyword classifiers are fallback
 * paths for offline/degraded operation, never the primary online language path.
 */
export async function fetchDevChatWorkerInterpretation(args: {
  readonly model: string;
  readonly text: string;
  readonly repoContext?: string;
  readonly runtimeContext?: string;
  readonly memoryContext?: string;
  readonly recentMessages?: readonly DevChatWorkerMessage[];
}): Promise<DevChatWorkerInterpretationResult> {
  const systemPrompt = [
    'Du bist der Natural-Language-Interpreter von Sovereign Studio.',
    'Verstehe Sprache, Absicht, Kontext und implizite Verweise des Users.',
    'Du führst selbst keine Aktion aus und behauptest niemals Erfolg.',
    'Die Runtime entscheidet nach deiner Deutung separat über Repo-, GitHub-, Workspace- und Draft-PR-Gates.',
    'Antworte ausschließlich als einzelnes JSON-Objekt ohne Markdown.',
    'Schema:',
    '{"mode":"chat|action","intent":"free_chat|status|direct_patch|code_execution|draft_pr|workflow_watch|repair_workflow|load_repo|unknown","assistant_text":"Antwort in Sprache des Users oder kurze Verständnisbestätigung","action_title":"konkreter Aktionsauftrag oder leer","confidence":0.0,"language":"de|en|..."}',
    'Nutze mode=action nur wenn der User tatsächlich etwas verändern, ausführen, reparieren, erstellen, prüfen oder als Draft PR vorbereiten lassen will.',
    'Nutze mode=chat für Fragen, Erklärungen, Diskussionen und Beratung.',
    'Bei Unsicherheit: mode=chat, intent=unknown, keine erfundene Aktion.',
    args.repoContext ? `Runtime-Repo-Kontext: ${args.repoContext}` : 'Runtime-Repo-Kontext: nicht geladen.',
    args.runtimeContext ? `Belegte Runtime-Fakten (nur Fakten, keine Sprachdeutung):\n${args.runtimeContext}` : '',
    args.memoryContext ? `Evidence-geprüfter Memory-Kontext:\n${args.memoryContext}` : '',
  ].filter(Boolean).join('\n');

  const recentMessages = (args.recentMessages ?? [])
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .slice(-6);
  const result = await fetchDevChatWorkerReply({
    model: args.model,
    messages: [
      { role: 'system', content: systemPrompt },
      ...recentMessages,
      { role: 'user', content: args.text },
    ],
  }, { maxRetries: 0 });

  if (!result.ok || !result.content) {
    return {
      ok: false,
      error: result.error || 'Online-Intent-Deutung fehlgeschlagen.',
      diagnostic: result.diagnostic,
    };
  }

  const interpretation = parseWorkerInterpretationContent(
    result.content,
    result.actualModel || args.model,
    Boolean(result.fallbackUsed),
  );
  if (!interpretation) {
    return {
      ok: false,
      error: 'Online-Intent-Deutung lieferte kein gültiges Schema.',
      rawContent: extractSseChatText(result.content),
      diagnostic: {
        route: SOVEREIGN_WORKER_CHAT,
        model: result.actualModel || args.model,
        messageCount: recentMessages.length + 2,
        scope: 'worker_runtime',
        canClientFix: false,
        bodySnippet: bodySnippet(result.content),
        nextAction: 'Online-Antwort als ungültige Intent-Evidence verwerfen und lokalen Offline-Fallback verwenden.',
      },
    };
  }

  return { ok: true, interpretation };
}

/**
 * Hard timeout for all Worker calls — streaming, blocking fetch, and health check.
 * After 30 s the request is aborted and a typed timeout diagnostic is returned so
 * BuilderContainer can route to the workerBlocker path instead of hanging forever.
 */
export const WORKER_REPLY_TIMEOUT_MS = 30_000;

/**
 * Returns true for any error that indicates a request was aborted due to a timeout
 * or an AbortSignal firing.  Handles AbortError, DOMException, and browsers that
 * surface timeout-phrased messages.
 */
export function isWorkerTimeoutError(error: unknown): boolean {
  if (!error) return false;
  if (error instanceof DOMException && (error.name === 'AbortError' || error.code === 20)) return true;
  if (error instanceof Error) {
    const name = error.name.toLowerCase();
    const msg  = error.message.toLowerCase();
    if (name === 'aborterror') return true;
    if (msg.includes('aborted') || msg.includes('timeout') || msg.includes('timed out')) return true;
    // AbortSignal fires: "signal is aborted without reason"
    if (msg.includes('signal')) return true;
  }
  return false;
}

/**
 * Builds a canonical timeout diagnostic with scope='worker_runtime' and
 * canClientFix=false so the caller never re-tries blindly.
 */
export function createWorkerTimeoutDiagnostic(args: {
  readonly model: string;
  readonly messageCount: number;
  readonly error?: unknown;
}): DevChatWorkerDiagnostic {
  const errorMsg = args.error instanceof Error ? args.error.message : undefined;
  return {
    route: SOVEREIGN_WORKER_CHAT,
    model: args.model,
    messageCount: args.messageCount,
    scope: 'worker_runtime',
    canClientFix: false,
    nextAction: 'Worker-Timeout als Runtime-Blocker behandeln; Worker Health prüfen und nicht blind erneut senden.',
    bodySnippet: errorMsg ? errorMsg.slice(0, 420) : 'Keine Antwort (Timeout).',
  };
}

/**
 * Streaming variant of fetchDevChatWorkerReply.
 * Posts with stream: true and yields SSE delta chunks in real-time.
 * Falls back to the non-streaming route if response.body is unavailable.
 */
// (timeout is shared with all fetch paths — see WORKER_REPLY_TIMEOUT_MS above)

export async function* streamDevChatWorkerReply(
  request: DevChatWorkerReplyRequest,
  onMetadata?: (metadata: { fallbackUsed: boolean; preferredModel: string; actualModel: string; fallbackReason?: string }) => void,
): AsyncGenerator<string> {
  const messages = request.messages
    .map((message) => ({ role: message.role, content: message.content.trim() }))
    .filter((message) => message.content.length > 0);
  const model = normalizeDevChatWorkerModel(request.model);

  if (messages.length === 0) return;

  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), WORKER_REPLY_TIMEOUT_MS);

  const combinedSignal = request.signal
    ? AbortSignal.any([request.signal, timeoutController.signal])
    : timeoutController.signal;

  let response: Response;
  try {
    response = await fetch(SOVEREIGN_WORKER_CHAT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'X-Sovereign-Client': 'android-webview',
      },
      body: JSON.stringify({
        model,
        messages,
        temperature: 0.2,
        max_tokens: 4096,
        reasoning_format: 'parsed',
        stream: true,
      }),
      signal: combinedSignal,
    });
    clearTimeout(timeoutId);
  } catch (err) {
    clearTimeout(timeoutId);
    if (isWorkerTimeoutError(err)) {
      throw createWorkerRuntimeError({
        message: 'Worker Chat Timeout: keine Antwort vom Worker.',
        diagnostic: createWorkerTimeoutDiagnostic({ model, messageCount: messages.length, error: err }),
      });
    }
    throw err;
  }

  if (!response.ok) {
    const text = await response.text();
    const { diagnostic, errorMessage } = createWorkerHttpDiagnostic({
      response,
      text,
      model,
      messageCount: messages.length,
    });
    throw createWorkerRuntimeError({ message: errorMessage, diagnostic });
  }

  const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
  if (!response.body || !contentType.includes('text/event-stream')) {
    const text = await response.text();
    const content = readWorkerContentFromText(text);
    if (content) yield content;
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data: ')) continue;
        const data = trimmed.slice(6).trim();
        if (data === '[DONE]') return;

        try {
          const payload = JSON.parse(data) as Record<string, unknown>;
          
          // Check for model metadata in the first chunk or specific metadata chunks
          const actualModel = readOptionalStringField(payload, 'model');
          if (actualModel && actualModel !== model && onMetadata) {
            onMetadata({
              fallbackUsed: true,
              preferredModel: model,
              actualModel,
              fallbackReason: readOptionalStringField(payload, 'fallback_reason'),
            });
          }

          // OpenAI-compatible SSE format: { choices: [{ delta: { content: "..." } }] }
          const choices = payload.choices;
          if (Array.isArray(choices) && choices.length > 0) {
            const delta = (choices[0] as Record<string, unknown>)?.delta;
            if (delta && typeof delta === 'object') {
              const content = (delta as Record<string, unknown>)?.content;
              if (typeof content === 'string' && content.length > 0) {
                yield content;
              }
            }
          }
        } catch {
          // Skip malformed JSON lines silently
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
