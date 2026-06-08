import { existsSync } from 'node:fs';

const required = [
  'package.json',
  'vite.config.ts',
  'src/ProductMagicApp.tsx',
  'src/features/product/freeFirstPlan.ts',
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
