/**
 * Direct GitHub Patch Runtime
 *
 * Lightweight runtime route for small README/docs changes when OpenHands is not
 * configured. This module produces only a reviewable patch plan. It does not
 * write to GitHub and it never persists credentials.
 */

import type {
  DirectGitHubPatchCapability,
  DirectGitHubPatchResult,
  DirectPatchRepoContext,
  DirectPatchBlocker,
  DirectPatchNextAction,
} from './directGithubPatchTypes';
import {
  getDirectPatchPathBlocker,
  isDirectPatchAllowedPath,
  isDirectPatchForbiddenPath,
} from './directGithubPatchTypes';

export interface LoadFileContentArgs {
  readonly owner: string;
  readonly repo: string;
  readonly branch: string;
  readonly filePath: string;
  /** Ephemeral session value. Used only for this request, never logged or persisted. */
  readonly token: string;
  readonly fetcher?: typeof fetch;
}

export interface LoadFileContentResult {
  readonly ok: boolean;
  readonly content?: string;
  readonly sha?: string;
  readonly error?: string;
}

function encodeGitHubContentPath(filePath: string): string {
  const cleanPath = filePath.trim().replace(/^\/+/, '');
  return cleanPath.split('/').map(encodeURIComponent).join('/');
}

function decodeBase64Content(content: string): string {
  return atob(content.replace(/\n/g, ''));
}

/**
 * Loads file content from GitHub Contents API.
 *
 * The token is an ephemeral session value and is only used to build the request
 * header. The function never logs or returns it.
 */
export async function loadGitHubFileContent(
  args: LoadFileContentArgs,
): Promise<LoadFileContentResult> {
  const { owner, repo, branch, filePath, token, fetcher = fetch } = args;
  const encodedPath = encodeGitHubContentPath(filePath);
  const apiUrl = `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/contents/${encodedPath}?ref=${encodeURIComponent(branch)}`;

  try {
    const response = await fetcher(apiUrl, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github.v3+json',
      },
    });

    if (!response.ok) {
      return {
        ok: false,
        error: `GitHub Contents API failed: HTTP ${response.status}`,
      };
    }

    const data = await response.json() as { content?: string; sha?: string; encoding?: string; type?: string };
    if (data.type && data.type !== 'file') {
      return { ok: false, error: 'GitHub Contents API target is not a file' };
    }
    if (data.encoding !== 'base64' || !data.content) {
      return { ok: false, error: 'Unexpected content format from GitHub API' };
    }

    return {
      ok: true,
      content: decodeBase64Content(data.content),
      sha: data.sha,
    };
  } catch (error) {
    return {
      ok: false,
      error: `Failed to load file content: ${error instanceof Error ? error.message : 'Unknown error'}`,
    };
  }
}

const DIRECT_PATCH_INTENT_TOKENS = [
  'readme',
  'dokumentation',
  'docs',
  'changelog',
  'history',
  'titel',
  'title',
  'überschrift',
  'ueberschrift',
  'heading',
  'text',
  'inhalt',
  'content',
  'füge hinzu',
  'fuege hinzu',
  'hinzufügen',
  'add',
  'ergänze',
  'ergaenze',
  'änder',
  'aender',
  'aktualisier',
  'update',
  'passe an',
  'fix',
] as const;

const COMPLEX_TASK_TOKENS = [
  'implementier',
  'baue',
  'bauen',
  'code',
  'komponent',
  'function',
  'funktio',
  'test',
  'teste',
  'refaktor',
  'api',
  'server',
  'backend',
  'frontend',
  'database',
  'datenbank',
  'security',
  'sicherheit',
  'workflow',
  'ci/cd',
  'docker',
  'kubernetes',
  'deployment',
] as const;

export function isDirectPatchIntent(text: string): boolean {
  const lower = text.toLowerCase();
  const hasDirectPatchKeyword = DIRECT_PATCH_INTENT_TOKENS.some((token) => lower.includes(token));
  const hasComplexTaskKeyword = COMPLEX_TASK_TOKENS.some((token) => lower.includes(token));
  return hasDirectPatchKeyword && !hasComplexTaskKeyword;
}

