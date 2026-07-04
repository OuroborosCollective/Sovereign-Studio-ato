/**
 * Direct GitHub Patch Runtime
 * 
 * A lightweight alternative to OpenHands for small README/docs changes.
 * This runtime reads the target file, generates a patch based on the instruction,
 * and produces either a diff preview or a Draft PR.
 * 
 * Security rules (STRICT):
 * - Token NEVER stored in any state. Only fetcher with auth headers used.
 * - Patch must be validated against content before any GitHub write.
 * - Only safe paths allowed (README.md, docs/*.md, etc.)
 * - File content must be loaded before patching.
 */

import type {
  DirectGitHubPatchCapability,
  DirectGitHubPatchResult,
  DirectPatchRepoContext,
  DirectPatchBlocker,
  DirectPatchNextAction,
} from './directGithubPatchTypes';
import {
  isDirectPatchAllowedPath,
  isDirectPatchForbiddenPath,
  getDirectPatchPathBlocker,
} from './directGithubPatchTypes';

// ─────────────────────────────────────────────────────────────
// GitHub Content Loading
// ─────────────────────────────────────────────────────────────

export interface LoadFileContentArgs {
  readonly owner: string;
  readonly repo: string;
  readonly branch: string;
  readonly filePath: string;
  readonly token: string;
  readonly fetcher?: typeof fetch;
}

export interface LoadFileContentResult {
  readonly ok: boolean;
  readonly content?: string;
  readonly sha?: string;
  readonly error?: string;
}

/**
 * Loads file content from GitHub Contents API.
 * Token is passed in and used only for this API call, never stored.
 */
export async function loadGitHubFileContent(
  args: LoadFileContentArgs,
): Promise<LoadFileContentResult> {
  const { owner, repo, branch, filePath, token, fetcher = fetch } = args;
  
  try {
    const cleanPath = filePath.trim().replace(/^\/+/, '');
    const apiUrl = `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/contents/${encodeURIComponent(cleanPath)}?ref=${encodeURIComponent(branch)}`;
    
    const response = await fetcher(apiUrl, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github.v3+json',
      },
    });
    
    if (!response.ok) {
      const statusText = `HTTP ${response.status}`;
      return {
        ok: false,
        error: `GitHub Contents API failed: ${statusText}`,
      };
    }
    
    const data = await response.json() as { content?: string; sha?: string; encoding?: string };
    
    // GitHub returns base64-encoded content
    if (data.encoding === 'base64' && data.content) {
      // Decode base64 content
      const decoded = atob(data.content.replace(/\n/g, ''));
      return {
        ok: true,
        content: decoded,
        sha: data.sha,
      };
    }
    
    return {
      ok: false,
      error: 'Unexpected content format from GitHub API',
    };
  } catch (err) {
    return {
      ok: false,
      error: `Failed to load file content: ${err instanceof Error ? err.message : 'Unknown error'}`,
    };
  }
}

// ─────────────────────────────────────────────────────────────
// Intent Detection
// ─────────────────────────────────────────────────────────────

// Keywords that indicate a simple README/docs change
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
  'änder',
  'aktualisier',
  'update',
  'passe an',
  'fix',
];

// Keywords that indicate a complex task requiring OpenHands/Executor
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
];

/**
 * Detects if a message is a simple README/docs change intent
 * that could be handled by the Direct GitHub Patch route.
 */
export function isDirectPatchIntent(text: string): boolean {
  const lower = text.toLowerCase();
  
  // Check for direct patch keywords
  const hasDirectPatchKeyword = DIRECT_PATCH_INTENT_TOKENS.some((token) =>
    lower.includes(token),
  );
  
  // Check against complex task keywords
  const hasComplexTaskKeyword = COMPLEX_TASK_TOKENS.some((token) =>
    lower.includes(token),
  );
  
  // Simple heuristics: has README/docs keyword but no complex task keyword
  return hasDirectPatchKeyword && !hasComplexTaskKeyword;
}

/**
 * Detects the target file path from a direct patch instruction.
 * Returns null if no target can be determined.
 */
