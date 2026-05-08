# Technical Debt & Duplicate Logic

This document outlines the identified technical debt and duplicated logic within the repository.

## 1. Duplicate Application Logic

The repository currently contains two main application entry points that share significant functionality:
- `src/App.tsx`
- `src/ProductMagicApp.tsx`

**Analysis:**
Both files implement a complex UI involving file exploration, code editing (Monaco-style), and AI chat/agent interactions. However, `src/main.tsx` currently imports and renders `ProductMagicApp.tsx`, indicating it is likely the active version. `App.tsx` appears to be a legacy or alternative version of the same conceptual UI.

**Debt:**
- Maintaining two parallel monolithic components is error-prone.
- The files are excessively large (~680 lines for `App.tsx` and ~260 lines for `ProductMagicApp.tsx`) and contain mixed concerns (state management, UI rendering, complex business logic).

**Suggested Refactor:**
- Confirm if `src/App.tsx` is obsolete. If so, it should be deleted.
- Break down `src/ProductMagicApp.tsx` into smaller, feature-specific components (e.g., `EditorView`, `PipelineView`, `Sidebar`) and move them into `src/features/product/components/`.

## 2. Structural Inconsistencies

**Analysis:**
The project follows a feature-based architecture (as stated in `ONBOARDING.md`), where domains are separated into folders like `src/features/ai`. However, test files are sometimes placed outside these domains.

**Debt:**
- `src/services/ai/geminiService.test.ts` exists outside the `src/features/ai` directory where the actual `geminiService.ts` resides. This violates the co-location principle.

**Suggested Refactor:**
- Move `src/services/ai/geminiService.test.ts` to `src/features/ai/geminiService.test.ts`.

## 3. Test Setup and Build Issues

**Analysis:**
The testing framework (`vitest`) was failing to execute out of the box because a required peer dependency (`vite`) was missing from the `devDependencies` in `package.json`, despite being required by `@vitejs/plugin-react` which is used in `vitest.config.ts`.

**Debt:**
- Broken "out-of-the-box" developer experience.
- The `npm install` process required `--legacy-peer-deps` due to conflicts with Capacitor packages, indicating potential dependency resolution issues that need long-term addressing.

**Suggested Refactor:**
- Add `vite` to `devDependencies`.
- Resolve Capacitor peer dependency conflicts to allow standard `npm install`.
