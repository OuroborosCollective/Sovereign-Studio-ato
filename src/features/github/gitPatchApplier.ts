/**
 * Git Patch Applier — SEARCH/REPLACE patch engine
 *
 * Befund E (Audit 2026-07-02): Full-file writes are too risky for large live-path
 * files like BuilderContainer.tsx. This module implements a guarded SEARCH/REPLACE
 * patch path that enforces:
 *   - Repo allowlist
 *   - Branch allowlist (never writes directly to protected branches)
 *   - Exact-match-count check  (0 → blocked, >1 → blocked, 1 → apply)
 *   - Per-block and total size limits
 *   - Secret scanning before any log/response
 *   - dryRun support (returns preview without writing)
 *   - expectedSha guard (detects concurrent edits)
 *
 * No GitHub token is handled here. The caller is responsible for obtaining a
 * token via githubAuthSession and passing it as `token`.
 */

export interface PatchBlock {
  readonly search: string;
  readonly replace: string;
}

export interface GitPatchRequest {
  readonly repoUrl: string;
  readonly branch: string;
  readonly filePath: string;
  readonly blocks: readonly PatchBlock[];
  readonly commitMessage: string;
  readonly expectedSha?: string;
  readonly dryRun?: boolean;
  readonly token: string;
  readonly fetcher?: typeof fetch;
}

export interface GitPatchResult {
  readonly ok: boolean;
  readonly dryRun: boolean;
  readonly appliedBlocks: number;
  readonly newContent?: string;
  readonly commitSha?: string;
  readonly error?: string;
}

import { buildUnifiedLikePreview, type GeneratedFileDiffReport } from '../product/runtime/generatedFileDiffPreview';

export interface GitPatchValidationReport {
  readonly valid: boolean;
  readonly errors: readonly string[];
}

const ALLOWED_REPOS: readonly string[] = [
  'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
];

const PROTECTED_BRANCHES: readonly string[] = ['main', 'master', 'production'];
const PROTECTED_BRANCH_PREFIXES: readonly string[] = ['release/'];

const MAX_FILE_BYTES = 500_000;
const MAX_BLOCKS = 20;
const MAX_BLOCK_SEARCH_BYTES = 8_000;
const MAX_BLOCK_REPLACE_BYTES = 8_000;

function maskSecrets(text: string): string {
  return text
    .replace(/(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9_]{8,100}/g, '$1_****')
    .replace(/github_pat_[a-zA-Z0-9_]{20,200}/g, 'github_pat_****')
    .replace(/AIza[a-zA-Z0-9_-]{26,60}/g, 'AIza****')
    .replace(/sk-[a-zA-Z0-9_-]{20,120}/g, 'sk-****')
    .replace(/Bearer\s+[a-zA-Z0-9._~+/-]+=*/gi, 'Bearer ****');
}

function looksLikeSecret(value: string): boolean {
  const lower = value.toLowerCase();
  return (
    lower.includes('authorization: bearer') ||
    lower.includes('x-oauth-basic') ||
    lower.includes('private_key') ||
    lower.includes('access_token=')
  );
}

