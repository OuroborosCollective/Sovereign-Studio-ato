import { describe, expect, it } from 'vitest';
import { isNearBottom, SCROLL_LOCK_THRESHOLD_PX, shouldAutoScroll, shouldShowUnreadBadge } from './scrollLockBehavior';

describe('scrollLockBehavior', () => {
  it('recognizes the exact bottom', () => expect(isNearBottom({ scrollTop: 900, scrollHeight: 1000, clientHeight: 100 })).toBe(true));
  it('uses the configured threshold', () => expect(isNearBottom({ scrollTop: 820, scrollHeight: 1000, clientHeight: 100 })).toBe(true));
  it('locks when farther than the threshold', () => expect(isNearBottom({ scrollTop: 819, scrollHeight: 1000, clientHeight: 100 })).toBe(false));
  it('accepts a custom threshold', () => expect(isNearBottom({ scrollTop: 850, scrollHeight: 1000, clientHeight: 100 }, 49)).toBe(false));
  it('has a touch-friendly default threshold', () => expect(SCROLL_LOCK_THRESHOLD_PX).toBe(80));
  it('auto-scrolls only when unlocked', () => { expect(shouldAutoScroll(false)).toBe(true); expect(shouldAutoScroll(true)).toBe(false); });
  it('shows unread badge only when locked with unread activity', () => { expect(shouldShowUnreadBadge(true, true)).toBe(true); expect(shouldShowUnreadBadge(false, true)).toBe(false); expect(shouldShowUnreadBadge(true, false)).toBe(false); });
});
