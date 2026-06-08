/**
 * E2E Test Runner
 * Orchestrates all E2E tests: Detox, API Fallback, Self-Healing, Auto-Fix
 */

import { spawn } from 'child_process';
import { existsSync } from 'fs';
import path from 'path';

interface TestConfig {
  detox: boolean;
  apiFallback: boolean;
  selfHealing: boolean;
  autoFix: boolean;
  ci: boolean;
  verbose: boolean;
}

interface TestResult {
  suite: string;
  success: boolean;
  duration: number;
  output: string;
  errors: string[];
}

class E2ERunner {
  private config: TestConfig;
  private results: TestResult[] = [];
  private startTime: number;

  constructor(config: Partial<TestConfig> = {}) {
    this.config = {
      detox: true,
      apiFallback: true,
      selfHealing: true,
      autoFix: false,
      ci: false,
      verbose: true,
      ...config,
    };
    this.startTime = Date.now();
  }

  async runAll(): Promise<boolean> {
    console.log('🚀 Starting E2E Test Suite');
    console.log('='.repeat(60));
    console.log(`Detox: ${this.config.detox ? '✓' : '✗'}`);
    console.log(`API Fallback: ${this.config.apiFallback ? '✓' : '✗'}`);
    console.log(`Self-Healing: ${this.config.selfHealing ? '✓' : '✗'}`);
    console.log(`Auto-Fix: ${this.config.autoFix ? '✓' : '✗'}`);
    console.log(`CI Mode: ${this.config.ci ? '✓' : '✗'}`);
    console.log('='.repeat(60));

    const testResults: boolean[] = [];

    if (this.config.detox) {
      testResults.push(await this.runDetox());
    }

    if (this.config.apiFallback) {
      testResults.push(await this.runApiFallback());
    }

    if (this.config.selfHealing) {
      testResults.push(await this.runSelfHealing());
    }

    if (this.config.autoFix) {
      testResults.push(await this.runAutoFix());
    }

    const allPassed = testResults.every(r => r);
    this.printSummary();

    return allPassed;
  }

  private async runDetox(): Promise<boolean> {
    console.log('\n🎯 Running Detox E2E Tests...');
    const startTime = Date.now();
    
    try {
      // Check if Detox is configured
      const detoxConfig = path.join(process.cwd(), 'e2e/config/detox.config.ts');
      
      if (!existsSync(detoxConfig)) {
        console.log('⚠️ Detox config not found, skipping...');
        return true;
      }

      await this.runCommand('npx', [
        'detox',
        'test',
        '--configuration',
        'android.debug',
        ...(this.config.ci ? ['--record-logs', 'failing'] : []),
      ]);

      this.results.push({
        suite: 'Detox E2E',
        success: true,
        duration: Date.now() - startTime,
        output: 'All Detox tests passed',
        errors: [],
      });

      return true;
    } catch (error) {
      const output = error instanceof Error ? error.message : String(error);
      
      this.results.push({
        suite: 'Detox E2E',
        success: false,
        duration: Date.now() - startTime,
        output: output,
        errors: this.parseErrors(output),
      });

      if (this.config.autoFix) {
        console.log('🔄 Triggering Auto-Fix for Detox failures...');
        await this.triggerAutoFix('detox');
      }

      return false;
    }
  }

  private async runApiFallback(): Promise<boolean> {
    console.log('\n🔄 Running API Fallback Tests...');
    const startTime = Date.now();
    
    try {
      await this.runCommand('npx', [
        'jest',
        '--config',
        'e2e/api-fallback/jest.config.js',
        '--testPathPattern',
        'api-fallback.spec.ts',
      ]);

      this.results.push({
        suite: 'API Fallback',
        success: true,
        duration: Date.now() - startTime,
        output: 'All API fallback tests passed',
        errors: [],
      });

      return true;
    } catch (error) {
      const output = error instanceof Error ? error.message : String(error);
      
      this.results.push({
        suite: 'API Fallback',
        success: false,
        duration: Date.now() - startTime,
        output: output,
        errors: this.parseErrors(output),
      });

      return false;
    }
  }

  private async runSelfHealing(): Promise<boolean> {
    console.log('\n🧹 Running Self-Healing Tests...');
    const startTime = Date.now();
    
    try {
      await this.runCommand('npx', [
        'jest',
        '--config',
        'e2e/self-healing/jest.config.js',
        '--testPathPattern',
        'self-healing.spec.ts',
      ]);

      this.results.push({
        suite: 'Self-Healing',
        success: true,
        duration: Date.now() - startTime,
        output: 'All self-healing tests passed',
        errors: [],
      });

      return true;
    } catch (error) {
      const output = error instanceof Error ? error.message : String(error);
      
      this.results.push({
        suite: 'Self-Healing',
        success: false,
        duration: Date.now() - startTime,
        output: output,
        errors: this.parseErrors(output),
      });

      return false;
    }
  }

