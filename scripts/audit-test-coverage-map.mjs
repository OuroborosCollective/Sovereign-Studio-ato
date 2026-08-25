#!/usr/bin/env node
/**
 * audit-test-coverage-map.mjs
 *
 * Befund G (Audit 2026-07-02): Map every test file in the repo to the
 * package.json scripts and GitHub CI workflows that include it.
 *
 * Output format: JSON report written to generated/test-coverage-map.json
 * and a human-readable summary printed to stdout.
 *
 * Usage:
 *   node scripts/audit-test-coverage-map.mjs
 *   node scripts/audit-test-coverage-map.mjs --json   (suppress stdout, only file)
 */

import { readFileSync, readdirSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join, relative } from 'path';
import { fileURLToPath } from 'url';

const ROOT = join(fileURLToPath(import.meta.url), '..', '..');
const jsonOnly = process.argv.includes('--json');

// ─── Collect test files ────────────────────────────────────────────────────

const SKIPPED_DIRECTORIES = new Set([
  '.git', '.gradle', '.idea', '.mypy_cache', '.nox', '.pytest_cache',
  '.ruff_cache', '.sovereign-artifacts', '.tox', '.venv', '__pycache__',
  'build', 'coverage', 'dist', 'env', 'generated', 'node_modules', 'vendor', 'venv',
]);
const JAVASCRIPT_TEST_PATTERN = /\.(?:test|spec)\.(?:[cm]?[jt]sx?)$/i;
const TEST_FILE_PATTERNS = [
  JAVASCRIPT_TEST_PATTERN,
  /(?:^|\/)test_[^/]+\.py$/i,
  /(?:^|\/)[^/]+_test\.py$/i,
  /(?:^|\/)[^/]+_test\.go$/i,
  /(?:^|\/)[^/]+(?:Test|Tests)\.(?:java|kt|kts)$/,
  /(?:^|\/)test_[^/]+\.(?:sh|bash|c|cc|cpp)$/i,
];
const PLAYWRIGHT_TEST_ROOTS = ['tests/e2e/'];

function normalizePath(filePath) {
  return filePath.replaceAll('\\', '/');
}

function isTestFile(filePath) {
  const normalized = normalizePath(filePath);
  return TEST_FILE_PATTERNS.some((pattern) => pattern.test(normalized))
    || (normalized.includes('/tests/') && normalized.endsWith('.rs'));
}

function walkRepository(dir = ROOT, result = []) {
  if (!existsSync(dir)) return result;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) continue;
    if (entry.isDirectory() && SKIPPED_DIRECTORIES.has(entry.name)) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      walkRepository(full, result);
      continue;
    }
    if (!entry.isFile()) continue;
    const repositoryPath = normalizePath(relative(ROOT, full));
    if (isTestFile(repositoryPath)) result.push(repositoryPath);
  }
  return result;
}

function testLanguage(filePath) {
  if (/\.py$/i.test(filePath)) return 'python';
  if (/\.(?:[cm]?[jt]sx?)$/i.test(filePath)) return 'javascript-typescript';
  if (/\.(?:java|kt|kts)$/i.test(filePath)) return 'android-jvm';
  if (/\.go$/i.test(filePath)) return 'go';
  if (/\.rs$/i.test(filePath)) return 'rust';
  if (/\.(?:sh|bash)$/i.test(filePath)) return 'shell';
  if (/\.(?:c|cc|cpp)$/i.test(filePath)) return 'native';
  return 'unknown';
}

function testRoot(filePath) {
  const parts = normalizePath(filePath).split('/');
  const marker = parts.findIndex((part) => ['tests', 'test', 'androidTest', 'e2e'].includes(part));
  if (marker >= 0) {
    const includeNestedE2E = parts[marker] === 'tests' && parts[marker + 1] === 'e2e';
    return parts.slice(0, marker + (includeNestedE2E ? 2 : 1)).join('/');
  }
  return parts[0] || '.';
}

function isE2ETest(filePath) {
  const normalized = normalizePath(filePath);
  return normalized.startsWith('tests/e2e/')
    || normalized.includes('/e2e/')
    || normalized.includes('/androidTest/');
}

function isPlaywrightTest(filePath) {
  const normalized = normalizePath(filePath);
  return PLAYWRIGHT_TEST_ROOTS.some((root) => normalized.startsWith(root));
}

