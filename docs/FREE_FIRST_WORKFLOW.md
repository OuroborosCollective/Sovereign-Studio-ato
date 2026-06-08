# Sovereign Studio Free-First Workflow

Sovereign Studio must remain useful without an AI key.

## Runtime priority

1. Start the UI instantly.
2. Keep the NoCode ideas factory usable offline or with demo data.
3. Try no-key provider routes before optional user-owned keys.
4. Keep GitHub repository actions separated from AI provider actions.
5. Show every generated patch in the editor before push or merge.

## Provider route

Preferred free route:

- mlvoca
- Pollinations
- optional user-owned Gemini/Groq/OpenRouter/etc. key

A missing AI key is not a boot error. It is only a quality/performance limitation.

## GitHub workflow

- Public repo browsing can work without a token.
- Private repo reading or pushing needs a GitHub PAT.
- Push and merge should stay reviewable.
- Failed validation should return to a visible editor patch loop.

## Android boot rule

The WebView must never remain stuck on a static loader. If React does not mount, the HTML fallback must show a recovery panel with build instructions.
