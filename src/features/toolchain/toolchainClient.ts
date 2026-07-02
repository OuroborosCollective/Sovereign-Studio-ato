/**
 * toolchainClient — TypeScript-Client für den Sovereign Universal Toolchain Server.
 *
 * Alle Aufrufe gehen über den Flask-Backend-Proxy (POST /api/toolchain/universal/invoke),
 * damit der TOOLCHAIN_API_KEY nie im Frontend exponiert wird.
 *
 * Der Toolchain-Server läuft auf dem VPS unter:
 *   https://sovereign-backend.arelorian.de/toolchain/
 *   MCP:  /toolchain/mcp
 *   REST: /toolchain/api/v1/tools/{name}
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
  rest: string;
  openapi: string;
  mcp: string;
}

const BASE = '/api/toolchain/universal';

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json() as T & { error?: string };
  if (!res.ok) throw new Error((data as { error?: string }).error ?? `HTTP ${res.status}`);
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