function isVitestCandidate(filePath) {
  return JAVASCRIPT_TEST_PATTERN.test(filePath)
    && !isE2ETest(filePath)
    && (filePath.startsWith('src/') || filePath.startsWith('scripts/'));
}

const allTests = [...new Set(walkRepository())].sort();

// ─── Parse package.json scripts ───────────────────────────────────────────

const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
const scripts = pkg.scripts ?? {};

const GATE_PATTERNS = {
  'test:smoke': {
    description: 'Smoke gate (excludes chat/integration/e2e)',
    excludes: [
      '**/*.chat.test.ts',
      '**/*.integration.test.ts',
      '**/*.e2e.test.ts',
      '**/*.spec.ts',
      '**/*.sequential.test.ts',
      '**/ChatSidebar.test.tsx',
      '**/e2e/**',
      '**/api-fallback/**',
    ],
  },
  'test:integration': {
    description: 'Integration gate (specific files only)',
    includes: [
      'src/features/product/components/ChatSidebar.test.tsx',
      'src/features/product/hooks/useProductMagic.sequential.test.ts',
      'src/features/product/runtime/sequentialRuntimeGuard.test.ts',
      'src/features/github/gitPatchRuntime.test.ts',
      'src/features/product/runtime/agentWorkRuntime.test.ts',
      'src/features/product/runtime/agentWorkspaceRuntime.test.ts',
    ],
  },
  'test:all': {
    description: 'All vitest tests',
    includes: null,
  },
  'test:release-gate': {
    description: 'Release gate = smoke + integration',
    delegates: ['test:smoke', 'test:integration'],
  },
  verify: {
    description: 'Full verify = type-check + release-gate + build + e2e + audit',
    delegates: ['test:release-gate'],
    includesE2E: true,
  },
};

function matchesPattern(filePath, pattern) {
  // '**' alone — match everything
  if (pattern === '**') return true;
  // '**/dir/**' — file is somewhere inside that directory
  if (pattern.startsWith('**/') && pattern.endsWith('/**')) {
    const dir = pattern.slice(3, -3);
    return filePath.includes('/' + dir + '/') || filePath.startsWith(dir + '/');
  }
  // 'prefix/**' — file is under that prefix
  if (pattern.endsWith('/**')) {
    const prefix = pattern.slice(0, -3);
    return filePath.startsWith(prefix + '/') || filePath === prefix;
  }
  // legacy: bare trailing '**' (should not appear in our patterns, but keep safe)
  if (pattern.endsWith('**')) {
    const prefix = pattern.slice(0, -2);
    return filePath.startsWith(prefix);
  }
  // '**/suffix' — file path ends with that suffix (anywhere in tree)
  if (pattern.startsWith('**/')) {
    const suffix = pattern.slice(3);
    return filePath.endsWith(suffix) || filePath.includes('/' + suffix);
  }
  if (pattern.includes('**/')) {
    const parts = pattern.split('**/');
    return filePath.includes(parts[parts.length - 1]);
  }
  return filePath === pattern || filePath.endsWith('/' + pattern);
}

function fileInGate(file, gateKey, visited = new Set()) {
  if (visited.has(gateKey)) return false;
  visited.add(gateKey);
  const gate = GATE_PATTERNS[gateKey];
  if (!gate) return false;

  if (gate.delegates) {
    return gate.delegates.some(d => fileInGate(file, d, visited));
  }

  if (gate.includes === null) return true;

  if (gate.includes) {
    return gate.includes.some(p => matchesPattern(file, p));
  }

  if (gate.excludes) {
    const excluded = gate.excludes.some(p => matchesPattern(file, p));
    return !excluded;
  }

  return false;
}

// ─── Parse CI workflow files ───────────────────────────────────────────────

const ciDir = join(ROOT, '.github', 'workflows');
const ciWorkflows = [];

