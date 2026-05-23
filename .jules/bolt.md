## 2026-05-19 - [Gemini 404 Fix & Key Setup UX]
**Learning:** Hardcoded model names in the frontend can lead to breaking changes if the provider (Google Gemini) retires or changes preview model strings. Always ensure fallback or stable model identifiers are used. Corrupted HTML at the end of files (stray braces/scripts) can break entire app execution and Capacitor syncs.
**Action:** Use stable model identifiers (e.g., `gemini-1.5-flash`) instead of dated previews. Implement automated UX prompts for missing API keys to reduce "Denkprozess Fehler" reports.