function findReadmePath(repoFilePaths: readonly string[]): string | null {
  const readmeFiles = repoFilePaths.filter((path) => /^readme\.md$/i.test(path) || /^readme\.[a-z]{2,3}\.md$/i.test(path));
  if (readmeFiles.length === 0) return null;
  return readmeFiles.find((path) => path === 'README.md') ?? readmeFiles[0];
}

function findDocsPath(repoFilePaths: readonly string[]): string | null {
  return repoFilePaths.find((path) => /^docs\/.*\.md$/i.test(path) || /^doc\/.*\.md$/i.test(path) || /^documentation\/.*\.md$/i.test(path)) ?? null;
}

export function detectDirectPatchTarget(
  instruction: string,
  repoFilePaths: readonly string[],
): string | null {
  const lower = instruction.toLowerCase();
  const explicitPathMatch = instruction.match(/[a-zA-Z0-9_\-./]+\.(md|mdx|mdoc)/i);

  if (explicitPathMatch) {
    const explicitPath = explicitPathMatch[0].replace(/^\/+/, '');
    const matchedRepoPath = repoFilePaths.find((path) => path.toLowerCase() === explicitPath.toLowerCase());
    if (matchedRepoPath) return matchedRepoPath;
    if (repoFilePaths.length === 0 && isDirectPatchAllowedPath(explicitPath)) return explicitPath;
    return null;
  }

  if (lower.includes('readme')) {
    const readmePath = findReadmePath(repoFilePaths);
    if (readmePath) return readmePath;
    // BuilderContainer currently may only have a tree snapshot without filePaths.
    // README.md is the only safe implicit fallback; GitHub content loading verifies it.
    if (repoFilePaths.length === 0) return 'README.md';
  }

  if (lower.includes('docs') || lower.includes('dokumentation')) {
    return findDocsPath(repoFilePaths);
  }

  return null;
}

export interface CheckDirectPatchCapabilityArgs {
  readonly repoContext: DirectPatchRepoContext | null;
  readonly githubAccessReady: boolean;
  readonly instruction: string;
  readonly baseContent?: string;
}

export function checkDirectPatchCapability(args: CheckDirectPatchCapabilityArgs): DirectGitHubPatchCapability {
  const { repoContext, githubAccessReady, instruction, baseContent } = args;

  if (!githubAccessReady) {
    return {
      available: false,
      reason: 'GitHub-Zugang nicht bereit für Direct Patch Route.',
      blocker: 'github_access_missing',
    };
  }

  if (!repoContext) {
    return {
      available: false,
      reason: 'Repo-Kontext fehlt für Direct Patch Route.',
      blocker: 'repo_missing',
    };
  }

  if (!isDirectPatchIntent(instruction)) {
    return {
      available: false,
      reason: 'Auftrag ist nicht einfach genug für Direct Patch Route. OpenHands/Executor wird empfohlen.',
      blocker: 'unsupported_intent',
    };
  }

  const targetPath = detectDirectPatchTarget(instruction, repoContext.filePaths);
  if (!targetPath) {
    return {
      available: false,
      reason: 'Zieldatei konnte nicht erkannt werden.',
      blocker: 'target_not_in_repo',
    };
  }

  const pathBlocker = getDirectPatchPathBlocker(targetPath);
  if (pathBlocker) {
    const blockerMessages: Record<DirectPatchBlocker, string> = {
      unsafe_target: 'Dateipfad nicht erlaubt für Direct Patch. Nutze OpenHands/Executor.',
      unsupported_intent: 'Dateityp nicht unterstützt für Direct Patch v1.',
      repo_missing: 'Repo-Kontext fehlt.',
      github_access_missing: 'GitHub-Zugang nicht bereit.',
      target_not_in_repo: 'Zieldatei nicht im Repo gefunden.',
      content_load_failed: 'Zieldatei konnte nicht geladen werden.',
    };
    return {
      available: false,
      reason: blockerMessages[pathBlocker],
      blocker: pathBlocker,
    };
  }

  if (baseContent !== undefined && (!baseContent.trim() || baseContent.trim() === '[loaded]')) {
    return {
      available: false,
      reason: 'Zieldatei konnte nicht geladen werden.',
      blocker: 'content_load_failed',
    };
  }

  return {
    available: true,
    reason: `Direct Patch Route verfügbar für ${targetPath}.`,
  };
}

