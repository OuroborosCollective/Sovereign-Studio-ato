import { existsSync } from 'node:fs';

const required = [
  'package.json',
  'vite.config.ts',
  'src/ProductMagicApp.tsx',
  'src/features/product/freeFirstPlan.ts',
  'src/features/product/visiblePatch.ts',
  'src/features/product/githubWriteGuard.ts',
  'src/features/product/userFlow.ts',
  'src/features/product/flowMessages.ts',
  'src/features/product/autoModePolicy.ts',
  'src/features/product/workflowAnalysis.ts',
  'docs/FREE_FIRST_WORKFLOW.md',
  'android/app/src/main/assets/public/index.html',
];

let ok = true;
for (const file of required) {
  if (!existsSync(file)) {
    console.error(`[audit] missing: ${file}`);
    ok = false;
  }
}

if (!ok) process.exit(1);
console.log('[audit] Sovereign static audit passed.');
