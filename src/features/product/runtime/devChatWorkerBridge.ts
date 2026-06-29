/**
 * DevChat Worker Bridge
 *
 * Typed runtime helpers extracted from the approved DevChat reference.
 * This module owns Cloudflare route constants and real GitHub URL parsing.
 * It contains no demo messages and no simulated model responses.
 */

export const SOVEREIGN_WORKER_BASE = 'https://sovereign-llm-proxy.projectouroboroscollective.workers.dev' as const;
export const SOVEREIGN_WORKER_CHAT = `${SOVEREIGN_WORKER_BASE}/v1/chat/completions` as const;
export const SOVEREIGN_WORKER_KV = `${SOVEREIGN_WORKER_BASE}/kv` as const;
export const SOVEREIGN_SESSION_KEY = 'sovereign-session-v1' as const;

export type DevChatWorkerModelTier = 'fast' | 'smart' | 'power';

export interface DevChatWorkerModel {
  readonly id: string;
  readonly label: string;
  readonly tier: DevChatWorkerModelTier;
  readonly thinking: boolean;
}

export const DEV_CHAT_WORKER_MODELS: readonly DevChatWorkerModel[] = [
  { id: 'deepseek-r1', label: 'DeepSeek R1', tier: 'power', thinking: true },
  { id: 'llama-3.1-8b', label: 'Llama 3.1 8B', tier: 'smart', thinking: false },
  { id: 'llama-3-8b', label: 'Llama 3 8B', tier: 'fast', thinking: false },
  { id: 'mistral-7b', label: 'Mistral 7B', tier: 'fast', thinking: false },
  { id: 'qwen-14b', label: 'Qwen 1.5 14B', tier: 'smart', thinking: false },
  { id: 'gemma-7b', label: 'Gemma 7B', tier: 'fast', thinking: false },
];


export interface DevChatWorkerMessage {
  readonly role: 'system' | 'user' | 'assistant';
  readonly content: string;
}

export interface DevChatWorkerReplyRequest {
  readonly model: string;
  readonly messages: readonly DevChatWorkerMessage[];
  readonly signal?: AbortSignal;
}

export interface DevChatWorkerReplyResult {
  readonly ok: boolean;
  readonly content?: string;
  readonly error?: string;
  readonly route: typeof SOVEREIGN_WORKER_CHAT;
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

  const direct = root.content ?? root.reply ?? root.text;
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

export async function fetchDevChatWorkerReply(request: DevChatWorkerReplyRequest): Promise<DevChatWorkerReplyResult> {
  const messages = request.messages
    .map((message) => ({ role: message.role, content: message.content.trim() }))
    .filter((message) => message.content.length > 0);

  if (messages.length === 0) {
    return { ok: false, error: 'Worker Chat blockiert: keine gültige Nachricht.', route: SOVEREIGN_WORKER_CHAT };
  }

  try {
    const response = await fetch(SOVEREIGN_WORKER_CHAT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        model: request.model,
        messages,
        temperature: 0.2,
        stream: false,
      }),
      signal: request.signal,
    });

    if (!response.ok) {
      return { ok: false, error: `Worker Chat HTTP ${response.status}`, route: SOVEREIGN_WORKER_CHAT };
    }

    const payload = await response.json();
    const content = readWorkerContent(payload);
    if (!content) {
      return { ok: false, error: 'Worker Chat lieferte keine auswertbare Antwort.', route: SOVEREIGN_WORKER_CHAT };
    }

    return { ok: true, content, route: SOVEREIGN_WORKER_CHAT };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Worker Chat Anfrage fehlgeschlagen.',
      route: SOVEREIGN_WORKER_CHAT,
    };
  }
}

