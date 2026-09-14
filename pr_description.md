**What:**
Fixed issue #557 ("ux(session): wiederhergestellte Session mit Alter sichtbar machen"). Redirected the session restoration notice from a generic `appendRuntimeNotice` text line into the chat feed using `appendChatLine` with a specific `id: 'system:restore-age'`.

**Why:**
The UI already had logic in `ChatSidebar.tsx` to detect messages with `id: 'system:restore-age'` and render them with a special distinct green styling (and a reload icon) rather than the default amber styling for normal system messages. However, `BuilderContainer.tsx` was just using `appendRuntimeNotice`, which couldn't supply the needed `id`.

**Impact:**
Users now clearly see when a session has been restored via a distinctly styled chat bubble, including its age, providing better visibility and UX context into the app's persistence state.

**Measurement:**
The automated unit test `ChatSidebar.test.tsx` (which explicitly checks for the `system:restore-age` functionality) along with the `BuilderContainer.test.tsx` suite and all smoke tests run and pass properly.
