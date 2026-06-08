#!/usr/bin/env node
/**
 * E2E Test Runner Script
 * Convenience script to run E2E tests with various options
 */

import { E2ERunner } from '../run-e2e';

const args = process.argv.slice(2);
const command = args[0] || 'all';

const commands: Record<string, { detox?: boolean; apiFallback?: boolean; selfHealing?: boolean; autoFix?: boolean; ci?: boolean }> = {
  'all': { detox: true, apiFallback: true, selfHealing: true, ci: true },
  'detox': { detox: true },
  'api': { apiFallback: true },
  'healing': { selfHealing: true },
  'fix': { autoFix: true },
  'ci': { detox: true, apiFallback: true, selfHealing: true, ci: true },
  'quick': { detox: true },
};

const config = commands[command] || commands['all'];

console.log(`🚀 Running E2E tests: ${command}`);
console.log('='.repeat(50));

const runner = new E2ERunner({ ...config, verbose: true });

runner.runAll()
  .then(success => {
    console.log('\n' + (success ? '✅ All tests passed!' : '❌ Some tests failed'));
    process.exit(success ? 0 : 1);
  })
  .catch(error => {
    console.error('\n❌ E2E Runner failed:', error);
    process.exit(1);
  });