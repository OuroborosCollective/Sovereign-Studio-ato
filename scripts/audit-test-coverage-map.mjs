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

import { readFileSync, readdirSync, statSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join, relative } from 'path';
import { fileURLToPath } from 'url';

const ROOT = join(fileURLToPath(import.meta.url), '..', '..');
const jsonOnly = process.argv.includes('--json');

// ─── Collect test files ────────────────────────────────────────────────────

function walk(dir, result = []) {
  if (!existsSync(dir)) return result;
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === 'dist' || entry === '.git') continue;
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      walk(full, result);
    } else if (
      entry.endsWith('.test.ts') ||
      entry.endsWith('.test.tsx') ||
      entry.endsWith('.spec.ts') ||
      entry.endsWith('.spec.tsx')
    ) {
      result.push(relative(ROOT, full));
    }
  }
  return result;
}

function walkE2E(dir, result = []) {
  if (!existsSync(dir)) return result;
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules') continue;
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      walkE2E(full, result);
    } else if (entry.endsWith('.mjs') || entry.endsWith('.ts')) {
      result.push(relative(ROOT, full));
    }
  }
  return result;
}

const allTests = walk(join(ROOT, 'src'));
const e2eTests = walkE2E(join(ROOT, 'scripts')).filter(f => f.includes('e2e') || f.includes('smoke'));

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
if (existsSync(ciDir)) {
  for (const f of readdirSync(ciDir)) {
    if (f.endsWith('.yml') || f.endsWith('.yaml')) {
      const content = readFileSync(join(ciDir, f), 'utf8');
      const scriptMatches = [...content.matchAll(/pnpm(?:\s+run)?\s+(test[:\w-]*|verify[:\w-]*)/g)].map(m => m[1]);
      ciWorkflows.push({ file: f, scripts: [...new Set(scriptMatches)] });
    }
  }
}

// ─── Classify each test file ───────────────────────────────────────────────

const report = {
  generatedAt: new Date().toISOString(),
  totalTestFiles: allTests.length + e2eTests.length,
  files: [],
};

const gateKeys = Object.keys(GATE_PATTERNS);

for (const file of allTests) {
  const gates = gateKeys.filter(g => fileInGate(file, g));
  const ciCoverage = ciWorkflows
    .filter(w => w.scripts.some(s => gates.includes(s)))
    .map(w => w.file);

  let category;
  if (gates.includes('test:smoke') || gates.includes('test:integration')) {
    category = 'release-gate';
  } else if (gates.includes('test:all') || gates.includes('verify')) {
    category = 'verify-only';
  } else {
    category = 'not-in-any-gate';
  }

  report.files.push({ file, gates, ciWorkflows: ciCoverage, category });
}

for (const file of e2eTests) {
  report.files.push({
    file,
    gates: ['verify'],
    ciWorkflows: ciWorkflows.filter(w => w.scripts.some(s => s.includes('e2e') || s === 'verify')).map(w => w.file),
    category: 'e2e',
  });
}

// ─── Summary ──────────────────────────────────────────────────────────────

const byCategory = {
  'release-gate': report.files.filter(f => f.category === 'release-gate'),
  'verify-only': report.files.filter(f => f.category === 'verify-only'),
  'e2e': report.files.filter(f => f.category === 'e2e'),
  'not-in-any-gate': report.files.filter(f => f.category === 'not-in-any-gate'),
};

// ─── Write output ─────────────────────────────────────────────────────────

mkdirSync(join(ROOT, 'generated'), { recursive: true });
const outPath = join(ROOT, 'generated', 'test-coverage-map.json');
writeFileSync(outPath, JSON.stringify(report, null, 2), 'utf8');

if (!jsonOnly) {
  console.log('\n=== Test Gate Coverage Map ===\n');
  console.log(`Total test files: ${report.totalTestFiles}`);
  console.log(`  Release gate (smoke + integration): ${byCategory['release-gate'].length}`);
  console.log(`  Verify-only (not in release gate):  ${byCategory['verify-only'].length}`);
  console.log(`  E2E / smoke scripts:                ${byCategory['e2e'].length}`);
  console.log(`  Not in any gate:                    ${byCategory['not-in-any-gate'].length}`);

  if (byCategory['not-in-any-gate'].length > 0) {
    console.log('\n⚠️  Files NOT in any gate:');
    for (const f of byCategory['not-in-any-gate']) {
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