export function detectDirectPatchTarget(
  instruction: string,
  repoFilePaths: readonly string[],
): string | null {
  const lower = instruction.toLowerCase();
  
  // Common README patterns
  if (lower.includes('readme')) {
    const readmeFiles = repoFilePaths.filter((f) =>
      /^readme\.md$/i.test(f) || /^readme\.[a-z]{2,3}\.md$/i.test(f),
    );
    if (readmeFiles.length === 1) return readmeFiles[0];
    if (readmeFiles.length > 1) return readmeFiles.find((f) => f === 'README.md') || readmeFiles[0];
  }
  
  // docs pattern
  if (lower.includes('docs') || lower.includes('dokumentation')) {
    const docFiles = repoFilePaths.filter((f) => /^docs\/.*\.md$/i.test(f) || /^doc\/.*\.md$/i.test(f));
    if (docFiles.length > 0) return docFiles[0];
  }
  
  // If instruction explicitly mentions a file path
  const pathMatch = instruction.match(/[a-zA-Z0-9_\-./]+\.(md|mdx|mdoc)/i);
  if (pathMatch) {
    const potentialPath = pathMatch[0];
    if (repoFilePaths.some((f) => f.toLowerCase() === potentialPath.toLowerCase())) {
      return potentialPath;
    }
  }
  
  return null;
}

// ─────────────────────────────────────────────────────────────
// Capability Check
// ─────────────────────────────────────────────────────────────

export interface CheckDirectPatchCapabilityArgs {
  readonly repoContext: DirectPatchRepoContext | null;
  readonly githubAccessReady: boolean;
  readonly instruction: string;
  readonly baseContent?: string; // Optional - if provided, also checks content availability
}

/**
 * Checks if the Direct GitHub Patch route is available for the given context.
 * If baseContent is provided, also validates that content is loadable.
 */
export function checkDirectPatchCapability(args: CheckDirectPatchCapabilityArgs): DirectGitHubPatchCapability {
  const { repoContext, githubAccessReady, instruction, baseContent } = args;
  
  // Check GitHub access
  if (!githubAccessReady) {
    return {
      available: false,
      reason: 'GitHub-Zugang nicht bereit für Direct Patch Route.',
      blocker: 'github_access_missing',
    };
  }
  
  // Check repo context
  if (!repoContext) {
    return {
      available: false,
      reason: 'Repo-Kontext fehlt für Direct Patch Route.',
      blocker: 'repo_missing',
    };
  }
  
  // Check intent
  if (!isDirectPatchIntent(instruction)) {
    return {
      available: false,
      reason: 'Auftrag ist nicht einfach genug für Direct Patch Route. OpenHands/Executor wird empfohlen.',
      blocker: 'unsupported_intent',
    };
  }
  
  // Detect target
  const targetPath = detectDirectPatchTarget(instruction, repoContext.filePaths);
  if (!targetPath) {
    return {
      available: false,
      reason: 'Zieldatei konnte nicht erkannt werden.',
      blocker: 'target_not_in_repo',
    };
  }
  
  // Validate target path
  const pathBlocker = getDirectPatchPathBlocker(targetPath);
  if (pathBlocker) {
    const blockerMessages: Record<DirectPatchBlocker, string> = {
      'unsafe_target': 'Dateipfad nicht erlaubt für Direct Patch. Nutze OpenHands/Executor.',
      'unsupported_intent': 'Dateityp nicht unterstützt für Direct Patch v1.',
      'repo_missing': 'Repo-Kontext fehlt.',
      'github_access_missing': 'GitHub-Zugang nicht bereit.',
      'target_not_in_repo': 'Zieldatei nicht im Repo gefunden.',
      'content_load_failed': 'Zieldatei konnte nicht geladen werden.',
    };
    return {
      available: false,
      reason: blockerMessages[pathBlocker],
      blocker: pathBlocker,
    };
  }
  
  // If baseContent is provided, validate it is real content
  if (baseContent !== undefined) {
    // Reject placeholders like "[loaded]"
    if (baseContent.trim() === '' || baseContent === '[loaded]') {
      return {
        available: false,
        reason: 'Zieldatei konnte nicht geladen werden.',
        blocker: 'content_load_failed',
      };
    }
  }
  
  return {
    available: true,
    reason: `Direct Patch Route verfügbar für ${targetPath}.`,
  };
}

// ─────────────────────────────────────────────────────────────
// Patch Generation (Simple Text Manipulation)
// ─────────────────────────────────────────────────────────────