export function validateGitPatchRequest(req: GitPatchRequest): GitPatchValidationReport {
  const errors: string[] = [];

  const normalizedRepo = req.repoUrl.trim().replace(/\.git$/, '');
  if (!ALLOWED_REPOS.includes(normalizedRepo)) {
    errors.push(`Repo not in allowlist: ${maskSecrets(normalizedRepo)}`);
  }

  if (PROTECTED_BRANCHES.includes(req.branch.trim())) {
    errors.push(
      `Branch '${req.branch}' is protected. Use a feature branch and open a Draft PR.`,
    );
  }
  if (PROTECTED_BRANCH_PREFIXES.some((prefix) => req.branch.trim().startsWith(prefix))) {
    errors.push(
      `Branch '${req.branch}' is protected. Use a feature branch and open a Draft PR.`,
    );
  }

  const cleanPath = req.filePath.trim().replace(/^\/+/, '');
  if (!cleanPath || cleanPath.includes('..')) {
    errors.push(`Invalid filePath: ${cleanPath}`);
  }

  if (req.blocks.length === 0) {
    errors.push('At least one patch block is required.');
  }
  if (req.blocks.length > MAX_BLOCKS) {
    errors.push(`Too many blocks: ${req.blocks.length} (max ${MAX_BLOCKS}).`);
  }

  for (let i = 0; i < req.blocks.length; i++) {
    const b = req.blocks[i];
    if (!b.search.trim()) errors.push(`Block ${i}: search string must not be empty.`);
    if (b.search.length > MAX_BLOCK_SEARCH_BYTES) {
      errors.push(`Block ${i}: search string too large (${b.search.length} bytes, max ${MAX_BLOCK_SEARCH_BYTES}).`);
    }
    if (b.replace.length > MAX_BLOCK_REPLACE_BYTES) {
      errors.push(`Block ${i}: replace string too large (${b.replace.length} bytes, max ${MAX_BLOCK_REPLACE_BYTES}).`);
    }
    if (looksLikeSecret(b.search) || looksLikeSecret(b.replace)) {
      errors.push(`Block ${i}: secret-like content detected in patch block.`);
    }
  }

  if (!req.commitMessage.trim()) {
    errors.push('commitMessage must not be empty.');
  }

  return { valid: errors.length === 0, errors };
}

function countExactMatches(haystack: string, needle: string): number {
  if (!needle) return 0;
  let count = 0;
  let pos = 0;
  while ((pos = haystack.indexOf(needle, pos)) !== -1) {
    count++;
    pos += needle.length;
  }
  return count;
}

function applyBlocks(
  original: string,
  blocks: readonly PatchBlock[],
): { ok: false; error: string } | { ok: true; result: string; appliedBlocks: number } {
  let content = original;
  let appliedBlocks = 0;

  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    const matches = countExactMatches(content, b.search);

    if (matches === 0) {
      return {
        ok: false,
        error: `Block ${i}: search string found 0 times — patch aborted. Ensure the search string is an exact verbatim copy including whitespace.`,
      };
    }
    if (matches > 1) {
      return {
        ok: false,
        error: `Block ${i}: search string found ${matches} times — patch aborted. Provide enough context to make the match unique.`,
      };
    }

    content = content.replace(b.search, b.replace);
    appliedBlocks++;
  }

  return { ok: true, result: content, appliedBlocks };
}

interface GitHubFileResponse {
  content?: string;
  sha?: string;
  size?: number;
  encoding?: string;
}

function parseRepoFromUrl(repoUrl: string): { owner: string; repo: string } | null {
  const match = repoUrl
    .trim()
    .replace(/\.git$/, '')
    .match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)$/i);
  if (!match) return null;
  return { owner: match[1], repo: match[2] };
}

export function convertPatchResultToDiffReport(
  filePath: string,
  originalContent: string,
  patchResult: GitPatchResult,
): GeneratedFileDiffReport {
  const newContent = patchResult.newContent ?? originalContent;
  const oldLines = originalContent.split(/\r?\n/);
  const newLines = newContent.split(/\r?\n/);
  const changed = originalContent !== newContent;

  const item = {
    path: filePath,
    kind: (changed ? 'modified' : 'unchanged') as any,
    oldLineCount: oldLines.length,
    newLineCount: newLines.length,
    addedLines: Math.max(0, newLines.length - oldLines.length),
    removedLines: Math.max(0, oldLines.length - newLines.length),
    changed,
    summary: changed
      ? `${filePath} will change from ${oldLines.length} to ${newLines.length} line(s).`
      : `${filePath} appears unchanged.`,
    preview: buildUnifiedLikePreview(filePath, originalContent, newContent),
  };

  return {
    files: [item],
    created: 0,
    modified: changed ? 1 : 0,
    unchanged: changed ? 0 : 1,
    sourceMissing: 0,
    totalAddedLines: item.addedLines,
    totalRemovedLines: item.removedLines,
    summary: `Patch dry-run for ${filePath}: ${changed ? '1 modified' : 'unchanged'}.`,
  };
}

