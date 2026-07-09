import { parseDevChatGithubUrl } from './devChatWorkerBridge';

export type AndroidHapticLevel = 'light' | 'medium' | 'heavy';

export interface AndroidQuickRepoDetection {
  readonly recognized: boolean;
  readonly hint: string;
  readonly repoUrl?: string;
}

export interface ClipboardLike {
  readonly writeText?: (text: string) => Promise<void> | void;
}

export interface NavigatorQuickInteractionLike {
  readonly clipboard?: ClipboardLike;
  readonly vibrate?: (pattern: number | number[]) => boolean | void;
}

const GITHUB_REPO_URL_PATTERN = /https?:\/\/github\.com\/[^\s/]+\/[^\s/#?]+(?:\.git)?(?:\/tree\/[^\s/#?]+)?(?:\/[^\s#?]*)?/gi;

function cleanGithubRepoUrl(value: string): string {
  return value.trim().replace(/[),.;]+$/g, '').replace(/\.git$/i, '');
}

export function detectAndroidQuickRepoUrl(draft: string): AndroidQuickRepoDetection {
  const clean = draft.trim();
  if (!clean || clean.includes('\n')) {
    return { recognized: false, hint: 'Worker Chat senden · Repo-URL laden · Sovereign Agent nur bei Code-Auftrag' };
  }

  const matches = Array.from(clean.matchAll(GITHUB_REPO_URL_PATTERN));
  if (matches.length !== 1) {
    return { recognized: false, hint: 'Worker Chat senden · Enter senden · Shift+Enter Zeilenumbruch' };
  }

  const repoUrl = cleanGithubRepoUrl(matches[0][0]);
  const parsed = parseDevChatGithubUrl(repoUrl);
  if (!parsed) {
    return { recognized: false, hint: 'Worker Chat senden · Enter senden · Shift+Enter Zeilenumbruch' };
  }

  return {
    recognized: true,
    repoUrl: parsed.repoUrl,
    hint: 'Repo erkannt · Laden',
  };
}

export function createAndroidFollowUpDraft(text: string, limit = 100): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (!clean) return '';
  const quote = clean.length > limit ? `${clean.slice(0, limit)}…` : clean;
  return `"${quote}"\n\n`;
}

export async function copyAndroidBubbleText(
  text: string,
  navigatorLike: NavigatorQuickInteractionLike | undefined,
): Promise<{ readonly ok: boolean; readonly reason?: string }> {
  const clean = text.trim();
  if (!clean) return { ok: false, reason: 'empty' };
  const writeText = navigatorLike?.clipboard?.writeText;
  if (typeof writeText !== 'function') return { ok: false, reason: 'clipboard_unavailable' };

  try {
    await writeText(clean);
    return { ok: true };
  } catch (error) {
    return { ok: false, reason: error instanceof Error ? error.message : 'clipboard_failed' };
  }
}

/**
 * Result of a clipboard clear attempt.
 * - available: true if the browser/environment supports clipboard clearing
 * - cleared: true only if we successfully wrote empty string to clipboard
 */
export interface ClipboardClearResult {
  readonly available: boolean;
  readonly cleared: boolean;
  readonly reason?: string;
}

/**
 * Attempt to clear the clipboard (e.g., after sensitive token was copied).
 * Reports availability and success honestly — no fake success.
 * 
 * On Android WebView, clipboard write may succeed silently but not actually clear
 * the clipboard due to security restrictions. This is reported transparently.
 */
export async function attemptClearClipboard(
  navigatorLike: NavigatorQuickInteractionLike | undefined = typeof navigator !== 'undefined' ? navigator : undefined,
): Promise<ClipboardClearResult> {
  const writeText = navigatorLike?.clipboard?.writeText;
  if (typeof writeText !== 'function') {
    return { available: false, cleared: false, reason: 'clipboard_unavailable' };
  }

  try {
    // Write empty string to attempt clear
    await writeText('');
    // Note: Even if writeText() succeeds, the actual clipboard state depends on
    // browser/Android WebView implementation. We report cleared=true because
    // the write operation succeeded, but acknowledge this may not work on all platforms.
    return { available: true, cleared: true };
  } catch (error) {
    // Clear failed — report honestly
    const message = error instanceof Error ? error.message : undefined;
    return {
      available: true,
      cleared: false,
      reason: (message && message.trim()) || 'clipboard_clear_failed',
    };
  }
}

export function triggerAndroidHaptic(
  navigatorLike: NavigatorQuickInteractionLike | undefined,
  level: AndroidHapticLevel = 'light',
): boolean {
  const vibrate = navigatorLike?.vibrate;
  if (typeof vibrate !== 'function') return false;
  const duration = level === 'light' ? 10 : level === 'medium' ? 25 : 50;
  try {
    vibrate(duration);
    return true;
  } catch {
    return false;
  }
}