/**
 * Generates a patch for a README/docs file based on a simple instruction.
 * This is a simplified implementation - for production, use an LLM.
 * 
 * For v1, we focus on:
 * - Title/heading changes
 * - Adding content at the end
 * - Simple text replacements
 */
export function generateDirectPatchContent(
  baseContent: string,
  instruction: string,
): { content: string; summary: string } | null {
  const lower = instruction.toLowerCase();
  
  // Pattern: add emoji/symbol to title
  const titleEmojiMatch = lower.match(/(?:füge?|add|mit)\s*(.+?)\s*(?:in|to)\s*(?:den|die|das)?\s*(?:titel|title|überschrift|heading)/);
  if (titleEmojiMatch) {
    const emoji = titleEmojiMatch[1].trim();
    // Find first heading line (starts with #)
    const lines = baseContent.split('\n');
    let foundTitle = false;
    const newLines = lines.map((line) => {
      if (!foundTitle && line.trim().startsWith('#')) {
        foundTitle = true;
        return `${line.trim()} ${emoji}`;
      }
      return line;
    });
    
    if (foundTitle) {
      return {
        content: newLines.join('\n'),
        summary: `Added "${emoji}" to first title heading.`,
      };
    }
  }
  
  // Pattern: update title text
  const titleUpdateMatch = lower.match(/titel\s*(?:auf|zu|in)\s*["']?([^"']+)["']?|title\s*(?:to|to)\s*["']?([^"']+)["']?/);
  if (titleUpdateMatch) {
    const newTitle = titleUpdateMatch[1] || titleUpdateMatch[2];
    const lines = baseContent.split('\n');
    let foundTitle = false;
    const newLines = lines.map((line) => {
      if (!foundTitle && line.trim().startsWith('#')) {
        foundTitle = true;
        return `# ${newTitle}`;
      }
      return line;
    });
    
    if (foundTitle) {
      return {
        content: newLines.join('\n'),
        summary: `Updated title to "${newTitle}".`,
      };
    }
  }
  
  // Pattern: add content at end
  const addToEndMatch = lower.match(/(?:füge?|add|hinzu|ergänze|ergaenze)\s*(.+?)\s*(?:am ende|at the end|hinzu)/);
  if (addToEndMatch) {
    const additionalContent = addToEndMatch[1].trim();
    const newContent = baseContent.trim() + '\n\n' + additionalContent;
    return {
      content: newContent,
      summary: `Added content at the end.`,
    };
  }
  
  // Pattern: update/add changelog entry
  if (lower.includes('changelog') || lower.includes('history') || lower.includes('update history')) {
    const today = new Date().toISOString().split('T')[0];
    const changelogEntry = `- ${today}: ${instruction.replace(/changelog|history|update history/gi, '').trim()}`;
    
    // Try to find changelog section
    const lines = baseContent.split('\n');
    const changelogIndex = lines.findIndex((l) =>
      l.match(/^##?\s*(changelog|history|versions?|änderungen|updates?)/i),
    );
    
    if (changelogIndex >= 0) {
      lines.splice(changelogIndex + 1, 0, changelogEntry);
      return {
        content: lines.join('\n'),
        summary: `Added changelog entry for ${today}.`,
      };
    }
  }
  
  return null; // Could not generate patch for this instruction
}

// ─────────────────────────────────────────────────────────────
// Main Runtime Function
// ─────────────────────────────────────────────────────────────

export interface DirectPatchRuntimeArgs {
  readonly repoContext: DirectPatchRepoContext;
  readonly instruction: string;
  readonly baseContent: string;
  readonly targetPath: string;
}

/**
 * Executes the Direct GitHub Patch runtime for a simple README/docs change.
 * Returns a result that can be either a diff preview or a Draft PR request.
 */
export function executeDirectPatchRuntime(args: DirectPatchRuntimeArgs): DirectGitHubPatchResult {
  const { repoContext, instruction, baseContent, targetPath } = args;
  
  // Validate baseContent is loadable
  if (!baseContent || !baseContent.trim()) {
    return {
      ok: false,
      reason: 'Zieldatei konnte nicht geladen werden.',
      blocker: 'content_load_failed',
    };
  }
  
  // Validate target path is allowed for this route
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
  
  // Generate patch
  const patchResult = generateDirectPatchContent(baseContent, instruction);
  if (!patchResult) {
    return {
      ok: false,
      reason: 'Patch konnte nicht generiert werden. Auftrag ist möglicherweise zu komplex für Direct Patch.',
      blocker: 'unsupported_intent',
    };
  }
  
  // Validate patch is not empty
  if (patchResult.content.trim() === baseContent.trim()) {
    return {
      ok: false,
      reason: 'Patch würde keine Änderung erzeugen. Bitte Auftrag präzisieren.',
      blocker: 'unsupported_intent',
    };
  }
  
  // Validate patch doesn't contain secrets
  const secretPatterns = [
    /token/i,
    /password/i,
    /secret/i,
    /api[_-]?key/i,
    /ghp_[a-zA-Z0-9]{36,}/,
  ];
  const hasSecret = secretPatterns.some((pattern) => pattern.test(patchResult.content));
  if (hasSecret) {
    return {
      ok: false,
      reason: 'Patch enthält möglicherweise ein Secret. Bitte Token/Secrets entfernen.',
      blocker: 'unsafe_target',
    };
  }
  
  // Determine next action: preview first, then Draft PR
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

// ─────────────────────────────────────────────────────────────
// Builder Helper
// ─────────────────────────────────────────────────────────────

export interface BuildDirectPatchPlanArgs {
  readonly repoContext: DirectPatchRepoContext;
  readonly instruction: string;
  readonly baseContent: string;
  readonly githubAccessReady: boolean;
}

/**
 * Builds a complete Direct GitHub Patch plan or returns blockers.
 * This is the main entry point for BuilderContainer.
 * 
 * IMPORTANT: baseContent MUST be the real loaded file content.
 * No placeholder values are allowed in the live path.
 */
export function buildDirectPatchPlan(
  args: BuildDirectPatchPlanArgs,
): { capability: DirectGitHubPatchCapability } | { result: DirectGitHubPatchResult } {
  const { repoContext, instruction, baseContent, githubAccessReady } = args;
  
  // Detect target first - needed for capability validation
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
  
  // Check capability - validates github access, repo context, intent, and content
  const capability = checkDirectPatchCapability({
    repoContext,
    githubAccessReady,
    instruction,
    baseContent,
  });
  
  if (!capability.available) {
    return { capability };
  }
  
  // Execute runtime with validated content
  const result = executeDirectPatchRuntime({
    repoContext,
    instruction,
    baseContent,
    targetPath,
  });
  
  return { result };
}

// ─────────────────────────────────────────────────────────────
// Async Builder with Content Loading
// ─────────────────────────────────────────────────────────────

export interface BuildDirectPatchPlanWithLoadArgs {
  readonly repoContext: DirectPatchRepoContext;
  readonly instruction: string;
  readonly githubAccessReady: boolean;
  readonly token: string;
  readonly fetcher?: typeof fetch;
}

/**
 * Async version that loads file content from GitHub, then builds the patch plan.
 * This is the main entry point for BuilderContainer integration.
 * 
 * Flow:
 * 1. Detect target path
 * 2. Load content from GitHub
 * 3. If load fails: return blocker
 * 4. If load succeeds: buildDirectPatchPlan with real content
 */
export async function buildDirectPatchPlanWithContentLoad(
  args: BuildDirectPatchPlanWithLoadArgs,
): Promise<{ capability: DirectGitHubPatchCapability } | { result: DirectGitHubPatchResult }> {
  const { repoContext, instruction, githubAccessReady, token, fetcher = fetch } = args;
  
  // Step 1: Detect target path
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
  
  // Step 2: Load content from GitHub
  const loadResult = await loadGitHubFileContent({
    owner: repoContext.owner,
    repo: repoContext.name,
    branch: repoContext.branch,
    filePath: targetPath,
    token,
    fetcher,
  });
  
  // Step 3: If load fails, return blocker
  if (!loadResult.ok || !loadResult.content) {
    return {
      capability: {
        available: false,
        reason: 'Zieldatei konnte nicht geladen werden.',
        blocker: 'content_load_failed',
      },
    };
  }
  
  // Step 4: Build plan with real content
  const planResult = buildDirectPatchPlan({
    repoContext,
    instruction,
    baseContent: loadResult.content,
    githubAccessReady,
  });
  
  return planResult;
}
