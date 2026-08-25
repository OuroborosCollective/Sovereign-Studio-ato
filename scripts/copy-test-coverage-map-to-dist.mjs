#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const source = path.join(root, 'generated', 'test-coverage-map.json');
const targets = [
  path.join(root, 'dist', 'generated', 'test-coverage-map.json'),
];

// CodeQL #646: validate and read through one descriptor so no path-based
// check-then-use window exists between the file type check and the read.
let sourceFd;
let raw;
try {
  sourceFd = fs.openSync(
    source,
    fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0),
  );
  const sourceStat = fs.fstatSync(sourceFd);
  if (!sourceStat.isFile()) {
    throw new Error('generated/test-coverage-map.json is not a regular file.');
  }
  raw = fs.readFileSync(sourceFd, 'utf8');
} catch (error) {
  if (error instanceof Error && error.message.includes('not a regular file')) throw error;
  throw new Error('generated/test-coverage-map.json is missing or unsafe; run audit-test-coverage-map.mjs first.');
} finally {
  if (sourceFd !== undefined) fs.closeSync(sourceFd);
}
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
  const temporaryTarget = `${target}.tmp-${process.pid}`;
  try {
    fs.writeFileSync(temporaryTarget, raw, { encoding: 'utf8', flag: 'wx' });
    fs.renameSync(temporaryTarget, target);
  } finally {
    try {
      fs.unlinkSync(temporaryTarget);
    } catch (error) {
      if (!(error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT')) throw error;
    }
  }
  const readback = fs.readFileSync(target, 'utf8');
  if (readback !== raw) throw new Error(`Coverage-map copy readback mismatch: ${target}`);
}

console.log(`Coverage map copied into release artifact (${parsed.totalTestFiles} test files).`);
