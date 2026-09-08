import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function runScanner({ summaryPath, runnerTemp }) {
  const env = { ...process.env };
  if (summaryPath === undefined) delete env.GITHUB_STEP_SUMMARY;
  else env.GITHUB_STEP_SUMMARY = summaryPath;
  if (runnerTemp === undefined) delete env.RUNNER_TEMP;
  else env.RUNNER_TEMP = runnerTemp;

  const result = spawnSync(process.execPath, ['scripts/sovereign-live-path-scan.mjs'], {
    cwd: repoRoot,
    env,
    encoding: 'utf8',
  });

  assert.equal(
    result.status,
    0,
    `scanner failed\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`,
  );
}

function tempRoot(name) {
  return fs.mkdtempSync(path.join(os.tmpdir(), `sovereign-summary-${name}-`));
}

function writeSentinel(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, 'sentinel\n');
}

test('writes only to a valid GitHub step summary under RUNNER_TEMP', () => {
  const runnerTemp = tempRoot('valid');
  const summaryPath = path.join(
    runnerTemp,
    '_runner_file_commands',
    'step_summary_123e4567-e89b-12d3-a456-426614174000',
  );
  writeSentinel(summaryPath);
  runScanner({ summaryPath, runnerTemp });
  assert.match(fs.readFileSync(summaryPath, 'utf8'), /## Sovereign Live Path Scan/);
});

test('rejects parent traversal outside RUNNER_TEMP', () => {
  const runnerTemp = tempRoot('parent');
  const summaryPath = path.resolve(runnerTemp, '..', 'step_summary_parent-escape');
  writeSentinel(summaryPath);
  runScanner({ summaryPath, runnerTemp });
  assert.equal(fs.readFileSync(summaryPath, 'utf8'), 'sentinel\n');
});

test('rejects sibling-prefix paths outside RUNNER_TEMP', () => {
  const parent = tempRoot('sibling');
  const runnerTemp = path.join(parent, 'runner');
  const summaryPath = path.join(parent, 'runner-evil', 'step_summary_sibling-escape');
  fs.mkdirSync(runnerTemp, { recursive: true });
  writeSentinel(summaryPath);
  runScanner({ summaryPath, runnerTemp });
  assert.equal(fs.readFileSync(summaryPath, 'utf8'), 'sentinel\n');
});

test('rejects an absolute foreign path', () => {
  const runnerTemp = tempRoot('foreign-runner');
  const foreignRoot = tempRoot('foreign-target');
  const summaryPath = path.join(foreignRoot, 'step_summary_absolute-foreign');
  writeSentinel(summaryPath);
  runScanner({ summaryPath, runnerTemp });
  assert.equal(fs.readFileSync(summaryPath, 'utf8'), 'sentinel\n');
});

test('rejects a wrong summary filename inside RUNNER_TEMP', () => {
  const runnerTemp = tempRoot('wrong-name');
  const summaryPath = path.join(runnerTemp, '_runner_file_commands', 'summary.md');
  writeSentinel(summaryPath);
  runScanner({ summaryPath, runnerTemp });
  assert.equal(fs.readFileSync(summaryPath, 'utf8'), 'sentinel\n');
});

test('rejects summary output when RUNNER_TEMP is missing', () => {
  const runnerTemp = tempRoot('missing-root');
  const summaryPath = path.join(runnerTemp, '_runner_file_commands', 'step_summary_missing-root');
  writeSentinel(summaryPath);
  runScanner({ summaryPath, runnerTemp: undefined });
  assert.equal(fs.readFileSync(summaryPath, 'utf8'), 'sentinel\n');
});
