import { describe, expect, it, vi } from 'vitest';
import {
  attemptClearClipboard,
  copyAndroidBubbleText,
  createAndroidFollowUpDraft,
  detectAndroidQuickRepoUrl,
  triggerAndroidHaptic,
} from './androidQuickInteractionRuntime';

describe('androidQuickInteractionRuntime', () => {
  it('recognizes one pasted GitHub repo URL and returns the local load hint', () => {
    const result = detectAndroidQuickRepoUrl('https://github.com/OuroborosCollective/Sovereign-Studio-ato');

    expect(result).toEqual({
      recognized: true,
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      hint: 'Repo erkannt · Laden',
    });
  });

  it('does not auto-detect multiline drafts or multiple URLs', () => {
    expect(detectAndroidQuickRepoUrl('https://github.com/a/b\nbitte laden').recognized).toBe(false);
    expect(detectAndroidQuickRepoUrl('https://github.com/a/b https://github.com/c/d').recognized).toBe(false);
  });

  it('creates a conscious follow-up draft from visible bubble text only', () => {
    expect(createAndroidFollowUpDraft('Bitte prüfen und erklären.')).toBe('"Bitte prüfen und erklären."\n\n');
    expect(createAndroidFollowUpDraft('')).toBe('');
  });

  it('copies visible bubble text when clipboard is available', async () => {
    const writeText = vi.fn(async () => undefined);
    await expect(copyAndroidBubbleText('Nur sichtbarer Text', { clipboard: { writeText } })).resolves.toEqual({ ok: true });
    expect(writeText).toHaveBeenCalledWith('Nur sichtbarer Text');
  });

  it('returns a bounded copy result when clipboard is unavailable or fails', async () => {
    await expect(copyAndroidBubbleText('Text', {})).resolves.toEqual({ ok: false, reason: 'clipboard_unavailable' });
    await expect(copyAndroidBubbleText('Text', { clipboard: { writeText: () => { throw new Error('blocked'); } } })).resolves.toEqual({ ok: false, reason: 'blocked' });
  });

  it('guards optional haptics and never throws when unsupported', () => {
    expect(triggerAndroidHaptic(undefined)).toBe(false);
    expect(triggerAndroidHaptic({})).toBe(false);

    const vibrate = vi.fn(() => true);
    expect(triggerAndroidHaptic({ vibrate }, 'medium')).toBe(true);
    expect(vibrate).toHaveBeenCalledWith(25);

    expect(triggerAndroidHaptic({ vibrate: () => { throw new Error('unsupported'); } }, 'heavy')).toBe(false);
  });

  describe('attemptClearClipboard', () => {
    it('reports unavailable when clipboard API is missing', async () => {
      const result = await attemptClearClipboard({});
      expect(result).toEqual({ available: false, cleared: false, reason: 'clipboard_unavailable' });
    });

    it('successfully clears clipboard when writeText is available and succeeds', async () => {
      const writeText = vi.fn(async () => undefined);
      const result = await attemptClearClipboard({ clipboard: { writeText } });
      expect(result).toEqual({ available: true, cleared: true });
      expect(writeText).toHaveBeenCalledWith('');
    });

    it('reports failure honestly when clipboard write fails', async () => {
      const writeText = vi.fn(async () => { throw new Error('SecurityError'); });
      const result = await attemptClearClipboard({ clipboard: { writeText } });
      expect(result).toEqual({ available: true, cleared: false, reason: 'SecurityError' });
    });

    it('reports failure with default reason when error has no message', async () => {
      const writeText = vi.fn(async () => { throw new Error(); });
      const result = await attemptClearClipboard({ clipboard: { writeText } });
      expect(result).toEqual({ available: true, cleared: false, reason: 'clipboard_clear_failed' });
    });
  });
});
