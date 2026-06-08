import { cpSync, existsSync, rmSync, statSync } from 'node:fs';
import { resolve } from 'node:path';

const distDir = resolve('dist');
const androidPublicDir = resolve('android/app/src/main/assets/public');
const distIndex = resolve(distDir, 'index.html');

if (!existsSync(distIndex)) {
  console.error('[copy-dist-to-android] dist/index.html missing. Run vite build first.');
  process.exit(1);
}

if (existsSync(androidPublicDir)) {
  rmSync(androidPublicDir, { recursive: true, force: true });
}

cpSync(distDir, androidPublicDir, { recursive: true });

const copiedIndex = resolve(androidPublicDir, 'index.html');
if (!existsSync(copiedIndex) || !statSync(copiedIndex).isFile()) {
  console.error('[copy-dist-to-android] failed to copy Android index.');
  process.exit(1);
}

console.log('[copy-dist-to-android] copied real Vite dist into Android assets.');