  private async runAutoFix(): Promise<boolean> {
    console.log('\n🔧 Running Auto-Fix Loop...');
    const startTime = Date.now();
    
    try {
      await this.runCommand('npx', [
        'ts-node',
        'e2e/auto-fix/auto-fix-loop.ts',
        '--max=5',
        '--verbose',
      ]);

      this.results.push({
        suite: 'Auto-Fix',
        success: true,
        duration: Date.now() - startTime,
        output: 'Auto-fix completed successfully',
        errors: [],
      });

      return true;
    } catch (error) {
      const output = error instanceof Error ? error.message : String(error);
      
      this.results.push({
        suite: 'Auto-Fix',
        success: false,
        duration: Date.now() - startTime,
        output: output,
        errors: this.parseErrors(output),
      });

      return false;
    }
  }

  private async triggerAutoFix(suite: string): Promise<void> {
    console.log(`\n🔄 Triggering auto-fix for ${suite}...`);
    
    try {
      await this.runCommand('npx', [
        'ts-node',
        'e2e/auto-fix/auto-fix-loop.ts',
        '--max=3',
        '--test=detox',
      ]);
    } catch (error) {
      console.log(`❌ Auto-fix failed: ${error}`);
    }
  }

  private runCommand(cmd: string, args: string[]): Promise<string> {
    return new Promise((resolve, reject) => {
      const proc = spawn(cmd, args, {
        stdio: this.config.verbose ? 'inherit' : ['pipe', 'pipe', 'pipe'],
        shell: true,
        env: { ...process.env, FORCE_COLOR: 'true' },
      });

      let output = '';
      
      if (proc.stdout) {
        proc.stdout.on('data', (data) => {
          output += data.toString();
          if (this.config.verbose) {
            process.stdout.write(data);
          }
        });
      }

      if (proc.stderr) {
        proc.stderr.on('data', (data) => {
          output += data.toString();
          if (this.config.verbose) {
            process.stderr.write(data);
          }
        });
      }

      proc.on('close', (code) => {
        if (code === 0) {
          resolve(output);
        } else {
          reject(new Error(output || `Command failed with exit code ${code}`));
        }
      });

      proc.on('error', reject);
    });
  }

  private parseErrors(output: string): string[] {
    const errors: string[] = [];
    const lines = output.split('\n');
    
    for (const line of lines) {
      if (line.includes('Error:') || line.includes('FAIL') || line.includes('✕')) {
        errors.push(line.trim());
      }
    }
    
    return errors;
  }

  private printSummary(): void {
    const totalTime = Date.now() - this.startTime;
    
    console.log('\n' + '='.repeat(60));
    console.log('📊 E2E Test Summary');
    console.log('='.repeat(60));
    console.log(`Total Duration: ${(totalTime / 1000).toFixed(1)}s`);
    console.log('\nResults:');
    
    for (const result of this.results) {
      const icon = result.success ? '✅' : '❌';
      const duration = (result.duration / 1000).toFixed(1);
      console.log(`  ${icon} ${result.suite}: ${duration}s`);
      
      if (result.errors.length > 0 && this.config.verbose) {
        console.log(`     Errors: ${result.errors.length}`);
        result.errors.slice(0, 3).forEach(e => console.log(`       - ${e}`));
      }
    }

    const passedCount = this.results.filter(r => r.success).length;
    const totalCount = this.results.length;
    
    console.log('\n' + '-'.repeat(60));
    console.log(`Total: ${passedCount}/${totalCount} test suites passed`);
    console.log('='.repeat(60));

    // Generate report for CI
    if (this.config.ci) {
      this.generateCIReport();
    }
  }

  private generateCIReport(): void {
    const report = {
      timestamp: new Date().toISOString(),
      duration: Date.now() - this.startTime,
      results: this.results.map(r => ({
        suite: r.suite,
        success: r.success,
        duration: r.duration,
        errors: r.errors,
      })),
      allPassed: this.results.every(r => r.success),
    };

    console.log('\n📄 CI Report:');
    console.log(JSON.stringify(report, null, 2));
  }

  getResults(): TestResult[] {
    return this.results;
  }
}

export default E2ERunner;

// CLI Interface
if (require.main === module) {
  const args = process.argv.slice(2);
  const config: Partial<TestConfig> = {
    detox: !args.includes('--skip-detox'),
    apiFallback: !args.includes('--skip-api'),
    selfHealing: !args.includes('--skip-healing'),
    autoFix: args.includes('--auto-fix'),
    ci: args.includes('--ci'),
    verbose: !args.includes('--quiet'),
  };

  const runner = new E2ERunner(config);
  
  runner.runAll().then(success => {
    console.log('\n' + (success ? '✅ All tests passed!' : '❌ Some tests failed'));
    process.exit(success ? 0 : 1);
  }).catch(error => {
    console.error('❌ E2E Runner failed:', error);
    process.exit(1);
  });
}