/**
 * Git Patch Runtime — SEARCH/REPLACE patch engine for large files.
 *
 * Philosophy (Befund E, Audit 2026-07-02):
 *   Full-file replace is unsafe for large files like BuilderContainer.tsx.
 *   This module applies exact SEARCH/REPLACE blocks with strict safety rules:
 *   - Each search string must match exactly once in the file (0 or >1 → blocked).
 *   - dryRun: true returns the patched preview without returning it as the
 *     final content, so callers can show a diff before committing.
 *   - expectedSha can be used to verify the caller holds the correct version
 *     of the file before patching (checked externally against the GitHub blob SHA).
 *   - No secret-like patterns are leaked in error messages.
 */

export interface PatchBlock {
  readonly search: string;
  readonly replace: string;
}

export interface GitPatchRequest {
  readonly filePath: string;
  readonly fileContent: string;
  readonly expectedSha?: string;
  readonly blocks: readonly PatchBlock[];
  readonly dryRun?: boolean;
  readonly maxBlocks?: number;
  readonly maxSearchBytes?: number;
  readonly maxReplaceBytes?: number;
}

export interface GitPatchBlockResult {
  readonly index: number;
  readonly matchCount: number;
  readonly applied: boolean;
  readonly error?: string;
}

export interface GitPatchResult {
  readonly ok: boolean;
  readonly dryRun: boolean;
  readonly patched?: string;
  readonly blockResults: readonly GitPatchBlockResult[];
  readonly errors: readonly string[];
}

const DEFAULT_MAX_BLOCKS = 10;
const DEFAULT_MAX_SEARCH_BYTES = 8_000;
const DEFAULT_MAX_REPLACE_BYTES = 50_000;

const SECRET_PATTERNS = [
  /ghp_[a-zA-Z0-9_]{10,}/g,
  /github_pat_[a-zA-Z0-9_]{10,}/g,
  /AIza[a-zA-Z0-9_-]{20,}/g,
  /sk-[a-zA-Z0-9_-]{20,}/g,
  /Bearer\s+[a-zA-Z0-9._~+/-]+=*/gi,
];

function maskSecrets(text: string): string {
  let out = text;
  for (const pattern of SECRET_PATTERNS) {
    out = out.replace(pattern, '****');
  }
  return out;
}

function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

function countOccurrences(haystack: string, needle: string): number {
  if (!needle) return 0;
  let count = 0;
  let pos = 0;
  while ((pos = haystack.indexOf(needle, pos)) !== -1) {
    count++;
    pos += needle.length;
  }
  return count;
}

/**
 * Apply a sequence of SEARCH/REPLACE blocks to `fileContent`.
 *
 * Rules:
 * - Each block's `search` must appear exactly once in the current working
 *   content after all prior blocks have been applied (serial, not parallel).
 * - 0 matches → block error, patch aborted.
 * - >1 matches → block error, patch aborted.
 * - Empty `search` → block error, patch aborted.
 * - Limits: maxBlocks, maxSearchBytes, maxReplaceBytes enforced before apply.
 */
export function applyGitPatch(request: GitPatchRequest): GitPatchResult {
  const {
    filePath,
    fileContent,
    blocks,
    dryRun = false,
    maxBlocks = DEFAULT_MAX_BLOCKS,
    maxSearchBytes = DEFAULT_MAX_SEARCH_BYTES,
    maxReplaceBytes = DEFAULT_MAX_REPLACE_BYTES,
  } = request;

  const topErrors: string[] = [];

  if (!filePath.trim()) {
    topErrors.push('filePath is required.');
  }
  if (typeof fileContent !== 'string') {
    topErrors.push('fileContent must be a string.');
  }
  if (!Array.isArray(blocks) || blocks.length === 0) {
    topErrors.push('blocks must be a non-empty array.');
  }
  if (blocks.length > maxBlocks) {
    topErrors.push(`Too many blocks: ${blocks.length} (max ${maxBlocks}).`);
  }

  if (topErrors.length > 0) {
    return { ok: false, dryRun, blockResults: [], errors: topErrors };
  }

  let working = fileContent;
  const blockResults: GitPatchBlockResult[] = [];
  const applyErrors: string[] = [];

  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];

    if (!block.search) {
      const err = `Block ${i}: search string is empty.`;
      blockResults.push({ index: i, matchCount: 0, applied: false, error: err });
      applyErrors.push(err);
      break;
    }

    if (utf8ByteLength(block.search) > maxSearchBytes) {
      const err = `Block ${i}: search string exceeds ${maxSearchBytes} bytes.`;
      blockResults.push({ index: i, matchCount: 0, applied: false, error: err });
      applyErrors.push(err);
      break;
    }

    if (utf8ByteLength(block.replace) > maxReplaceBytes) {
      const err = `Block ${i}: replace string exceeds ${maxReplaceBytes} bytes.`;
      blockResults.push({ index: i, matchCount: 0, applied: false, error: err });
      applyErrors.push(err);
      break;
    }

    const matchCount = countOccurrences(working, block.search);

    if (matchCount === 0) {
      const snippet = maskSecrets(block.search.slice(0, 60));
      const err = `Block ${i}: search string not found in file. Snippet: "${snippet}…"`;
      blockResults.push({ index: i, matchCount: 0, applied: false, error: err });
      applyErrors.push(err);
      break;
    }

    if (matchCount > 1) {
      const snippet = maskSecrets(block.search.slice(0, 60));
      const err = `Block ${i}: search string matched ${matchCount} times — must match exactly once. Snippet: "${snippet}…"`;
      blockResults.push({ index: i, matchCount, applied: false, error: err });
      applyErrors.push(err);
      break;
    }

    working = working.replace(block.search, block.replace);
    blockResults.push({ index: i, matchCount: 1, applied: true });
  }

  if (applyErrors.length > 0) {
    return { ok: false, dryRun, blockResults, errors: applyErrors };
  }

  return {
    ok: true,
    dryRun,
    patched: working,
    blockResults,
    errors: [],
  };
}

/**
 * Validate a patch request without applying it.
 * Useful for pre-flight checks before presenting a confirmation UI.
 */
export function validateGitPatchRequest(request: GitPatchRequest): readonly string[] {
  const errors: string[] = [];
  const maxBlocks = request.maxBlocks ?? DEFAULT_MAX_BLOCKS;
  const maxSearchBytes = request.maxSearchBytes ?? DEFAULT_MAX_SEARCH_BYTES;
  const maxReplaceBytes = request.maxReplaceBytes ?? DEFAULT_MAX_REPLACE_BYTES;

  if (!request.filePath?.trim()) errors.push('filePath is required.');
  if (typeof request.fileContent !== 'string') errors.push('fileContent must be a string.');
  if (!Array.isArray(request.blocks) || request.blocks.length === 0) errors.push('blocks must be a non-empty array.');
  if (request.blocks.length > maxBlocks) errors.push(`Too many blocks: ${request.blocks.length} (max ${maxBlocks}).`);

  for (let i = 0; i < request.blocks.length; i++) {
    const b = request.blocks[i];
    if (!b.search) errors.push(`Block ${i}: search string is empty.`);
    if (utf8ByteLength(b.search ?? '') > maxSearchBytes) {
      errors.push(`Block ${i}: search string exceeds ${maxSearchBytes} bytes.`);
    }
    if (utf8ByteLength(b.replace ?? '') > maxReplaceBytes) {
      errors.push(`Block ${i}: replace string exceeds ${maxReplaceBytes} bytes.`);
    }
  }

  return errors;
}
