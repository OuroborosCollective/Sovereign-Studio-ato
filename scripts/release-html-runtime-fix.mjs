import { existsSync, statSync } from 'node:fs';
import { resolve } from 'node:path';

// Build output validation - verifies the Vite + React build produced correct artifacts
const distIndex = resolve('dist/index.html');
const distAssets = resolve('dist/assets');

if (!existsSync(distIndex)) {
  console.error('[build-validate] dist/index.html not found. Build may have failed.');
  process.exit(1);
}

if (!existsSync(distAssets)) {
  console.error('[build-validate] dist/assets/ not found. Vite did not produce JS bundles.');
  process.exit(1);
}

const htmlSize = statSync(distIndex).size;
if (htmlSize > 50000) {
  console.warn(`[build-validate] dist/index.html is ${htmlSize} bytes — may still contain old canvas artifact. Check index.html in repo root.`);
}

console.log('[build-validate] Build artifacts OK. React app will be used for Capacitor Android.');
console.log(`[build-validate] dist/index.html: ${htmlSize} bytes`);
