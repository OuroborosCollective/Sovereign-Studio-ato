import { existsSync, readFileSync } from 'node:fs';

const required = [
  'package.json',
  'vite.config.ts',
  'AGENTS.md',
  'sovereign.guard.json',
  'src/main.tsx',
  'src/App.tsx',
  'android/app/src/main/assets/public/index.html',
];

let ok = true;

for (const file of required) {
  if (!existsSync(file)) {
    console.error(`[audit] missing: ${file}`);
    ok = false;
  }
}

if (existsSync('src/main.tsx')) {
  const main = readFileSync('src/main.tsx', 'utf8');
  if (!main.includes("import App from './App'")) {
    console.error('[audit] src/main.tsx must import the current App shell.');
    ok = false;
  }
  if (!main.includes('<App />')) {
    console.error('[audit] src/main.tsx must render the current App shell.');
    ok = false;
  }
}

if (!ok) process.exit(1);
console.log('[audit] Sovereign static audit passed.');
