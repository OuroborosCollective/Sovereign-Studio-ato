/**
 * Toolchain Auto-Calling Runtime
 *
 * Deterministically selects safe read-only Toolchain calls for the chat runtime.
 * It never performs write tools automatically. Write-capable intents may only be
 * surfaced as context so the normal confirm=true / Draft PR path remains the
 * source of truth.
 */

import type { DevChatRepoSnapshot, DevChatRepoTreeFile } from './devChatWorkerBridge';

export const TOOLCHAIN_UNIVERSAL_INVOKE_ENDPOINT = '/api/toolchain/universal/invoke' as const;

export type ToolchainAutoToolName =
  | 'toolchain_briefing'
  | 'plan_sandbox_commands'
  | 'github_read_file';

export interface ToolchainAutoCall {
  readonly tool: ToolchainAutoToolName;
  readonly args: Record<string, unknown>;
  readonly reason: string;
  readonly writeAction: false;
}

export interface ToolchainAutoCallResult {
  readonly call: ToolchainAutoCall;
  readonly ok: boolean;
  readonly summary: string;
}

export interface ToolchainAutoContextRequest {
  readonly submittedText: string;
  readonly repoSnapshot?: DevChatRepoSnapshot | null;
  readonly fetchImpl?: typeof fetch;
  readonly endpoint?: string;
  readonly maxCalls?: number;
}

export interface ToolchainAutoContextResult {
  readonly context: string;
  readonly calls: readonly ToolchainAutoCall[];
  readonly results: readonly ToolchainAutoCallResult[];
  readonly writeIntentDetected: boolean;
}

const VERIFY_WORDS = [
  'typecheck', 'type-check', 'tsc', 'test', 'vitest', 'build', 'verify',
  'lint', 'ci', 'workflow', 'prüf', 'pruef', 'check', 'fehlerlog', 'error log',
];

const TOOLCHAIN_WORDS = [
  'toolchain', 'mcp', 'openapi', 'no-code', 'nocode', 'n8n', 'make', 'retool',
  'bubble', 'werkzeug', 'tools', 'function call', 'calling', 'dispatcher',
];

const WRITE_WORDS = [
  'draft pr', 'pull request', 'pr erstellen', 'patch anwenden', 'apply', 'commit',
  'push', 'schreib', 'write', 'umsetzen', 'fixe', 'fixen', 'baue', 'bauen',
];

const PATH_PATTERN = /(?:^|\s|`)([\w@./-]+\.(?:ts|tsx|js|jsx|mjs|cjs|py|md|json|css|scss|yml|yaml|sh|toml|txt))(?:`|\s|$)/i;

function includesAny(text: string, words: readonly string[]): boolean {
  const lower = text.toLowerCase();
  return words.some((word) => lower.includes(word));
}

function repoFiles(snapshot?: DevChatRepoSnapshot | null): readonly DevChatRepoTreeFile[] {
  return snapshot?.files?.filter((file) => file.type === 'blob') ?? [];
}

function normalizeBasename(path: string): string {
  const slash = path.lastIndexOf('/');
  return slash >= 0 ? path.slice(slash + 1).toLowerCase() : path.toLowerCase();
}

export function detectToolchainWriteIntent(text: string): boolean {
  return includesAny(text, WRITE_WORDS);
}

