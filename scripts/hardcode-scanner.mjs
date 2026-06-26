#!/usr/bin/env node
/**
 * Hardcode & Logic Scanner
 * Scans source files for hardcoded values, credentials, magic numbers,
 * and logic issues that could impact functions, UI/UX, or other parts.
 * 
 * Usage:
 *   node hardcode-scanner.mjs [path1] [path2] ...  # Scan specific paths
 *   node hardcode-scanner.mjs --all               # Scan all project paths
 *   node hardcode-scanner.mjs src                  # Scan single path (backward compatible)
 */

import { readFileSync, readdirSync, statSync } from 'fs';
import { join, resolve } from 'path';
import { existsSync } from 'fs';

const SCAN_PATTERNS = {
  // Critical: Hardcoded credentials/secrets (ERROR level)
  credentials: [
    { regex: /(api[_-]?key|token|password|secret|auth|private[_-]?key)\s*[:=]\s*['"][a-zA-Z0-9_.-]{8,}['"]/gi, type: 'HARDCODED_CREDENTIAL', severity: 'ERROR', suggestion: 'Use environment variables: process.env.API_KEY' },
    { regex: /gh[pousr]_[a-zA-Z0-9_]{36,}/g, type: 'GITHUB_TOKEN', severity: 'ERROR', suggestion: 'Use GitHub Secrets for authentication' },
    { regex: /(mongodb|postgres|mysql|redis|sql):\/\/[^@]+@/g, type: 'DB_CONNECTION', severity: 'ERROR', suggestion: 'Use environment variables for database connection strings' },
    { regex: /sk-[a-zA-Z0-9_]{20,}/g, type: 'OPENAI_KEY', severity: 'ERROR', suggestion: 'Use environment variables: process.env.OPENAI_API_KEY' },
    { regex: /AIza[a-zA-Z0-9_-]{35}/g, type: 'GOOGLE_API_KEY', severity: 'ERROR', suggestion: 'Use environment variables: process.env.GOOGLE_API_KEY' },
  ],
  // High: Hardcoded URLs and endpoints
  urls: [
    { regex: /https?:\/\/[a-zA-Z0-9.-]+\.(com|io|org|net|dev|app)\/[^\s'"`]+/g, type: 'HARDCODED_URL', severity: 'WARNING', suggestion: 'Use environment-specific configuration' },
  ],
  // Medium: Magic numbers
  magic: [
    { regex: /(setTimeout|setInterval|delay|timeout)\s*\(\s*\w+\s*,\s*([0-9]{5,})/g, type: 'MAGIC_TIMEOUT', severity: 'WARNING', suggestion: 'Extract to named constant: const LONG_TIMEOUT = 60000' },
    { regex: /timeout\s*[:=]\s*([0-9]{5,})/g, type: 'MAGIC_TIMEOUT', severity: 'WARNING', suggestion: 'Use a named timeout constant' },
    { regex: /\b(86400000|3600000|600000)\b/g, type: 'MAGIC_TIME', severity: 'WARNING', suggestion: 'Use time constants: const DAY_MS = 86400000' },
  ],
  // Console output
  debug: [
    { regex: /console\.(log|debug|info|warn|error)\s*\(/g, type: 'CONSOLE_OUTPUT', severity: 'INFO', suggestion: 'Remove or use proper telemetry logging' },
    { regex: /debugger\s*;/g, type: 'DEBUGGER', severity: 'WARNING', suggestion: 'Remove debugger statements' },
  ],
  // Unresolved issues
  issues: [
    { regex: /(TODO|FIXME|HACK|XXX|BUG)\s*:\s*.{20,}/g, type: 'UNRESOLVED_ISSUE', severity: 'INFO', suggestion: 'Address this issue or create tracking ticket' },
  ],
};

// Default paths for all-scope scanning (runtime, mobile, mesh, and worker paths)
const DEFAULT_SCAN_PATHS = [
  'src',
  'sovereign-studio-rn/src',
  'mesh-system',
  'cloudflare-worker/src',
  'ato-v2',
  'scripts',
  'brain',
];

const SKIP_PATHS = ['node_modules', 'dist', '.git', '.next', 'build', '.cache', 'coverage'];
const SKIP_FILES = ['.test.', '.spec.', '.d.ts', '.min.js', '.bundle.js'];

function shouldSkip(filePath) {
  for (const skip of SKIP_PATHS) {
    if (filePath.includes(skip)) return true;
  }
  for (const skip of SKIP_FILES) {
    if (filePath.includes(skip)) return true;
  }
  return false;
}

function scanFile(filePath, content) {
  const findings = [];
  const lines = content.split('\n');
  
  for (const [category, patterns] of Object.entries(SCAN_PATTERNS)) {
    for (const pattern of patterns) {
      // Reset regex
      pattern.regex.lastIndex = 0;
      
      lines.forEach((line, index) => {
        const matches = line.matchAll(new RegExp(pattern.regex.source, pattern.regex.flags));
        
        for (const match of matches) {
          // Skip if it's already using env var
          if (match[0] && (line.includes('process.env') || line.includes('VITE_') || line.includes('import.meta.env') || line.includes('example') || line.includes('sample') || line.includes('test'))) {
            continue;
          }
          
          findings.push({
            file: filePath,
            line: index + 1,
            column: match.index || 0,
            type: pattern.type,
            severity: pattern.severity,
            message: match[0],
            suggestion: pattern.suggestion,
            category,
          });
        }
      });
    }
  }
  
  return findings;
}

function scanDirectory(dirPath, allFindings = []) {
  if (!existsSync(dirPath)) return allFindings;
  
  // Handle single file path
  const stat = statSync(dirPath);
  if (stat.isFile()) {
    if (shouldSkip(dirPath)) return allFindings;
    if (/\.(ts|tsx|js|jsx|mjs)$/.test(dirPath)) {
      try {
        const content = readFileSync(dirPath, 'utf-8');
        const findings = scanFile(dirPath, content);
        allFindings.push(...findings);
      } catch (err) {
        // Skip files that can't be read
      }
    }
    return allFindings;
  }
  
  const entries = readdirSync(dirPath, { withFileTypes: true });
  
  for (const entry of entries) {
    const fullPath = join(dirPath, entry.name);
    const relativePath = fullPath;
    
    if (entry.isDirectory()) {
      if (!SKIP_PATHS.some(skip => entry.name.includes(skip))) {
        scanDirectory(fullPath, allFindings);
      }
    } else if (entry.isFile() && /\.(ts|tsx|js|jsx|mjs)$/.test(entry.name)) {
      if (shouldSkip(relativePath)) continue;
      
      try {
        const content = readFileSync(fullPath, 'utf-8');
        const findings = scanFile(relativePath, content);
        allFindings.push(...findings);
      } catch (err) {
        // Skip files that can't be read
      }
    }
  }
  
  return allFindings;
}

function formatReport(findings, scannedPaths = []) {
  const errors = findings.filter(f => f.severity === 'ERROR');
  const warnings = findings.filter(f => f.severity === 'WARNING');
  const info = findings.filter(f => f.severity === 'INFO');
  
  const byFile = {};
  for (const finding of findings) {
    if (!byFile[finding.file]) byFile[finding.file] = [];
    byFile[finding.file].push(finding);
  }
  
  console.log('\n╔══════════════════════════════════════════════════════════════════╗');
  console.log('║          🔍 HARDCODED VALUE & LOGIC SCAN REPORT                ║');
  console.log('╚══════════════════════════════════════════════════════════════════╝\n');
  
  // Show scanned paths if available
  if (scannedPaths.length > 0) {
    console.log('📁 Validated paths:');
    for (const p of scannedPaths) {
      console.log(`   • ${p}`);
    }
    console.log('');
  }
  
  if (findings.length === 0) {
    console.log('✅ No hardcoded values or logic issues detected!\n');
    return { errors: 0, warnings: 0, info: 0, findings: [], scannedPaths };
  }
  
  console.log(`📊 Summary: ${errors.length} errors | ${warnings.length} warnings | ${info.length} info\n`);
  
  if (errors.length > 0) {
    console.log('❌ ERRORS (must fix):\n');
    for (const finding of errors) {
      console.log(`   [ERROR] ${finding.file}:${finding.line}:${finding.column}`);
      console.log(`           Type: ${finding.type}`);
      console.log(`           Found: ${finding.message.substring(0, 60)}${finding.message.length > 60 ? '...' : ''}`);
      console.log(`           Fix: ${finding.suggestion}`);
      console.log('');
    }
  }
  
  if (warnings.length > 0) {
    console.log('⚠️  WARNINGS (should fix):\n');
    for (const finding of warnings) {
      console.log(`   [WARNING] ${finding.file}:${finding.line}:${finding.column}`);
      console.log(`              Type: ${finding.type}`);
      console.log(`              Found: ${finding.message.substring(0, 60)}${finding.message.length > 60 ? '...' : ''}`);
      console.log(`              Fix: ${finding.suggestion}`);
      console.log('');
    }
  }
  
  if (info.length > 0) {
    console.log('ℹ️  INFO:\n');
    for (const finding of info.slice(0, 10)) {
      console.log(`   [INFO] ${finding.file}:${finding.line}`);
      console.log(`          Type: ${finding.type}`);
      console.log('');
    }
    if (info.length > 10) {
      console.log(`   ... and ${info.length - 10} more info items\n`);
    }
  }
  
  return {
    errors: errors.length,
    warnings: warnings.length,
    info: info.length,
    findings,
    scannedPaths
  };
}

const SAFE_SCAN_ROOT = resolve(process.cwd());

function resolveSafeScanPath(inputPath) {
  const resolvedPath = resolve(SAFE_SCAN_ROOT, inputPath);
  const normalizedRoot = SAFE_SCAN_ROOT.endsWith('/') ? SAFE_SCAN_ROOT : `${SAFE_SCAN_ROOT}/`;
  const normalizedPath = resolvedPath.endsWith('/') ? resolvedPath : `${resolvedPath}/`;

  if (resolvedPath !== SAFE_SCAN_ROOT && !normalizedPath.startsWith(normalizedRoot)) {
    return null;
  }

  return resolvedPath;
}

/**
 * Run scan on one or more paths
 * @param {string|string[]} scanPaths - Single path string, array of paths, or '--all' flag
 * @returns {Object} Scan results
 */
export function runScan(scanPaths = 'src') {
  let paths = [];
  
  // Handle --all flag
  if (scanPaths === '--all' || (Array.isArray(scanPaths) && scanPaths[0] === '--all')) {
    paths = DEFAULT_SCAN_PATHS;
    console.log(`\n🎯 All-scope audit mode: scanning ${paths.length} paths\n`);
    console.log('Scanned paths:');
    for (const p of paths) {
      console.log(`  • ${p}`);
    }
    console.log('');
  } else if (Array.isArray(scanPaths)) {
    paths = scanPaths;
  } else {
    paths = [scanPaths];
  }
  
  const rejectedPaths = [];
  const existingPaths = [];

  for (const p of paths) {
    const safePath = resolveSafeScanPath(p);
    if (!safePath) {
      rejectedPaths.push(p);
      continue;
    }
    if (existsSync(safePath)) {
      existingPaths.push(safePath);
    }
  }
  
  if (existingPaths.length === 0) {
    console.error(`\n❌ No valid paths to scan: ${paths.join(', ')}\n`);
    return { errors: 0, warnings: 0, info: 0, findings: [], scannedPaths: [] };
  }
  
  if (existingPaths.length < paths.length) {
    const missing = paths.filter(p => {
      const safePath = resolveSafeScanPath(p);
      return safePath && !existsSync(safePath);
    });
    if (missing.length > 0) {
      console.warn(`\n⚠️  Skipping non-existent paths: ${missing.join(', ')}\n`);
    }
  }

  if (rejectedPaths.length > 0) {
    console.warn(`\n⚠️  Skipping paths outside scan root (${SAFE_SCAN_ROOT}): ${rejectedPaths.join(', ')}\n`);
  }
  
  console.log(`\n🔍 Scanning ${existingPaths.length} path(s)...\n`);
  
  // Scan all paths
  let allFindings = [];
  for (const path of existingPaths) {
    console.log(`  → Scanning: ${path}`);
    const findings = scanDirectory(path);
    allFindings.push(...findings);
  }
  
  console.log(`\n✅ Scanned paths: ${existingPaths.join(', ')}`);
  
  return formatReport(allFindings, existingPaths);
}

// Export constants for external use
export { DEFAULT_SCAN_PATHS, SKIP_PATHS, SKIP_FILES };

// Only run main logic when executed directly (not imported as a module)
const isMainModule = import.meta.url === `file://${process.argv[1]}`;

if (isMainModule) {
  const args = process.argv.slice(2);
  let scanInput = args[0] || 'src';

  // Handle multiple paths (e.g., "node script.mjs src scripts")
  if (args.length > 1 && !args.includes('--all')) {
    scanInput = args;
  }

  // Handle --all flag
  if (args.includes('--all')) {
    scanInput = '--all';
  }

  const result = runScan(scanInput);

  // Exit with error code if errors found
  process.exit(result.errors > 0 ? 1 : 0);
}