function extractWorkflowRunCommands(content) {
  const lines = content.split(/\r?\n/);
  const commands = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].match(/^(\s*)run:\s*(.*)$/);
    if (!match) continue;
    const baseIndent = match[1].length;
    const inline = match[2].trim();
    if (inline && !/^[|>][-+0-9]*$/.test(inline)) {
      commands.push(inline.replace(/^(['"])([\s\S]*)\1$/, '$2'));
      continue;
    }

    const block = [];
    let cursor = index + 1;
    for (; cursor < lines.length; cursor += 1) {
      const line = lines[cursor];
      if (!line.trim()) {
        block.push(line);
        continue;
      }
      const indent = line.match(/^\s*/)?.[0].length ?? 0;
      if (indent <= baseIndent) break;
      block.push(line);
    }
    const contentIndents = block
      .filter((line) => line.trim())
      .map((line) => line.match(/^\s*/)?.[0].length ?? 0);
    const trimIndent = contentIndents.length > 0 ? Math.min(...contentIndents) : baseIndent + 2;
    commands.push(block.map((line) => line.slice(Math.min(trimIndent, line.length))).join('\n'));
    index = cursor - 1;
  }
  return commands;
}

function shellTokens(value) {
  return (value.match(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s]+/g) ?? [])
    .map((token) => token.replace(/^(['"])([\s\S]*)\1$/, '$2'));
}

function stripShellHereDocuments(command) {
  const executableLines = [];
  let delimiter = null;
  for (const line of command.split(/\r?\n/)) {
    if (delimiter !== null) {
      if (line.trim() === delimiter) delimiter = null;
      continue;
    }
    executableLines.push(line);
    const match = line.match(/<<-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1/);
    if (match) delimiter = match[2];
  }
  return executableLines.join('\n');
}

function logicalShellCommands(command) {
  return stripShellHereDocuments(command)
    .replace(/\\\r?\n/g, ' ')
    .split(/\r?\n|&&|\|\||;/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function extractInvokedPackageScripts(commands) {
  const invoked = [];
  for (const command of commands) {
    for (let logicalCommand of logicalShellCommands(command)) {
      logicalCommand = logicalCommand
        .replace(/^env\s+/, '')
        .replace(/^(?:(?:[A-Za-z_][A-Za-z0-9_]*)=(?:"[^"]*"|'[^']*'|\S+)\s+)*/, '');
      const match = logicalCommand.match(/^pnpm(?:\s+run)?\s+(test[:\w-]*|verify[:\w-]*)\b/);
      if (match) invoked.push(match[1]);
    }
  }
  return [...new Set(invoked)];
}

const RUNNER_OPTIONS_WITH_VALUE = new Set([
  '-c', '-k', '-m', '-n', '-o',
  '--basetemp', '--capture', '--color', '--config', '--confcutdir', '--cov',
  '--cov-config', '--cov-fail-under', '--cov-report', '--deselect', '--durations',
  '--exclude', '--html', '--ignore', '--import-mode', '--junit-prefix', '--junitxml',
  '--log-cli-level', '--log-file', '--log-file-level', '--log-level', '--maxfail',
  '--outputFile', '--override-ini', '--project', '--reporter', '--rootdir',
  '--tb', '--testNamePattern', '--timeout', '--workers',
]);

function normalizeRunnerTarget(rawTarget) {
  let target = rawTarget.trim().replace(/[),]+$/, '');
  target = target.replace(/^\$\{?GITHUB_WORKSPACE\}?\//, '');
  target = target.split('::', 1)[0];
  target = normalizePath(target).replace(/^\.\//, '').replace(/\/$/, '');
  if (
    !target
    || target === '.'
    || target.startsWith('-')
    || target.startsWith('$')
    || target.startsWith('/')
    || target.startsWith('~')
    || /^(?:then|do|done|fi|true|false)$/i.test(target)
    || /^(?:[012]?>|[012]?>&)/.test(target)
  ) return null;
  return target;
}

function runnerTargetsFromTail(tail) {
  const commandTail = tail.split(/\s+\|\s+/, 1)[0];
  const tokens = shellTokens(commandTail);
  const targets = [];
  let skipNext = false;
  for (const token of tokens) {
    if (skipNext) {
      skipNext = false;
      continue;
    }
    const option = token.split('=', 1)[0];
    if (RUNNER_OPTIONS_WITH_VALUE.has(option) && !token.includes('=')) {
      skipNext = true;
      continue;
    }
    if (token.startsWith('-') || token.includes('=')) continue;
    const target = normalizeRunnerTarget(token);
    if (target) targets.push(target);
  }
  return targets;
}

function extractWorkflowTestTargets(commands) {
  const targets = [];
  for (const command of commands) {
    for (let logicalCommand of logicalShellCommands(command)) {
      logicalCommand = logicalCommand
        .replace(/^env\s+/, '')
        .replace(/^(?:(?:[A-Za-z_][A-Za-z0-9_]*)=(?:"[^"]*"|'[^']*'|\S+)\s+)*/, '');
      let match = logicalCommand.match(/^(?:(?:python|python3)(?:\.\d+)?\s+-m\s+)?pytest\b([\s\S]*)$/);
      if (match) {
        for (const target of runnerTargetsFromTail(match[1])) targets.push({ language: 'python', target });
        continue;
      }
      match = logicalCommand.match(/^(?:python|python3)(?:\.\d+)?\s+-m\s+unittest\b([\s\S]*)$/);
      if (match) {
        for (const target of runnerTargetsFromTail(match[1])) targets.push({ language: 'python', target });
        continue;
      }
      match = logicalCommand.match(/^(?:(?:pnpm\s+(?:exec\s+)?)|(?:npx\s+))?vitest(?:\s+run)?\b([\s\S]*)$/);
      if (match) {
        for (const target of runnerTargetsFromTail(match[1])) targets.push({ language: 'javascript-typescript', target });
        continue;
      }
      match = logicalCommand.match(/^node\s+--test\b([\s\S]*)$/);
      if (match) {
        for (const target of runnerTargetsFromTail(match[1])) targets.push({ language: 'javascript-typescript', target });
        continue;
      }
      match = logicalCommand.match(/^(?:(?:pnpm\s+(?:exec\s+)?)|(?:npx\s+))?playwright\s+test\b([\s\S]*)$/);
      if (match) {
        const explicitTargets = runnerTargetsFromTail(match[1]);
        const playwrightTargets = explicitTargets.length > 0
          ? explicitTargets
          : PLAYWRIGHT_TEST_ROOTS.map((root) => root.replace(/\/$/, ''));
        for (const target of playwrightTargets) {
          targets.push({ language: 'javascript-typescript', target });
        }
      }
    }
  }
  return [...new Map(targets.map((entry) => [`${entry.language}:${entry.target}`, entry])).values()];
}

function collectPackageScriptCommands(scriptName, visited = new Set()) {
  if (visited.has(scriptName)) return [];
  visited.add(scriptName);
  const definition = scripts[scriptName];
  if (typeof definition !== 'string' || !definition.trim()) return [];
  const delegatedScripts = extractInvokedPackageScripts([definition]);
  return [
    definition,
    ...delegatedScripts.flatMap((delegated) => collectPackageScriptCommands(delegated, visited)),
  ];
}

function scriptGateKeys(scriptName, visited = new Set()) {
  if (visited.has(scriptName)) return [];
  visited.add(scriptName);
  const gateKeys = GATE_PATTERNS[scriptName] ? [scriptName] : [];
  const definition = scripts[scriptName];
  if (typeof definition !== 'string') return gateKeys;
  const delegatedScripts = extractInvokedPackageScripts([definition]);
  return [
    ...gateKeys,
    ...delegatedScripts.flatMap((delegated) => scriptGateKeys(delegated, visited)),
  ];
}

if (existsSync(ciDir)) {
  for (const f of readdirSync(ciDir)) {
    if (f.endsWith('.yml') || f.endsWith('.yaml')) {
      const content = readFileSync(join(ciDir, f), 'utf8');
      const runCommands = extractWorkflowRunCommands(content);
      const workflowScripts = extractInvokedPackageScripts(runCommands);
      const packageCommands = workflowScripts.flatMap((script) => collectPackageScriptCommands(script));
      ciWorkflows.push({
        file: f,
        scripts: workflowScripts,
        testTargets: extractWorkflowTestTargets([...runCommands, ...packageCommands]),
      });
    }
  }
}

function runnerTargetCoversFile(target, file) {
  if (target.includes('*')) {
    const sentinel = '\u0000';
    const expression = target
      .replace(/[.+?^${}()|[\]\\]/g, '\\$&')
      .replaceAll('**', sentinel)
      .replaceAll('*', '[^/]*')
      .replaceAll(sentinel, '.*');
    return new RegExp(`^${expression}$`).test(file);
  }
  return file === target || file.startsWith(`${target}/`);
}

function workflowCoversFile(workflow, file, gates) {
  if (workflow.scripts.some((script) => scriptGateKeys(script).some((gate) => gates.includes(gate)))) return true;
  const language = testLanguage(file);
  return workflow.testTargets.some((entry) => (
    entry.language === language && runnerTargetCoversFile(entry.target, file)
  ));
}

// ─── Classify each test file ───────────────────────────────────────────────

const gateKeys = Object.keys(GATE_PATTERNS);
const files = allTests.map((file) => {
  const gates = isVitestCandidate(file) ? gateKeys.filter((gate) => fileInGate(file, gate)) : [];
  if (isPlaywrightTest(file) && !gates.includes('verify')) gates.push('verify');
  const ciCoverage = ciWorkflows
    .filter((workflow) => workflowCoversFile(workflow, file, gates))
    .map((workflow) => workflow.file)
    .sort();
  const language = testLanguage(file);
  let category = 'not-in-any-gate';
  if (isE2ETest(file)) category = 'e2e';
  else if (language === 'python') category = 'python-suite';
  else if (language === 'android-jvm') category = 'android-suite';
  else if (gates.includes('test:smoke') || gates.includes('test:integration')) category = 'release-gate';
  else if (gates.includes('test:all') || gates.includes('verify')) category = 'verify-only';
  else if (ciCoverage.length > 0) category = 'ci-only';
  return {
    file,
    language,
    testRoot: testRoot(file),
    gates,
    ciWorkflows: ciCoverage,
    category,
  };
});

const rootCounts = new Map();
for (const entry of files) rootCounts.set(entry.testRoot, (rootCounts.get(entry.testRoot) ?? 0) + 1);
const report = {
  schemaVersion: 'sovereign.test-coverage-map.v2',
  generatedAt: new Date().toISOString(),
  discovery: {
    scope: 'tracked repository test conventions',
    excludedDirectories: [...SKIPPED_DIRECTORIES].sort(),
    representativeRoots: ['src', 'backend/tests', 'scripts/tests', 'tests/e2e'],
  },
  totalTestFiles: files.length,
  testRoots: Object.fromEntries([...rootCounts.entries()].sort(([left], [right]) => left.localeCompare(right))),
  files,
};

// ─── Summary ──────────────────────────────────────────────────────────────

const byCategory = report.files.reduce((categories, file) => {
  (categories[file.category] ??= []).push(file);
  return categories;
}, {});

// ─── Write output ─────────────────────────────────────────────────────────

mkdirSync(join(ROOT, 'generated'), { recursive: true });
const outPath = join(ROOT, 'generated', 'test-coverage-map.json');
writeFileSync(outPath, JSON.stringify(report, null, 2), 'utf8');

if (!jsonOnly) {
  console.log('\n=== Test Gate Coverage Map ===\n');
  console.log(`Total test files: ${report.totalTestFiles}`);
  console.log(`  Release gate (smoke + integration): ${(byCategory['release-gate'] ?? []).length}`);
  console.log(`  Verify-only (not in release gate):  ${(byCategory['verify-only'] ?? []).length}`);
  console.log(`  Python suites:                      ${(byCategory['python-suite'] ?? []).length}`);
  console.log(`  Android/JVM suites:                 ${(byCategory['android-suite'] ?? []).length}`);
  console.log(`  E2E suites:                         ${(byCategory.e2e ?? []).length}`);
  console.log(`  CI-only suites:                     ${(byCategory['ci-only'] ?? []).length}`);
  console.log(`  Not in any inferred gate:           ${(byCategory['not-in-any-gate'] ?? []).length}`);

  if ((byCategory['not-in-any-gate'] ?? []).length > 0) {
    console.log('\n⚠️  Files NOT in any inferred gate:');
    for (const f of byCategory['not-in-any-gate'] ?? []) {
      console.log(`  - ${f.file}`);
    }
  }

  if (ciWorkflows.length > 0) {
    console.log('\nCI workflows detected:');
    for (const w of ciWorkflows) {
      console.log(`  - ${w.file}: ${w.scripts.join(', ') || '(no test scripts)'}`);
    }
  } else {
    console.log('\n⚠️  No CI workflows found in .github/workflows/');
  }

  console.log(`\nFull report written to: ${outPath}\n`);
}
