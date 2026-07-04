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
 * - No fake success - every action produces verifiable state.
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
  repoFiles: readonly string[],
): string | null {
  const lower = instruction.toLowerCase();
  
  // Common README patterns
  if (lower.includes('readme')) {
    const readmeFiles = repoFiles.filter((f) =>
      /^readme\.md$/i.test(f) || /^readme\.[a-z]{2,3}\.md$/i.test(f),
    );
    if (readmeFiles.length === 1) return readmeFiles[0];
    if (readmeFiles.length > 1) return readmeFiles.find((f) => f === 'README.md') || readmeFiles[0];
  }
  
  // docs pattern
  if (lower.includes('docs') || lower.includes('dokumentation')) {
    const docFiles = repoFiles.filter((f) => /^docs\/.*\.md$/i.test(f) || /^doc\/.*\.md$/i.test(f));
    if (docFiles.length > 0) return docFiles[0];
  }
  
  // If instruction explicitly mentions a file path
  const pathMatch = instruction.match(/[a-zA-Z0-9_\-./]+\.(md|mdx|mdoc)/i);
  if (pathMatch) {
    const potentialPath = pathMatch[0];
    if (repoFiles.some((f) => f.toLowerCase() === potentialPath.toLowerCase())) {
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
}

/**
 * Checks if the Direct GitHub Patch route is available for the given context.
 */
export function checkDirectPatchCapability(args: CheckDirectPatchCapabilityArgs): DirectGitHubPatchCapability {
  const { repoContext, githubAccessReady, instruction } = args;
  
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
  const targetPath = detectDirectPatchTarget(instruction, repoContext.files);
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
    };
    return {
      available: false,
      reason: blockerMessages[pathBlocker],
      blocker: pathBlocker,
    };
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
  
  // Validate target path
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
 */
export function buildDirectPatchPlan(
  args: BuildDirectPatchPlanArgs,
): { capability: DirectGitHubPatchCapability } | { result: DirectGitHubPatchResult } {
  const { repoContext, instruction, baseContent, githubAccessReady } = args;
  
  // Check capability first
  const capability = checkDirectPatchCapability({
    repoContext,
    githubAccessReady,
    instruction,
  });
  
  if (!capability.available) {
    return { capability };
  }
  
  // Detect target
  const targetPath = detectDirectPatchTarget(instruction, repoContext.files);
  if (!targetPath) {
    return {
      capability: {
        available: false,
        reason: 'Zieldatei konnte nicht erkannt werden.',
        blocker: 'target_not_in_repo',
      },
    };
  }
  
  // Execute runtime
  const result = executeDirectPatchRuntime({
    repoContext,
    instruction,
    baseContent,
    targetPath,
  });
  
  return { result };
}
