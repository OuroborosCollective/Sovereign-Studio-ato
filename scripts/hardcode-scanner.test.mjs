/**
 * Tests for hardcode-scanner.mjs
 * Tests multi-path scanning, all-scope mode, and skip logic
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { readFileSync, writeFileSync, mkdirSync, rmSync } from 'fs';
import { join } from 'path';
import { existsSync } from 'fs';

// Create test fixtures in a temp directory with a unique name
const TEST_DIR_PREFIX = 'hardcode-test-fixtures-';
let TEST_DIR = '';

// Create test fixtures
function createTestFixtures() {
  TEST_DIR = join(process.cwd(), TEST_DIR_PREFIX + Date.now());
  mkdirSync(TEST_DIR, { recursive: true });

  // Test subdirectory with credential file
  mkdirSync(join(TEST_DIR, 'creds'), { recursive: true });
  writeFileSync(join(TEST_DIR, 'creds', 'secrets.ts'), `
const config = {
  apiKey: "sk-test1234567890abcdefghijklmnop",
  secret: "supersecretpassword123"
};
`);

  // Test file with proper env usage (should not be flagged)
  mkdirSync(join(TEST_DIR, 'config'), { recursive: true });
  writeFileSync(join(TEST_DIR, 'config', 'env.ts'), `
const apiKey = process.env.API_KEY;
const config = { url: import.meta.env.VITE_API_URL };
`);

  // Test file with no issues
  mkdirSync(join(TEST_DIR, 'utils'), { recursive: true });
  writeFileSync(join(TEST_DIR, 'utils', 'helper.ts'), `
export function processData(data) {
  return data.map(item => item.id);
}
`);

  // Test file in node_modules (should be skipped)
  mkdirSync(join(TEST_DIR, 'node_modules'), { recursive: true });
  writeFileSync(join(TEST_DIR, 'node_modules', 'fake-lib.ts'), `
const apiKey = "sk-test1234567890abcdefghijklmnop";
`);

  // Test file in dist (should be skipped)
  mkdirSync(join(TEST_DIR, 'dist'), { recursive: true });
  writeFileSync(join(TEST_DIR, 'dist', 'bundle.js'), `
const apiKey = "sk-test1234567890abcdefghijklmnop";
`);

  // Test file in test dir (should be skipped)
  mkdirSync(join(TEST_DIR, '__tests__'), { recursive: true });
  writeFileSync(join(TEST_DIR, '__tests__', 'helper.spec.ts'), `
const apiKey = "sk-test1234567890abcdefghijklmnop";
`);

  // Test subdirectory for nested scanning
  mkdirSync(join(TEST_DIR, 'db'), { recursive: true });
  writeFileSync(join(TEST_DIR, 'db', 'connection.ts'), `
const dbUrl = "postgres://user:pass@localhost:5432/db";
`);

  // Test file with console.log (should be INFO)
  mkdirSync(join(TEST_DIR, 'logs'), { recursive: true });
  writeFileSync(join(TEST_DIR, 'logs', 'logger.ts'), `
console.log("Debug info");
console.warn("Warning");
`);

  // Test file with TODO (should be INFO)
  mkdirSync(join(TEST_DIR, 'issues'), { recursive: true });
  writeFileSync(join(TEST_DIR, 'issues', 'pending.ts'), `
function process() {
  // TODO: Implement proper validation logic here with more details
}
`);

  // Test file with magic number (should be WARNING)
  mkdirSync(join(TEST_DIR, 'values'), { recursive: true });
  writeFileSync(join(TEST_DIR, 'values', 'constants.ts'), `
const timeout = setTimeout(() => {}, 86400000);
const day = 86400000;
`);

  // Test file with hardcoded URL (should be WARNING)
  mkdirSync(join(TEST_DIR, 'endpoints'), { recursive: true });
  writeFileSync(join(TEST_DIR, 'endpoints', 'api.ts'), `
const apiUrl = "https://api.server.io/v1/users";
`);

  return TEST_DIR;
}

// Cleanup test fixtures
function cleanupTestFixtures() {
  if (TEST_DIR && existsSync(TEST_DIR)) {
    rmSync(TEST_DIR, { recursive: true, force: true });
  }
  // Also cleanup any leftover test dirs
  try {
    const entries = require('fs').readdirSync(process.cwd());
    for (const entry of entries) {
      if (entry.startsWith(TEST_DIR_PREFIX) && entry !== TEST_DIR) {
        rmSync(join(process.cwd(), entry), { recursive: true, force: true });
      }
    }
  } catch (e) {
    // Ignore errors during cleanup
  }
}

// Import the scanner module
import { runScan, DEFAULT_SCAN_PATHS, SKIP_PATHS, SKIP_FILES } from './hardcode-scanner.mjs';

describe('hardcode-scanner.mjs', () => {
  let testDir;

  beforeEach(() => {
    testDir = createTestFixtures();
  });

  afterEach(() => {
    cleanupTestFixtures();
  });

  it('should detect hardcoded credentials', () => {
    const result = runScan(testDir);

    const credentialFindings = result.findings?.filter(f =>
      f.type === 'HARDCODED_CREDENTIAL' || f.type === 'DB_CONNECTION'
    );
    expect(credentialFindings).toBeDefined();
    expect(credentialFindings?.length).toBeGreaterThan(0);
  });

  it('should skip files in node_modules', () => {
    const result = runScan(testDir);

    const nodeModulesFindings = result.findings?.filter(f => f.file?.includes('node_modules'));
    expect(nodeModulesFindings?.length).toBe(0);
  });

  it('should skip files in dist directory', () => {
    const result = runScan(testDir);

    const distFindings = result.findings?.filter(f => f.file?.includes('dist'));
    expect(distFindings?.length).toBe(0);
  });

  it('should skip test files', () => {
    const result = runScan(testDir);

    const testFindings = result.findings?.filter(f => f.file?.includes('.test.') || f.file?.includes('.spec.'));
    expect(testFindings?.length).toBe(0);
  });

  it('should scan subdirectories', () => {
    const result = runScan(testDir);

    const nestedFindings = result.findings?.filter(f => f.file?.includes('db'));
    expect(nestedFindings).toBeDefined();
  });

  it('should not flag process.env usage', () => {
    const result = runScan(join(testDir, 'config'));

    // Should not flag env usage
    const envFindings = result.findings?.filter(f =>
      f.type === 'HARDCODED_CREDENTIAL'
    );
    expect(envFindings?.length).toBe(0);
  });

  it('should detect console.log as INFO', () => {
    const result = runScan(join(testDir, 'logs'));

    const consoleFindings = result.findings?.filter(f => f.type === 'CONSOLE_OUTPUT');
    expect(consoleFindings).toBeDefined();
    expect(consoleFindings?.length).toBeGreaterThan(0);
    expect(consoleFindings?.[0].severity).toBe('INFO');
  });

  it('should detect TODO as INFO', () => {
    const result = runScan(join(testDir, 'issues'));

    const todoFindings = result.findings?.filter(f => f.type === 'UNRESOLVED_ISSUE');
    expect(todoFindings).toBeDefined();
    expect(todoFindings?.length).toBeGreaterThan(0);
  });

  it('should detect magic numbers as WARNING', () => {
    const result = runScan(join(testDir, 'values'));

    const magicFindings = result.findings?.filter(f =>
      f.type === 'MAGIC_TIME' || f.type === 'MAGIC_TIMEOUT'
    );
    expect(magicFindings).toBeDefined();
    expect(magicFindings?.length).toBeGreaterThan(0);
  });

  it('should detect hardcoded URLs as WARNING', () => {
    const result = runScan(join(testDir, 'endpoints'));

    const urlFindings = result.findings?.filter(f => f.type === 'HARDCODED_URL');
    expect(urlFindings).toBeDefined();
    expect(urlFindings?.length).toBeGreaterThan(0);
    expect(urlFindings?.[0].severity).toBe('WARNING');
  });

  it('should return correct error count when hardcodes present', () => {
    const result = runScan(join(testDir, 'creds'));

    expect(result.errors).toBeGreaterThan(0);
  });

  it('should handle --all flag for all-scope scanning', () => {
    // The all-scope should use DEFAULT_SCAN_PATHS
    expect(DEFAULT_SCAN_PATHS).toBeDefined();
    expect(Array.isArray(DEFAULT_SCAN_PATHS)).toBe(true);
    expect(DEFAULT_SCAN_PATHS).toContain('src');
    expect(DEFAULT_SCAN_PATHS).toContain('sovereign-studio-rn/src');
    expect(DEFAULT_SCAN_PATHS).toContain('mesh-system');
    expect(DEFAULT_SCAN_PATHS).toContain('cloudflare-worker/src');
    expect(DEFAULT_SCAN_PATHS).toContain('ato-v2');
    expect(DEFAULT_SCAN_PATHS).toContain('scripts');
    expect(DEFAULT_SCAN_PATHS).toContain('brain');
  });

  it('should handle multiple paths argument', () => {
    // Scan multiple specific paths
    const result = runScan([join(testDir, 'creds'), join(testDir, 'db')]);

    expect(result.scannedPaths).toBeDefined();
    expect(result.scannedPaths.length).toBeGreaterThanOrEqual(2);
  });

  it('should return empty result for non-existent path', () => {
    const result = runScan('/non-existent-path-12345');

    expect(result.errors).toBe(0);
    expect(result.warnings).toBe(0);
    expect(result.findings).toBeDefined();
  });

  it('should handle single file path', () => {
    const result = runScan(join(testDir, 'creds', 'secrets.ts'));

    expect(result.scannedPaths).toBeDefined();
    expect(result.errors).toBeGreaterThan(0);
  });
});

describe('hardcode-scanner.mjs - Skip paths', () => {
  it('should have correct SKIP_PATHS defined', () => {
    expect(SKIP_PATHS).toContain('node_modules');
    expect(SKIP_PATHS).toContain('dist');
    expect(SKIP_PATHS).toContain('.git');
    expect(SKIP_PATHS).toContain('.next');
    expect(SKIP_PATHS).toContain('build');
    expect(SKIP_PATHS).toContain('.cache');
    expect(SKIP_PATHS).toContain('coverage');
    expect(SKIP_PATHS).toContain('test-fixtures');
    expect(SKIP_PATHS).toContain('test-fixtures-hardcode');
  });

  it('should have correct SKIP_FILES defined', () => {
    expect(SKIP_FILES).toContain('.test.');
    expect(SKIP_FILES).toContain('.spec.');
    expect(SKIP_FILES).toContain('.d.ts');
    expect(SKIP_FILES).toContain('.min.js');
    expect(SKIP_FILES).toContain('.bundle.js');
  });
});