export function extractToolchainFileTarget(
  text: string,
  snapshot?: DevChatRepoSnapshot | null,
): string | null {
  const files = repoFiles(snapshot);
  const lowerText = text.toLowerCase();

  const exact = files.find((file) => lowerText.includes(file.path.toLowerCase()));
  if (exact) return exact.path;

  const mentioned = text.match(PATH_PATTERN)?.[1]?.replace(/^\.\//, '');
  if (mentioned) {
    const direct = files.find((file) => file.path.toLowerCase() === mentioned.toLowerCase());
    if (direct) return direct.path;
    if (mentioned.includes('/')) return mentioned;
  }

  const basenameMatches = files.filter((file) => lowerText.includes(normalizeBasename(file.path)));
  if (basenameMatches.length === 1) return basenameMatches[0].path;

  return null;
}

export function planToolchainAutoCalls(request: ToolchainAutoContextRequest): readonly ToolchainAutoCall[] {
  const text = request.submittedText.trim();
  if (!text) return [];
  const maxCalls = Math.max(0, request.maxCalls ?? 3);
  const calls: ToolchainAutoCall[] = [];

  if (includesAny(text, TOOLCHAIN_WORDS)) {
    calls.push({
      tool: 'toolchain_briefing',
      args: {},
      reason: 'Der Auftrag fragt nach Toolchain/MCP/OpenAPI/Workspace-Werkzeugen.',
      writeAction: false,
    });
  }

  if (includesAny(text, VERIFY_WORDS)) {
    calls.push({
      tool: 'plan_sandbox_commands',
      args: { goal: text.slice(0, 420) },
      reason: 'Der Auftrag verlangt Prüfung, Build, Typecheck, Tests oder CI-Planung.',
      writeAction: false,
    });
  }

  const targetPath = extractToolchainFileTarget(text, request.repoSnapshot);
  if (targetPath && request.repoSnapshot) {
    calls.push({
      tool: 'github_read_file',
      args: {
        owner: request.repoSnapshot.owner,
        repo: request.repoSnapshot.repo,
        path: targetPath,
        ref: request.repoSnapshot.branch,
      },
      reason: 'Der Auftrag nennt eine konkrete Repo-Datei; Lesen ist als Kontext erlaubt.',
      writeAction: false,
    });
  }

  return calls.slice(0, maxCalls);
}

function compact(value: unknown, max = 1800): string {
  const raw = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const clean = raw.replace(/\s+$/g, '').trim();
  return clean.length > max ? `${clean.slice(0, max)}\n…[gekürzt]` : clean;
}

async function invokeReadOnlyTool(
  call: ToolchainAutoCall,
  fetchImpl: typeof fetch,
  endpoint: string,
): Promise<ToolchainAutoCallResult> {
  try {
    const response = await fetchImpl(endpoint, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool: call.tool, args: call.args }),
    });
    const text = await response.text();
    let payload: unknown = text;
    try { payload = text ? JSON.parse(text) : {}; } catch { /* keep raw text */ }

    if (!response.ok) {
      return {
        call,
        ok: false,
        summary: `HTTP ${response.status}: ${compact(payload, 800)}`,
      };
    }

    return {
      call,
      ok: true,
      summary: compact(payload),
    };
  } catch (error) {
    return {
      call,
      ok: false,
      summary: error instanceof Error ? error.message : 'Toolchain-Aufruf fehlgeschlagen.',
    };
  }
}

export function formatToolchainAutoContext(args: {
  readonly results: readonly ToolchainAutoCallResult[];
  readonly writeIntentDetected: boolean;
}): string {
  const sections: string[] = [];

  if (args.results.length > 0) {
    sections.push('── Sovereign Toolchain Auto-Calls (read-only) ──');
    for (const result of args.results) {
      sections.push([
        `Tool: ${result.call.tool}`,
        `Grund: ${result.call.reason}`,
        `Status: ${result.ok ? 'ok' : 'blocked/error'}`,
        `Ergebnis:\n${result.summary}`,
      ].join('\n'));
    }
  }

  if (args.writeIntentDetected) {
    sections.push([
      '── Toolchain Write Guard ──',
      'Der Nutzerauftrag kann Schreib-/Draft-PR-Arbeit meinen.',
      'Automatische Toolchain-Calls in diesem Chat-Pfad bleiben read-only.',
      'Write-Tools dürfen nur über confirm=true, Draft-PR-Pfad und Audit-Log laufen; niemals direkter main-Push.',
    ].join('\n'));
  }

  return sections.join('\n\n');
}

export async function buildToolchainAutoContext(
  request: ToolchainAutoContextRequest,
): Promise<ToolchainAutoContextResult> {
  const calls = planToolchainAutoCalls(request);
  const writeIntentDetected = detectToolchainWriteIntent(request.submittedText);
  const fetchImpl = request.fetchImpl ?? globalThis.fetch?.bind(globalThis);
  const endpoint = request.endpoint ?? TOOLCHAIN_UNIVERSAL_INVOKE_ENDPOINT;

  if (!fetchImpl || calls.length === 0) {
    return {
      calls,
      results: [],
      writeIntentDetected,
      context: formatToolchainAutoContext({ results: [], writeIntentDetected }),
    };
  }

  const results = await Promise.all(calls.map((call) => invokeReadOnlyTool(call, fetchImpl, endpoint)));
  return {
    calls,
    results,
    writeIntentDetected,
    context: formatToolchainAutoContext({ results, writeIntentDetected }),
  };
}