export async function applyGitPatch(req: GitPatchRequest): Promise<GitPatchResult> {
  const validation = validateGitPatchRequest(req);
  if (!validation.valid) {
    return { ok: false, dryRun: req.dryRun ?? false, appliedBlocks: 0, error: validation.errors.join(' | ') };
  }

  const fetcher = req.fetcher ?? fetch;
  const parsed = parseRepoFromUrl(req.repoUrl);
  if (!parsed) {
    return { ok: false, dryRun: req.dryRun ?? false, appliedBlocks: 0, error: 'Could not parse repoUrl.' };
  }

  const { owner, repo } = parsed;
  const cleanPath = req.filePath.trim().replace(/^\/+/, '');
  const apiBase = `https://api.github.com/repos/${owner}/${repo}/contents/${cleanPath}`;

  const fileResp = await fetcher(`${apiBase}?ref=${encodeURIComponent(req.branch)}`, {
    headers: {
      Authorization: `Bearer ${req.token}`,
      Accept: 'application/vnd.github.v3+json',
    },
  });

  if (!fileResp.ok) {
    const msg = await fileResp.text().catch(() => '(no body)');
    return {
      ok: false,
      dryRun: req.dryRun ?? false,
      appliedBlocks: 0,
      error: `GitHub GET file failed (${fileResp.status}): ${maskSecrets(msg)}`,
    };
  }

  const fileData = (await fileResp.json()) as GitHubFileResponse;
  const currentSha = fileData.sha ?? '';

  if (req.expectedSha && currentSha !== req.expectedSha) {
    return {
      ok: false,
      dryRun: req.dryRun ?? false,
      appliedBlocks: 0,
      error: `SHA mismatch: expected ${req.expectedSha}, got ${currentSha}. File was changed by someone else — please re-fetch and re-apply.`,
    };
  }

  const rawContent = fileData.content ?? '';
  const encoding = fileData.encoding ?? 'base64';
  const originalContent =
    encoding === 'base64'
      ? decodeURIComponent(
          escape(atob(rawContent.replace(/\n/g, '')))
        )
      : rawContent;

  if (originalContent.length > MAX_FILE_BYTES) {
    return {
      ok: false,
      dryRun: req.dryRun ?? false,
      appliedBlocks: 0,
      error: `File too large: ${originalContent.length} bytes (max ${MAX_FILE_BYTES}).`,
    };
  }

  const patchResult = applyBlocks(originalContent, req.blocks);
  if (patchResult.ok === false) {
    return {
      ok: false,
      dryRun: req.dryRun ?? false,
      appliedBlocks: 0,
      error: patchResult.error,
    };
  }

  if (req.dryRun) {
    return {
      ok: true,
      dryRun: true,
      appliedBlocks: patchResult.appliedBlocks,
      newContent: patchResult.result,
    };
  }

  const encoded = btoa(unescape(encodeURIComponent(patchResult.result)));
  const putResp = await fetcher(apiBase, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${req.token}`,
      Accept: 'application/vnd.github.v3+json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message: req.commitMessage,
      content: encoded,
      sha: currentSha,
      branch: req.branch,
    }),
  });

  if (!putResp.ok) {
    const msg = await putResp.text().catch(() => '(no body)');
    return {
      ok: false,
      dryRun: false,
      appliedBlocks: 0,
      error: `GitHub PUT file failed (${putResp.status}): ${maskSecrets(msg)}`,
    };
  }

  const putData = (await putResp.json()) as { commit?: { sha?: string } };

  return {
    ok: true,
    dryRun: false,
    appliedBlocks: patchResult.appliedBlocks,
    commitSha: putData.commit?.sha,
  };
}
