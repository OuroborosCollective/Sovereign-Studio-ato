# Freigabe Mobile UX Fix

## Problem

On mobile, the workflow could reach `Freigabe wartet`, but the user could lose the bottom action bar and only see the chat send icon. Pressing `Frei` or the blue send icon did not make the completion state obvious.

## Fix

- Restored mobile tabs by removing the hard `display: none` behavior.
- Added an explicit `approvalConfirmed` state.
- Added a large visible `Freigabe bestaetigen` card when the pipeline is green.
- Kept the bottom action bar sticky.
- Made the blue send button confirm approval when the pipeline is already green.
- Changed the final state text to tell the user they are done and no hidden send button is required.

## Expected mobile flow

1. Start Auftrag.
2. App switches to Live.
3. Agent plans, checks, fixes, rechecks.
4. When green, a large `Freigabe bestaetigen` button appears in the center.
5. Tapping it changes the state to `Freigabe bestaetigt` and logs completion.

This is intentionally simple enough for a non-technical user.
