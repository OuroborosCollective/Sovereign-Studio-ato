---
name: Sovereign Launcher system architecture
description: How the Launcher feature (Issues #451-#455, #460) is structured and how to add new tools.
---

## Structure

- `src/features/launcher/launcherRegistry.ts` — **only file to edit when adding a tool**. LAUNCHER_REGISTRY is an array of `LauncherEntry` objects.
- `src/features/launcher/components/LauncherMenu.tsx` — bottom-sheet grid overlay, opens on `useLauncherStore.openMenu()`.
- `src/features/launcher/components/LauncherWindowHost.tsx` — renders floating windows for open tools.
- `src/features/launcher/components/LauncherTaskbar.tsx` — horizontal chip strip above composer showing minimized/open tools.
- `src/features/launcher/LauncherContext.tsx` — `LauncherProvider` wraps LauncherMenu + LauncherWindowHost inside BuilderContainer's `<section>`.
- `src/features/launcher/tools/<tool-name>/` — each tool is self-contained. Exports a `LauncherEntry` from `index.ts`.

## Adding a tool

1. Create `src/features/launcher/tools/<name>/index.ts` exporting a `LauncherEntry`.
2. Import and add to `LAUNCHER_REGISTRY` in `launcherRegistry.ts`.
3. No changes to BuilderContainer needed.

## Trigger path

`SovereignToolLauncher` ("+" button) → "Alle Tools" item → `useLauncherStore.getState().openMenu()` → `isMenuOpen = true` → `LauncherMenu` renders.

## VPS tool

Currently `disabled: true` (security, Issue #454) — remove `disabled` to re-enable after hardening.

**Why:** LauncherProvider must wrap LauncherMenu + LauncherWindowHost as siblings inside the JSX tree (not outside `<section>`). BuilderContainer uses a React Fragment to make auth modals siblings of `<section>` while keeping LauncherProvider inside it.