export function generateDirectPatchContent(
  baseContent: string,
  instruction: string,
): { content: string; summary: string } | null {
  const lower = instruction.toLowerCase();

  const titleEmojiMatch = lower.match(/(?:füge?|add|mit)\s*(.+?)\s*(?:in|to)\s*(?:den|die|das)?\s*(?:titel|title|überschrift|heading)/);
  if (titleEmojiMatch) {
    const marker = titleEmojiMatch[1].trim();
    let changed = false;
    const content = baseContent
      .split('\n')
      .map((line) => {
        if (changed || !line.trim().startsWith('#')) return line;
        changed = true;
        return `${line.trim()} ${marker}`;
      })
      .join('\n');
    return changed ? { content, summary: `Added "${marker}" to first title heading.` } : null;
  }

  const titleUpdateMatch = instruction.match(/(?:titel|title)\s*(?:auf|zu|in|to)\s*["']?([^"'\n]+)["']?/i);
  if (titleUpdateMatch) {
    const newTitle = titleUpdateMatch[1].trim();
    let changed = false;
    const content = baseContent
      .split('\n')
      .map((line) => {
        if (changed || !line.trim().startsWith('#')) return line;
        changed = true;
        return `# ${newTitle}`;
      })
      .join('\n');
    return changed ? { content, summary: `Updated title to "${newTitle}".` } : null;
  }

  const addToEndMatch = instruction.match(/(?:füge?|add|hinzu|ergänze|ergaenze)\s*(.+?)\s*(?:am ende|at the end|hinzu)/i);
  if (addToEndMatch) {
    const additionalContent = addToEndMatch[1].trim();
    if (!additionalContent) return null;
    return {
      content: `${baseContent.trimEnd()}\n\n${additionalContent}\n`,
      summary: 'Added content at the end.',
    };
  }

  if (lower.includes('changelog') || lower.includes('history') || lower.includes('update history')) {
    const today = new Date().toISOString().split('T')[0];
    const entry = `- ${today}: ${instruction.replace(/changelog|history|update history/gi, '').trim()}`;
    const lines = baseContent.split('\n');
    const changelogIndex = lines.findIndex((line) => /^##?\s*(changelog|history|versions?|änderungen|updates?)/i.test(line));
    if (changelogIndex >= 0) {
      lines.splice(changelogIndex + 1, 0, entry);
      return { content: lines.join('\n'), summary: `Added changelog entry for ${today}.` };
    }
  }

  return null;
}

function containsLikelySecret(content: string): boolean {
  return [
    /gh[pousr]_[A-Za-z0-9_]{20,}/,
    /(?:token|password|secret|api[_-]?key)\s*[:=]\s*['"]?[^\s'"]{8,}/i,
  ].some((pattern) => pattern.test(content));
}

export interface DirectPatchRuntimeArgs {
  readonly repoContext: DirectPatchRepoContext;
  readonly instruction: string;
  readonly baseContent: string;
  readonly targetPath: string;
}

export function executeDirectPatchRuntime(args: DirectPatchRuntimeArgs): DirectGitHubPatchResult {
  const { instruction, baseContent, targetPath } = args;

  if (!baseContent.trim() || baseContent.trim() === '[loaded]') {
    return {
      ok: false,
      reason: 'Zieldatei konnte nicht geladen werden.',
      blocker: 'content_load_failed',
    };
  }

  if (isDirectPatchForbiddenPath(targetPath)) {
    return {
      ok: false,
      reason: `Dateipfad "${targetPath}" nicht erlaubt für Direct Patch. Nutze OpenHands/Executor.`,
      blocker: 'unsafe_target',
    };
  }

  if (!isDirectPatchAllowedPath(targetPath)) {
    return {
      ok: false,
      reason: `Dateipfad "${targetPath}" nicht unterstützt für Direct Patch v1.`,
      blocker: 'unsupported_intent',
    };
  }

  const patchResult = generateDirectPatchContent(baseContent, instruction);
  if (!patchResult) {
    return {
      ok: false,
      reason: 'Patch konnte nicht generiert werden. Auftrag ist möglicherweise zu komplex für Direct Patch.',
      blocker: 'unsupported_intent',
    };
  }

  if (patchResult.content.trim() === baseContent.trim()) {
    return {
      ok: false,
      reason: 'Patch würde keine Änderung erzeugen. Bitte Auftrag präzisieren.',
      blocker: 'unsupported_intent',
    };
  }

  if (containsLikelySecret(patchResult.content)) {
    return {
      ok: false,
      reason: 'Patch enthält möglicherweise ein Secret. Bitte Tokens/Secrets entfernen.',
      blocker: 'unsafe_target',
    };
  }

  const nextAction: DirectPatchNextAction = 'preview_diff';
  return {
    ok: true,
    targetPath,
    patchSummary: patchResult.summary,
    nextAction,
    proposedContent: patchResult.content,
    instruction,
  };
}

export interface BuildDirectPatchPlanArgs {
  readonly repoContext: DirectPatchRepoContext;
  readonly instruction: string;
  readonly baseContent: string;
  readonly githubAccessReady: boolean;
}

export function buildDirectPatchPlan(
  args: BuildDirectPatchPlanArgs,
): { capability: DirectGitHubPatchCapability } | { result: DirectGitHubPatchResult } {
  const { repoContext, instruction, baseContent, githubAccessReady } = args;
  const capability = checkDirectPatchCapability({ repoContext, githubAccessReady, instruction, baseContent });
  if (!capability.available) return { capability };

  const targetPath = detectDirectPatchTarget(instruction, repoContext.filePaths);
  if (!targetPath) {
    return {
      capability: {
        available: false,
        reason: 'Zieldatei konnte nicht erkannt werden.',
        blocker: 'target_not_in_repo',
      },
    };
  }

  return {
    result: executeDirectPatchRuntime({ repoContext, instruction, baseContent, targetPath }),
  };
}

export interface BuildDirectPatchPlanWithLoadArgs {
  readonly repoContext: DirectPatchRepoContext;
  readonly instruction: string;
  readonly githubAccessReady: boolean;
  readonly token: string;
  readonly fetcher?: typeof fetch;
}

export async function buildDirectPatchPlanWithContentLoad(
  args: BuildDirectPatchPlanWithLoadArgs,
): Promise<{ capability: DirectGitHubPatchCapability } | { result: DirectGitHubPatchResult }> {
  const { repoContext, instruction, githubAccessReady, token, fetcher = fetch } = args;
  const capability = checkDirectPatchCapability({ repoContext, githubAccessReady, instruction });
  if (!capability.available) return { capability };

  const targetPath = detectDirectPatchTarget(instruction, repoContext.filePaths);
  if (!targetPath) {
    return {
      capability: {
        available: false,
        reason: 'Zieldatei konnte nicht erkannt werden.',
        blocker: 'target_not_in_repo',
      },
    };
  }

  const loadResult = await loadGitHubFileContent({
    owner: repoContext.owner,
    repo: repoContext.name,
    branch: repoContext.branch,
    filePath: targetPath,
    token,
    fetcher,
  });

  if (!loadResult.ok || !loadResult.content?.trim()) {
    return {
      capability: {
        available: false,
        reason: 'Zieldatei konnte nicht geladen werden.',
        blocker: 'content_load_failed',
      },
    };
  }

  return buildDirectPatchPlan({
    repoContext,
    instruction,
    baseContent: loadResult.content,
    githubAccessReady,
  });
}
