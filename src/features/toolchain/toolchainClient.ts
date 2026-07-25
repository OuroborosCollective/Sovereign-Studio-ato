/**
 * toolchainClient — TypeScript-Client für den Sovereign Universal Toolchain Server.
 *
 * Alle Aufrufe gehen über den Flask-Backend-Proxy (POST /api/toolchain/universal/invoke),
 * damit der TOOLCHAIN_API_KEY nie im Frontend exponiert wird.
 *
 * Die eingebettete Toolchain wird ausschließlich über die registrierten
 * Backend-Verträge /api/toolchain/universal/{status,manifest,invoke} angesprochen.
 */

export interface ToolDefinition {
  name: string;
  description: string;
  write_action: boolean;
  requires_confirm?: boolean;
  input_schema: Record<string, unknown>;
}

export interface ToolResult {
  ok: boolean;
  tool: string;
  result?: unknown;
  error?: string;
}

export interface ToolchainManifest {
  name: string;
  tools: ToolDefinition[];
}

export interface ToolchainStatus {
  ok: boolean;
  name: string;
  version?: string;
  runtime?: string;
  toolCount?: number;
}

export type ToolchainFailureKind =
  | 'authentication'
  | 'permission'
  | 'not_found'
  | 'invalid_response'
  | 'client_request'
  | 'server'
  | 'network';

export class ToolchainRequestError extends Error {
  readonly kind: ToolchainFailureKind;
  readonly status?: number;

  constructor(message: string, kind: ToolchainFailureKind, status?: number) {
    super(message);
    this.name = 'ToolchainRequestError';
    this.kind = kind;
    this.status = status;
  }
}

const configuredApiBase = (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined)?.trim();
const API_BASE = (configuredApiBase || 'https://sovereign-backend.arelorian.de').replace(/\/$/, '');
const BASE = `${API_BASE}/api/toolchain/universal`;

export const SOVEREIGN_TOOLCHAIN_ENDPOINTS = {
  status: `${BASE}/status`,
  manifest: `${BASE}/manifest`,
  invoke: `${BASE}/invoke`,
} as const;

function failureKind(status: number): ToolchainFailureKind {
  if (status === 401) return 'authentication';
  if (status === 403) return 'permission';
  if (status === 404) return 'not_found';
  if (status >= 500) return 'server';
  return 'client_request';
}

function boundedSnippet(text: string): string {
  return text.replace(/\s+/g, ' ').trim().slice(0, 240);
}

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  let res: Response;
  try {
    const headers = new Headers(options?.headers);
    headers.set('Accept', 'application/json');
    if (options?.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    res = await fetch(url, {
      ...options,
      credentials: 'include',
      headers,
    });
  } catch (error) {
    throw new ToolchainRequestError(
      error instanceof Error ? error.message : 'Toolchain-Netzwerkanfrage fehlgeschlagen.',
      'network',
    );
  }

  const text = await res.text();
  let data: (T & { error?: string }) | null = null;
  if (text.trim()) {
    try {
      data = JSON.parse(text) as T & { error?: string };
    } catch {
      const contentType = res.headers.get('content-type')?.toLowerCase() ?? '';
      const htmlResponse = contentType.includes('text/html') || /^\s*</.test(text);
      const detail = boundedSnippet(text);
      throw new ToolchainRequestError(
        htmlResponse
          ? `Toolchain-Endpunkt lieferte HTML statt JSON${detail ? `: ${detail}` : ''}`
          : `Toolchain-Endpunkt lieferte ungültiges JSON${detail ? `: ${detail}` : ''}`,
        'invalid_response',
        res.status,
      );
    }
  }

  if (!res.ok) {
    throw new ToolchainRequestError(
      data?.error || `Toolchain HTTP ${res.status}`,
      failureKind(res.status),
      res.status,
    );
  }
  if (!data) {
    throw new ToolchainRequestError(
      'Toolchain-Endpunkt lieferte keine JSON-Antwort.',
      'invalid_response',
      res.status,
    );
  }
  return data;
}

export const toolchainClient = {
  /** Manifest aller verfügbaren Tools */
  manifest(): Promise<ToolchainManifest> {
    return req<ToolchainManifest>('/manifest');
  },

  /** Health / Status des Toolchain-Servers */
  status(): Promise<ToolchainStatus> {
    return req<ToolchainStatus>('/status');
  },

  /** Tool nach Name aufrufen */
  invoke(toolName: string, args: Record<string, unknown>): Promise<ToolResult> {
    return req<ToolResult>('/invoke', {
      method: 'POST',
      body: JSON.stringify({ tool: toolName, args }),
    });
  },

  /** Kurzform: GitHub-Datei lesen */
  githubReadFile(owner: string, repo: string, path: string, ref?: string): Promise<ToolResult> {
    return toolchainClient.invoke('github_read_file', { owner, repo, path, ...(ref ? { ref } : {}) });
  },

  /** Kurzform: SEARCH/REPLACE-Vorschau ohne Write */
  previewSearchReplace(path: string, content: string, blocks: Array<{ search: string; replace: string }>): Promise<ToolResult> {
    return toolchainClient.invoke('preview_search_replace', { path, content, blocks });
  },

  /** Kurzform: Draft PR via guarded patch */
  applyGuardrailsPR(confirm = false, expectedSha?: string): Promise<ToolResult> {
    return toolchainClient.invoke('apply_backend_guardrails_patch_pr', {
      confirm,
      ...(expectedSha ? { expected_sha: expectedSha } : {}),
    });
  },
} as const;
