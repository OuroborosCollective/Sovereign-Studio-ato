/**
 * Tests for hardcode-scanner.mjs
 * Tests multi-path scanning, all-scope mode, and skip logic
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readFileSync, writeFileSync, mkdirSync, rmSync } from 'fs';
import { join } from 'path';
import { existsSync } from 'fs';

// Test fixtures directory
const TEST_FIXTURES_DIR = join(process.cwd(), 'test-fixtures-hardcode');

// Create test fixtures
function createTestFixtures() {
  mkdirSync(TEST_FIXTURES_DIR, { recursive: true });
  
  // Test subdirectory with credential file (not using 'test' keyword to avoid scanner filtering)
  mkdirSync(join(TEST_FIXTURES_DIR, 'creds'), { recursive: true });
  writeFileSync(join(TEST_FIXTURES_DIR, 'creds', 'secrets.ts'), `
const config = {
  apiKey: "sk-test1234567890abcdefghijklmnop",
  secret: "supersecretpassword123"
};
`);

  // Test file with proper env usage (should not be flagged)
  mkdirSync(join(TEST_FIXTURES_DIR, 'config'), { recursive: true });
  writeFileSync(join(TEST_FIXTURES_DIR, 'config', 'env.ts'), `
const apiKey = process.env.API_KEY;
const config = { url: import.meta.env.VITE_API_URL };
`);

  // Test file with no issues
  mkdirSync(join(TEST_FIXTURES_DIR, 'utils'), { recursive: true });
  writeFileSync(join(TEST_FIXTURES_DIR, 'utils', 'helper.ts'), `
export function processData(data) {
  return data.map(item => item.id);
}
`);

  // Test file in node_modules (should be skipped)
  mkdirSync(join(TEST_FIXTURES_DIR, 'node_modules'), { recursive: true });
  writeFileSync(join(TEST_FIXTURES_DIR, 'node_modules', 'fake-lib.ts'), `
const apiKey = "sk-test1234567890abcdefghijklmnop";
`);

  // Test file in dist (should be skipped)
  mkdirSync(join(TEST_FIXTURES_DIR, 'dist'), { recursive: true });
  writeFileSync(join(TEST_FIXTURES_DIR, 'dist', 'bundle.js'), `
const apiKey = "sk-test1234567890abcdefghijklmnop";
`);

  // Test file in test dir (should be skipped)
  mkdirSync(join(TEST_FIXTURES_DIR, '__tests__'), { recursive: true });
  writeFileSync(join(TEST_FIXTURES_DIR, '__tests__', 'helper.spec.ts'), `
const apiKey = "sk-test1234567890abcdefghijklmnop";
`);

  // Test subdirectory for nested scanning
  mkdirSync(join(TEST_FIXTURES_DIR, 'db'), { recursive: true });
  writeFileSync(join(TEST_FIXTURES_DIR, 'db', 'connection.ts'), `
const dbUrl = "postgres://user:pass@localhost:5432/db";
`);

  // Test file with console.log (should be INFO)
  mkdirSync(join(TEST_FIXTURES_DIR, 'logs'), { recursive: true });
  writeFileSync(join(TEST_FIXTURES_DIR, 'logs', 'logger.ts'), `
console.log("Debug info");
console.warn("Warning");
`);

  // Test file with TODO (should be INFO)
  mkdirSync(join(TEST_FIXTURES_DIR, 'issues'), { recursive: true });
  writeFileSync(join(TEST_FIXTURES_DIR, 'issues', 'pending.ts'), `
function process() {
  // TODO: Implement proper validation logic here with more details
}
`);

  // Test file with magic number (should be WARNING)
  mkdirSync(join(TEST_FIXTURES_DIR, 'values'), { recursive: true });
  writeFileSync(join(TEST_FIXTURES_DIR, 'values', 'constants.ts'), `
const timeout = setTimeout(() => {}, 86400000);
const day = 86400000;
`);

  // Test file with hardcoded URL (should be WARNING)
  mkdirSync(join(TEST_FIXTURES_DIR, 'endpoints'), { recursive: true });
  writeFileSync(join(TEST_FIXTURES_DIR, 'endpoints', 'api.ts'), `
const apiUrl = "https://api.server.io/v1/users";
`);
}

// Cleanup test fixtures
function cleanupTestFixtures() {
  if (existsSync(TEST_FIXTURES_DIR)) {
    rmSync(TEST_FIXTURES_DIR, { recursive: true, force: true });
  }
}

// Import the scanner module (only exports, no execution)
import { runScan, DEFAULT_SCAN_PATHS, SKIP_PATHS, SKIP_FILES } from './hardcode-scanner.mjs';

describe('hardcode-scanner.mjs', () => {
  beforeEach(() => {
    createTestFixtures();
  });

  afterEach(() => {
    cleanupTestFixtures();
  });

  it('should detect hardcoded credentials', () => {
    const result = runScan(TEST_FIXTURES_DIR);
    
    const credentialFindings = result.findings?.filter(f => 
      f.type === 'HARDCODED_CREDENTIAL' || f.type === 'DB_CONNECTION'
    );
    expect(credentialFindings).toBeDefined();
    expect(credentialFindings?.length).toBeGreaterThan(0);
  });

  it('should skip files in node_modules', () => {
    const result = runScan(TEST_FIXTURES_DIR);
    
    const nodeModulesFindings = result.findings?.filter(f => f.file?.includes('node_modules'));
    expect(nodeModulesFindings?.length).toBe(0);
  });

  it('should skip files in dist directory', () => {
    const result = runScan(TEST_FIXTURES_DIR);
    
    const distFindings = result.findings?.filter(f => f.file?.includes('dist'));
    expect(distFindings?.length).toBe(0);
  });

  it('should skip test files', () => {
    const result = runScan(TEST_FIXTURES_DIR);
    
    const testFindings = result.findings?.filter(f => f.file?.includes('.test.') || f.file?.includes('.spec.'));
    expect(testFindings?.length).toBe(0);
  });

  it('should scan subdirectories', () => {
    const result = runScan(TEST_FIXTURES_DIR);
    
    const nestedFindings = result.findings?.filter(f => f.file?.includes('db'));
    expect(nestedFindings).toBeDefined();
  });

  it('should not flag process.env usage', () => {
    const result = runScan(join(TEST_FIXTURES_DIR, 'config'));
    
    // Should not flag env usage
    const envFindings = result.findings?.filter(f => 
      f.type === 'HARDCODED_CREDENTIAL'
    );
    expect(envFindings?.length).toBe(0);
  });

  it('should detect console.log as INFO', () => {
    const result = runScan(join(TEST_FIXTURES_DIR, 'logs'));
    
    const consoleFindings = result.findings?.filter(f => f.type === 'CONSOLE_OUTPUT');
    expect(consoleFindings).toBeDefined();
    expect(consoleFindings?.length).toBeGreaterThan(0);
    expect(consoleFindings?.[0].severity).toBe('INFO');
  });

  it('should detect TODO as INFO', () => {
    const result = runScan(join(TEST_FIXTURES_DIR, 'issues'));
    
    const todoFindings = result.findings?.filter(f => f.type === 'UNRESOLVED_ISSUE');
    expect(todoFindings).toBeDefined();
    expect(todoFindings?.length).toBeGreaterThan(0);
  });

  it('should detect magic numbers as WARNING', () => {
    const result = runScan(join(TEST_FIXTURES_DIR, 'values'));
    
    const magicFindings = result.findings?.filter(f => 
      f.type === 'MAGIC_TIME' || f.type === 'MAGIC_TIMEOUT'
    );
    expect(magicFindings).toBeDefined();
    expect(magicFindings?.length).toBeGreaterThan(0);
  });

  it('should detect hardcoded URLs as WARNING', () => {
    const result = runScan(join(TEST_FIXTURES_DIR, 'endpoints'));
    
    const urlFindings = result.findings?.filter(f => f.type === 'HARDCODED_URL');
    expect(urlFindings).toBeDefined();
    expect(urlFindings?.length).toBeGreaterThan(0);
    expect(urlFindings?.[0].severity).toBe('WARNING');
  });

  it('should return correct error count when hardcodes present', () => {
    const result = runScan(join(TEST_FIXTURES_DIR, 'creds'));
    
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
    const result = runScan([join(TEST_FIXTURES_DIR, 'creds'), join(TEST_FIXTURES_DIR, 'db')]);
    
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
    const result = runScan(join(TEST_FIXTURES_DIR, 'creds', 'secrets.ts'));
    
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
  });

  it('should have correct SKIP_FILES defined', () => {
    expect(SKIP_FILES).toContain('.test.');
    expect(SKIP_FILES).toContain('.spec.');
    expect(SKIP_FILES).toContain('.d.ts');
    expect(SKIP_FILES).toContain('.min.js');
    expect(SKIP_FILES).toContain('.bundle.js');
  });
});
