const SOVEREIGN_BACKEND_BASE_URL = 'https://sovereign-backend.arelorian.de';

type JsonObject = Record<string, unknown>;

export interface GitHubFileParams {
  owner: string;
  repo: string;
  branch: string;
  path: string;
}

export interface GitHubFileSnapshot {
  content: string;
  sha: string;
}

export interface RepositoryTreeEntry {
  path: string;
  type: 'blob' | 'tree';
  size?: number;
}

export interface DraftPatchParams extends GitHubFileParams {
  originalContent: string;
  updatedContent: string;
  expectedFileSha: string;
  commitMessage: string;
  branchName: string;
  title: string;
  body: string;
  baseBranch?: string;
}

export interface DraftPatchResult {
  prNumber: number;
  prUrl: string;
  branchName: string;
  diff: string;
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`${label} fehlt in der Backend-Antwort.`);
  }
  return value;
}

function requireInteger(value: unknown, label: string): number {
  if (!Number.isInteger(value) || Number(value) <= 0) {
    throw new Error(`${label} fehlt in der Backend-Antwort.`);
  }
  return Number(value);
}

function normalizeBackendUrl(value: string): string {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.hostname !== 'sovereign-backend.arelorian.de') {
    throw new Error('Die Mobile-App darf ausschließlich den kanonischen Sovereign-Backend-Gateway verwenden.');
  }
  return url.origin;
}

function requireObject(value: unknown, label: string): JsonObject {
  if (!isObject(value)) throw new Error(`${label} ist keine Objekt-Antwort.`);
  return value;
}

async function postGateway(path: string, payload: JsonObject): Promise<unknown> {
  const baseUrl = normalizeBackendUrl(SOVEREIGN_BACKEND_BASE_URL);
  const response = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error(`Sovereign-Gateway lieferte keine gültige JSON-Antwort (${response.status}).`);
  }
  if (!response.ok) {
    const message = isObject(data) && typeof data.error === 'string'
      ? data.error
      : `HTTP ${response.status}`;
    throw new Error(`Sovereign-Gateway verweigerte die Operation: ${message}`);
  }
  return data;
}

/**
 * Liest eine Datei ausschließlich über die sessiongeschützte, repo-allowlistete
 * Backend-Grenze. Die Mobile-App erhält und speichert keinen GitHub-PAT.
 */
export async function fetchFileFromGitHub({
  owner,
  repo,
  branch,
  path,
}: GitHubFileParams): Promise<GitHubFileSnapshot> {
  const data = requireObject(await postGateway('/api/toolchain/github/read-file', {
    owner,
    repo,
    path,
    ref: branch,
  }), 'GitHub-Dateiantwort');
  return {
    content: requireString(data.content, 'content'),
    sha: requireString(data.sha, 'sha'),
  };
}

/**
 * Baut einen begrenzten Repository-Baum ausschließlich über die kanonische
 * list-directory-Grenze auf. Keine freie GitHub-URL und kein Client-Token.
 */
export async function listRepositoryTree({
  owner,
  repo,
  branch,
  maxEntries = 250,
}: {
  owner: string;
  repo: string;
  branch: string;
  maxEntries?: number;
}): Promise<readonly RepositoryTreeEntry[]> {
  if (!Number.isInteger(maxEntries) || maxEntries < 1 || maxEntries > 500) {
    throw new Error('maxEntries muss zwischen 1 und 500 liegen.');
  }

  const queue: string[] = [''];
  const visited = new Set<string>();
  const result: RepositoryTreeEntry[] = [];

  while (queue.length > 0 && result.length < maxEntries) {
    const directory = queue.shift() ?? '';
    if (visited.has(directory)) continue;
    visited.add(directory);

    const raw = await postGateway('/api/toolchain/github/list-directory', {
      owner,
      repo,
      path: directory,
      ref: branch,
    });
    const entries = Array.isArray(raw)
      ? raw
      : isObject(raw) && Array.isArray(raw.items)
        ? raw.items
        : null;
    if (!entries) throw new Error('GitHub-Verzeichnisantwort besitzt keine Eintragsliste.');

    const normalized = entries
      .filter(isObject)
      .map((entry) => {
        const pathValue = requireString(entry.path, 'path');
        const typeValue = requireString(entry.type, 'type');
        if (typeValue !== 'blob' && typeValue !== 'tree') {
          throw new Error(`Nicht unterstützter GitHub-Eintragstyp: ${typeValue}`);
        }
        return {
          path: pathValue,
          type: typeValue,
          ...(Number.isFinite(entry.size) ? { size: Number(entry.size) } : {}),
        } satisfies RepositoryTreeEntry;
      })
      .sort((left, right) => left.path.localeCompare(right.path));

    for (const entry of normalized) {
      if (result.length >= maxEntries) break;
      result.push(entry);
      if (entry.type === 'tree' && !visited.has(entry.path)) queue.push(entry.path);
    }
  }

  return Object.freeze(result);
}

/**
 * Erstellt niemals einen Direkt-Push. Der Gateway erzeugt nach einer exakten
 * Search/Replace-Vorschau ausschließlich einen Draft-PR. Eine zwischenzeitlich
 * geänderte Datei wird vor der Mutation anhand ihrer SHA verworfen.
 */
export async function createDraftPatch({
  owner,
  repo,
  branch,
  path,
  originalContent,
  updatedContent,
  expectedFileSha,
  commitMessage,
  branchName,
  title,
  body,
  baseBranch = branch,
}: DraftPatchParams): Promise<DraftPatchResult> {
  const latest = await fetchFileFromGitHub({ owner, repo, branch, path });
  if (latest.sha !== expectedFileSha) {
    throw new Error('Die Datei wurde zwischenzeitlich geändert; Draft-PR-Erstellung wurde CAS-sicher abgebrochen.');
  }
  if (latest.content !== originalContent) {
    throw new Error('Der rückgelesene Dateiinhalt stimmt nicht mit der geprüften Ausgangsfassung überein.');
  }
  if (originalContent === updatedContent) {
    throw new Error('Es liegt keine Änderung für einen Draft-PR vor.');
  }

  const blocks = [{ search: originalContent, replace: updatedContent }];
  const preview = requireObject(await postGateway('/api/toolchain/preview-patch', {
    owner,
    repo,
    path,
    ref: branch,
    blocks,
  }), 'Patch-Vorschau');
  const diff = requireString(preview.diff, 'diff');

  const created = requireObject(await postGateway('/api/toolchain/create-draft-pr', {
    owner,
    repo,
    path,
    message: commitMessage,
    blocks,
    confirm: true,
    branch_name: branchName,
    title,
    body,
    base_branch: baseBranch,
  }), 'Draft-PR-Antwort');

  return {
    prNumber: requireInteger(created.pr_number, 'pr_number'),
    prUrl: requireString(created.pr_url, 'pr_url'),
    branchName: typeof created.branch === 'string' && created.branch ? created.branch : branchName,
    diff,
  };
}
