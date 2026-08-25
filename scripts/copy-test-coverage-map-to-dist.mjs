#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const source = path.join(root, 'generated', 'test-coverage-map.json');
const targets = [
  path.join(root, 'dist', 'generated', 'test-coverage-map.json'),
];

if (!fs.existsSync(source) || !fs.statSync(source).isFile()) {
  throw new Error('generated/test-coverage-map.json is missing; run audit-test-coverage-map.mjs first.');
}

const raw = fs.readFileSync(source, 'utf8');
let parsed;
try {
  parsed = JSON.parse(raw);
} catch {
  throw new Error('generated/test-coverage-map.json is not valid JSON.');
}
if (!parsed || typeof parsed !== 'object' || !Number.isInteger(parsed.totalTestFiles) || !Array.isArray(parsed.files)) {
  throw new Error('generated/test-coverage-map.json does not satisfy the coverage-map contract.');
}

for (const target of targets) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, raw, 'utf8');
  const readback = fs.readFileSync(target, 'utf8');
  if (readback !== raw) throw new Error(`Coverage-map copy readback mismatch: ${target}`);
}

console.log(`Coverage map copied into release artifact (${parsed.totalTestFiles} test files).`);
