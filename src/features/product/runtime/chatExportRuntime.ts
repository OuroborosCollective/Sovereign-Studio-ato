/**
 * Chat Export Runtime - Safe chat export for Android share
 * 
 * Phase 1: Export current chat history as Markdown-like plain text
 * - Excludes thought/workstate lines by default
 * - Includes repo name/branch if available
 * - No secrets/tokens in exported text
 * - User-triggered only
 * 
 * Phase 2: Session history design is documented as a future extension.
 */

import type { DevChatRepoSnapshot } from './devChatWorkerBridge';

export interface ChatLine {
  readonly id: string;
  readonly role: 'system' | 'thought' | 'user' | 'assistant';
  readonly text: string;
  readonly file?: string;
  readonly path?: string;
  readonly createdAt?: number;
}

export interface ChatExportOptions {
  /** Exclude thought/runtime animation lines */
  excludeThoughts?: boolean;
  /** Include repo metadata */
  includeRepoMetadata?: boolean;
  /** Custom header text */
  customHeader?: string;
}

/**
 * Strip potential secrets/tokens from text
 */
function stripSecrets(text: string): string {
  // Strip potential tokens
  let stripped = text;
  
  // GitHub tokens: ghp_, gho_, ghu_, ghs_, ghr_ patterns
  const githubTokenRegex = /gh[phsu][_\w]{30,}/gi;
  if (githubTokenRegex.test(stripped)) {
    stripped = stripped.replace(/gh[phsu][_\w]{30,}/gi, '[TOKEN]');
  }
  
  // Bearer tokens
  stripped = stripped.replace(/Bearer\s+[\w-]{20,}/gi, 'Bearer [TOKEN]');
  
  // API keys (generic patterns)
  stripped = stripped.replace(/api[_-]?key["\s:=]+[\w-]{20,}/gi, 'api_key=[KEY]');
  
  // Generic long alphanumeric strings that might be tokens
  const hexPattern = /^[a-f0-9]{40,}$/i;
  stripped = stripped.replace(/\b[A-Za-z0-9]{40,}\b/g, (match) => {
    // Keep if it looks like a hex string (like commit hashes)
    if (hexPattern.test(match)) return match;
    return '[TOKEN]';
  });
  
  return stripped;
}

/**
 * Format a single chat line for export
 */
function formatLine(line: ChatLine, options: ChatExportOptions): string {
  const { excludeThoughts = true } = options;
  
  // Skip thought/runtime lines if option is set
  if (excludeThoughts && (line.role === 'thought' || line.role === 'system')) {
    return '';
  }
  
  const timestamp = line.createdAt 
    ? new Date(line.createdAt).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
    : '';
  
  const prefix = line.role === 'user' ? '**Du**' : '**Assistant**';
  const text = stripSecrets(line.text);
  
  // Include file reference if present
  const fileRef = line.file 
    ? `\n  📎 ${line.file}${line.path ? ` (${line.path})` : ''}`
    : '';
  
  return `${timestamp ? `[${timestamp}] ` : ''}${prefix}: ${text}${fileRef}`;
}

/**
 * Format repo metadata for export
 */
function formatRepoMetadata(repo: DevChatRepoSnapshot | null): string {
  if (!repo) return '';
  
  const lines = [
    '---',
    `**Repository**: ${repo.name}`,
    `**URL**: ${repo.repoUrl || 'N/A'}`,
    repo.branch ? `**Branch**: ${repo.branch}` : '',
    repo.fileCount ? `**Files**: ${repo.fileCount}` : '',
    repo.truncated ? '⚠️ *Snapshot truncated*' : '',
  ].filter(Boolean);
  
  return lines.join('\n') + '\n---\n\n';
}

/**
 * Export chat history as formatted string
 */
export function exportChatHistory(
  chatLines: ChatLine[],
  repoSnapshot: DevChatRepoSnapshot | null,
  options: ChatExportOptions = {}
): string {
  const {
    excludeThoughts = true,
    includeRepoMetadata = true,
    customHeader,
  } = options;
  
  const lines: string[] = [];
  
  // Header
  if (customHeader !== undefined && customHeader.length > 0) {
    lines.push(`# ${customHeader}`);
    lines.push('');
  } else {
    lines.push('# Sovereign Studio Chat Export');
    lines.push(`*Exportiert am ${new Date().toLocaleDateString('de-DE')} um ${new Date().toLocaleTimeString('de-DE')}*`);
    lines.push('');
  }
  
  // Repo metadata
  if (includeRepoMetadata !== false && repoSnapshot) {
    lines.push(formatRepoMetadata(repoSnapshot));
  }
  
  // Chat lines
  const formattedLines = chatLines
    .map(line => formatLine(line, { excludeThoughts }))
    .filter(Boolean);
  
  if (formattedLines.length > 0) {
    lines.push(...formattedLines);
  } else {
    lines.push('*Keine Chatnachrichten vorhanden*');
  }
  
  return lines.join('\n');
}

/**
 * Share chat via native share or fallback to clipboard
 */
export async function shareChatExport(exportedText: string): Promise<'shared' | 'copied' | 'failed'> {
  // Try native share if available
  if (typeof navigator !== 'undefined' && navigator.share) {
    try {
      await navigator.share({
        title: 'Sovereign Studio Chat',
        text: exportedText,
      });
      return 'shared';
    } catch (err) {
      // User cancelled or share failed, fall through to clipboard
      if ((err as Error).name === 'AbortError') {
        return 'failed';
      }
    }
  }
  
  // Fallback to clipboard
  if (typeof navigator !== 'undefined' && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(exportedText);
      return 'copied';
    } catch {
      return 'failed';
    }
  }
  
  return 'failed';
}

// ─────────────────────────────────────────────────────────────
// Phase 2: Session History Design (documented future extension)
// ─────────────────────────────────────────────────────────────
//
// Expected index key pattern: `session:${sessionId}`
// Validation rules:
//   - sessionId must be non-empty alphanumeric string
//   - Timestamp must be valid ISO date
//   - repoSnapshot must have required fields: name, url
//   - Token must never be stored
//
// Session switching requirements:
//   - Must be explicit user action
//   - Must preserve current repoSnapshot
//   - Must preserve token in memory (not localStorage)
//   - Must clear chat lines but not runtime state
//
// This requires a safe gateway contract before implementation.

export default { exportChatHistory, shareChatExport };
