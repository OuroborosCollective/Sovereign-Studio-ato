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
export const DEV_CHAT_WORKER_DEFAULT_MODEL = 'cerebras/gpt-oss-120b' as const;
export const DEV_CHAT_WORKER_FALLBACK_MODEL = 'cerebras/zai-glm-4.7' as const;

const LEGACY_WORKER_MODEL_ALIASES = new Set([
  'llama-3-8b',
  'llama-3.1-8b',
  'mistral-7b',
  'gemma-7b',
  'qwen-14b',
  'deepseek-r1',
]);

export type DevChatWorkerModelTier = 'fast' | 'smart' | 'power';

export interface DevChatWorkerModel {
  readonly id: string;
  readonly label: string;
  readonly tier: DevChatWorkerModelTier;
  readonly thinking: boolean;
}

/**
 * The deployed primary bridge uses the Cloudflare AI Gateway route configured in
 * .github/workflows/deploy-primary-llm-bridge.yml. Keep this model aligned with
 * that workflow; legacy friendly aliases are normalized in the hosted bridge.
 */
export const DEV_CHAT_WORKER_MODELS: readonly DevChatWorkerModel[] = [
  { id: DEV_CHAT_WORKER_DEFAULT_MODEL, label: 'Cerebras GPT OSS 120B', tier: 'power', thinking: true },
  { id: DEV_CHAT_WORKER_FALLBACK_MODEL, label: 'Cerebras ZAI GLM 4.7', tier: 'smart', thinking: true },
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
  readonly route: typeof SOVEREIGN_WORKER_CHAT;
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
}

export interface DevChatRepoSnapshot {
  readonly owner: string;
  readonly repo: string;
  readonly branch: string;
  readonly name: string;
  readonly repoUrl: string;
  readonly fileCount: number;
  readonly files: readonly DevChatRepoTreeFile[];
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
  try {
    const response = await fetch(
      `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/trees/${encodeURIComponent(parsed.branch)}?recursive=1`,
      { headers: { Accept: 'application/vnd.github+json' } },
    );

    if (!response.ok) return { ok: false, error: `GitHub API ${response.status}` };

    const data = await response.json();
    const tree = Array.isArray(data.tree) ? data.tree : [];
    const files = tree
      .filter((entry: { type?: string }) => entry.type === 'blob' || entry.type === 'tree')
      .slice(0, 500)
      .map((entry: { path: string; type: 'blob' | 'tree'; size?: number }) => ({
        path: entry.path,
        type: entry.type,
        size: entry.size,
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
        fileCount: files.length,
        files,
        dirs,
        lastFile: lastPath ? lastPath.slice(slash + 1) : undefined,
        lastPath: lastPath && slash >= 0 ? lastPath.slice(0, slash + 1) : undefined,
        truncated: Boolean(data.truncated),
      },
    };
  } catch (error) {
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
  try {
    const response = await fetch(SOVEREIGN_WORKER_HEALTH, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal,
    });
    const text = await response.text();
    const snippet = bodySnippet(text);
    let payload: Record<string, unknown> = {};
    try {
      payload = text ? JSON.parse(text) as Record<string, unknown> : {};
    } catch {
      payload = {};
    }

    return {
      ok: response.ok,
      route: SOVEREIGN_WORKER_HEALTH,
      status: response.status,
      error: response.ok ? undefined : (typeof payload.error === 'string' ? payload.error : response.statusText || `HTTP ${response.status}`),
      provider: typeof payload.provider === 'string' ? payload.provider : undefined,
      gateway: typeof payload.gateway === 'string' ? payload.gateway : undefined,
      model: typeof payload.model === 'string' ? payload.model : undefined,
      upstreamConfigured: typeof payload.upstreamConfigured === 'boolean' ? payload.upstreamConfigured : undefined,
      secretConfigured: typeof payload.secretConfigured === 'boolean' ? payload.secretConfigured : undefined,
      configured: typeof payload.configured === 'boolean' ? payload.configured : undefined,
      bodySnippet: snippet,
    };
  } catch (error) {
    return {
      ok: false,
      route: SOVEREIGN_WORKER_HEALTH,
      error: error instanceof Error ? error.message : 'Worker Health Anfrage fehlgeschlagen.',
    };
  }
}

export async function fetchDevChatWorkerReply(request: DevChatWorkerReplyRequest): Promise<DevChatWorkerReplyResult> {
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
        max_tokens: 1024,
        reasoning_format: 'parsed',
        stream: false,
      }),
      signal: request.signal,
    });

    const text = await response.text();
    if (!response.ok) {
      const payload = extractErrorPayload(text);
      const classification = classifyWorkerFailure({
        status: response.status,
        errorType: payload.type,
        errorCode: payload.code,
        bodySnippet: payload.snippet,
      });
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

    return { ok: true, content, route: SOVEREIGN_WORKER_CHAT };
  } catch (error) {
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

/**
 * Streaming variant of fetchDevChatWorkerReply.
 * Posts with stream: true and yields SSE delta chunks in real-time.
 * Falls back to the non-streaming route if response.body is unavailable.
 */
export async function* streamDevChatWorkerReply(
  request: DevChatWorkerReplyRequest,
): AsyncGenerator<string> {
  const messages = request.messages
    .map((message) => ({ role: message.role, content: message.content.trim() }))
    .filter((message) => message.content.length > 0);
  const model = normalizeDevChatWorkerModel(request.model);

  if (messages.length === 0) return;

  const response = await fetch(SOVEREIGN_WORKER_CHAT, {
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
      max_tokens: 1024,
      reasoning_format: 'parsed',
      stream: true,
    }),
    signal: request.signal,
  });

  if (!response.ok) return;
  if (!response.body) {
    // Fallback: fetch non-streaming response and yield content at once
    const fallback = await fetchDevChatWorkerReply(request);
    if (fallback.ok && fallback.content) yield fallback.content;
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
