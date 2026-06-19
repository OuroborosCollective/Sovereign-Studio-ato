#!/usr/bin/env node
/**
 * Hardcode & Logic Scanner
 * Scans source files for hardcoded values, credentials, magic numbers,
 * and logic issues that could impact functions, UI/UX, or other parts.
 */

import { readFileSync, readdirSync } from 'fs';
import { join } from 'path';
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

function formatReport(findings) {
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
  
  if (findings.length === 0) {
    console.log('✅ No hardcoded values or logic issues detected!\n');
    return { errors: 0, warnings: 0, info: 0, findings: [] };
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
    findings
  };
}

// Export for use in GitHub Actions
export function runScan(scanPath = 'src') {
  console.log(`Scanning directory: ${scanPath}...\n`);
  const findings = scanDirectory(scanPath);
  return formatReport(findings);
}

// Run if called directly
const scanPath = process.argv[2] || 'src';
const result = runScan(scanPath);

// Exit with error code if errors found
process.exit(result.errors > 0 ? 1 : 0);
