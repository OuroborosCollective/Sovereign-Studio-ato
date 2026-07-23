/** Pure DOM-geometry helpers for real chat scroll state. */
export const SCROLL_LOCK_THRESHOLD_PX = 80;
export function isNearBottom(node: { scrollTop: number; scrollHeight: number; clientHeight: number }, thresholdPx = SCROLL_LOCK_THRESHOLD_PX): boolean { return node.scrollHeight - node.scrollTop - node.clientHeight <= thresholdPx; }
export function shouldAutoScroll(isLocked: boolean): boolean { return !isLocked; }
export function shouldShowUnreadBadge(isLocked: boolean, hasUnread: boolean): boolean { return isLocked && hasUnread; }
