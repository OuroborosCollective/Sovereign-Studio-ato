import { existsSync, readFileSync } from 'node:fs';

const path = 'sovereign.guard.json';
if (!existsSync(path)) {
  console.error('[guard-config] missing sovereign.guard.json');
  process.exit(1);
}

const data = JSON.parse(readFileSync(path, 'utf8'));
const mustHave = ['audit:sovereign', 'type-check', 'test:run', 'build'];
const commands = Array.isArray(data.greenRequires) ? data.greenRequires : [];

let ok = true;
for (const command of mustHave) {
  if (!commands.includes(command)) {
    console.error(`[guard-config] missing command: ${command}`);
    ok = false;
  }
}

if (!String(data.automationRule || '').includes('complete-current-repository')) {
  console.error('[guard-config] automation rule must cover the complete current repository');
  ok = false;
}

if (!ok) process.exit(1);
console.log('[guard-config] ok');
