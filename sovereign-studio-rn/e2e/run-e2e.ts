/**
 * E2E Test Runner
 * Orchestrates E2E suites without fake-green results.
 * Missing optional suite configs are reported as SKIPPED, not passed.
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

type TestResultStatus = 'passed' | 'failed' | 'skipped';

interface TestResult {
  suite: string;
  status: TestResultStatus;
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

    if (this.config.detox) testResults.push(await this.runDetox());
    if (this.config.apiFallback) testResults.push(await this.runApiFallback());
    if (this.config.selfHealing) testResults.push(await this.runSelfHealing());
    if (this.config.autoFix) testResults.push(await this.runAutoFix());

    const allPassed = testResults.every((result) => result);
    this.printSummary();

    return allPassed;
  }

  private recordSkipped(suite: string, startTime: number, output: string): boolean {
    console.log(`⏭️ ${suite}: ${output}`);
    this.results.push({
      suite,
      status: 'skipped',
      success: true,
      duration: Date.now() - startTime,
      output,
      errors: [],
    });
    return true;
  }

  private recordPassed(suite: string, startTime: number, output: string): boolean {
    this.results.push({
      suite,
      status: 'passed',
      success: true,
      duration: Date.now() - startTime,
      output,
      errors: [],
    });
    return true;
  }

  private recordFailed(suite: string, startTime: number, error: unknown): boolean {
    const output = error instanceof Error ? error.message : String(error);
    this.results.push({
      suite,
      status: 'failed',
      success: false,
      duration: Date.now() - startTime,
      output,
      errors: this.parseErrors(output),
    });
    return false;
  }

  private async runDetox(): Promise<boolean> {
    console.log('\n🎯 Running Detox E2E Tests...');
    const startTime = Date.now();

    try {
      const detoxConfig = path.join(process.cwd(), 'sovereign-studio-rn/e2e/config/detox.config.ts');
      if (!existsSync(detoxConfig)) {
        return this.recordSkipped('Detox E2E', startTime, 'Detox config not found.');
      }

      await this.runCommand('pnpm', [
        'exec',
        'detox',
        'test',
        '--configuration',
        'android.debug',
        ...(this.config.ci ? ['--record-logs', 'failing'] : []),
      ]);

      return this.recordPassed('Detox E2E', startTime, 'All Detox tests passed');
    } catch (error) {
      const failed = this.recordFailed('Detox E2E', startTime, error);
      if (this.config.autoFix) {
        console.log('🔄 Triggering Auto-Fix for Detox failures...');
        await this.triggerAutoFix('detox');
      }
      return failed;
    }
  }

  private async runApiFallback(): Promise<boolean> {
    console.log('\n🔄 Running API Fallback Tests...');
    const startTime = Date.now();

    try {
      const configPath = 'sovereign-studio-rn/e2e/api-fallback/jest.config.js';
      const specPattern = 'api-fallback.spec.ts';
      if (!existsSync(path.join(process.cwd(), configPath))) {
        return this.recordSkipped('API Fallback', startTime, `${configPath} not found.`);
      }

      await this.runCommand('pnpm', [
        'exec',
        'jest',
        '--config',
        configPath,
        '--testPathPatterns',
        specPattern,
      ]);

      return this.recordPassed('API Fallback', startTime, 'All API fallback tests passed');
    } catch (error) {
      return this.recordFailed('API Fallback', startTime, error);
    }
  }

  private async runSelfHealing(): Promise<boolean> {
    console.log('\n🧹 Running Self-Healing Tests...');
    const startTime = Date.now();

    try {
      const configPath = 'sovereign-studio-rn/e2e/self-healing/jest.config.js';
      const specPattern = 'self-healing.spec.ts';
      if (!existsSync(path.join(process.cwd(), configPath))) {
        return this.recordSkipped('Self-Healing', startTime, `${configPath} not found.`);
      }

      await this.runCommand('pnpm', [
        'exec',
        'jest',
        '--config',
        configPath,
        '--testPathPatterns',
        specPattern,
      ]);

      return this.recordPassed('Self-Healing', startTime, 'All self-healing tests passed');
    } catch (error) {
      return this.recordFailed('Self-Healing', startTime, error);
    }
  }

  private async runAutoFix(): Promise<boolean> {
    console.log('\n🔧 Running Auto-Fix Loop...');
    const startTime = Date.now();

    try {
      const autoFixPath = 'sovereign-studio-rn/e2e/auto-fix/auto-fix-loop.ts';
      if (!existsSync(path.join(process.cwd(), autoFixPath))) {
        return this.recordSkipped('Auto-Fix', startTime, `${autoFixPath} not found.`);
      }

      await this.runCommand('pnpm', [
        'exec',
        'tsx',
        autoFixPath,
        '--max=5',
        '--verbose',
      ]);

      return this.recordPassed('Auto-Fix', startTime, 'Auto-fix completed successfully');
    } catch (error) {
      return this.recordFailed('Auto-Fix', startTime, error);
    }
  }

  private async triggerAutoFix(suite: string): Promise<void> {
    console.log(`\n🔄 Triggering auto-fix for ${suite}...`);

    try {
      const autoFixPath = 'sovereign-studio-rn/e2e/auto-fix/auto-fix-loop.ts';
      if (!existsSync(path.join(process.cwd(), autoFixPath))) {
        console.log(`⏭️ Auto-fix skipped: ${autoFixPath} not found.`);
        return;
      }

      await this.runCommand('pnpm', [
        'exec',
        'tsx',
        autoFixPath,
        '--max=3',
        `--test=${suite}`,
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
          if (this.config.verbose) process.stdout.write(data);
        });
      }

      if (proc.stderr) {
        proc.stderr.on('data', (data) => {
          output += data.toString();
          if (this.config.verbose) process.stderr.write(data);
        });
      }

      proc.on('close', (code) => {
        if (code === 0) resolve(output);
        else reject(new Error(output || `Command failed with exit code ${code}`));
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
      const icon = result.status === 'passed' ? '✅' : result.status === 'skipped' ? '⏭️' : '❌';
      const duration = (result.duration / 1000).toFixed(1);
      console.log(`  ${icon} ${result.suite}: ${result.status.toUpperCase()} (${duration}s)`);

      if (result.status === 'skipped') {
        console.log(`     ${result.output}`);
      }

      if (result.errors.length > 0 && this.config.verbose) {
        console.log(`     Errors: ${result.errors.length}`);
        result.errors.slice(0, 3).forEach((error) => console.log(`       - ${error}`));
      }
    }

    const passedCount = this.results.filter((result) => result.status === 'passed').length;
    const skippedCount = this.results.filter((result) => result.status === 'skipped').length;
    const failedCount = this.results.filter((result) => result.status === 'failed').length;
    const totalCount = this.results.length;

    console.log('\n' + '-'.repeat(60));
    console.log(`Total: ${passedCount}/${totalCount} passed, ${skippedCount} skipped, ${failedCount} failed`);
    console.log('='.repeat(60));

    if (this.config.ci) this.generateCIReport();
  }

  private generateCIReport(): void {
    const report = {
      timestamp: new Date().toISOString(),
      duration: Date.now() - this.startTime,
      results: this.results.map((result) => ({
        suite: result.suite,
        status: result.status,
        success: result.success,
        duration: result.duration,
        errors: result.errors,
      })),
      allPassed: this.results.every((result) => result.success),
    };

    console.log('\n📄 CI Report:');
    console.log(JSON.stringify(report, null, 2));
  }

  getResults(): TestResult[] {
    return this.results;
  }
}

export default E2ERunner;

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

  runner.runAll().then((success) => {
    console.log('\n' + (success ? '✅ All required tests passed or were explicitly skipped!' : '❌ Some tests failed'));
    process.exit(success ? 0 : 1);
  }).catch((error) => {
    console.error('❌ E2E Runner failed:', error);
    process.exit(1);
  });
}
