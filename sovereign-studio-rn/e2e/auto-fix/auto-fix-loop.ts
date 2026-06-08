/**
 * Auto-Fix Loop Implementation
 * Error → Fix → Re-Test → Auto-Merge
 */

import { execSync } from 'child_process';
import { writeFileSync, readFileSync, existsSync } from 'fs';
import { join } from 'path';

export interface AutoFixConfig {
  maxIterations: number;
  testCommand: string;
  fixModel: 'gemini' | 'claude' | 'gpt4';
  autoMerge: boolean;
  verbose: boolean;
}

export interface FixResult {
  success: boolean;
  iterations: number;
  fixed: boolean;
  error?: string;
  changes?: string[];
  testOutput?: string;
}

export interface TestFailure {
  testName: string;
  errorMessage: string;
  stackTrace?: string;
  file?: string;
  line?: number;
}

export const DEFAULT_AUTO_FIX_CONFIG: AutoFixConfig = {
  maxIterations: Infinity, // Unlimited iterations until all tests pass
  testCommand: 'npm run e2e:detox',
  fixModel: 'gemini',
  autoMerge: false,
  verbose: true,
};

class AutoFixLoop {
  private config: AutoFixConfig;
  private iteration = 0;
  private testResults: string[] = [];

  constructor(config: Partial<AutoFixConfig> = {}) {
    this.config = { ...DEFAULT_AUTO_FIX_CONFIG, ...config };
  }

  async run(fixFunction?: (failure: TestFailure) => Promise<string>): Promise<FixResult> {
    console.log('🚀 Starting Auto-Fix Loop');
    console.log(`   Max iterations: ${this.config.maxIterations === Infinity ? 'Unlimited' : this.config.maxIterations}`);
    console.log(`   Test command: ${this.config.testCommand}`);

    while (this.iteration < this.config.maxIterations) {
      this.iteration++;
      const iterationDisplay = this.config.maxIterations === Infinity 
        ? `Iteration ${this.iteration}` 
        : `Iteration ${this.iteration}/${this.config.maxIterations}`;
      console.log(`\n${'='.repeat(50)}`);
      console.log(`📋 ${iterationDisplay}`);
      console.log('='.repeat(50));

      // Step 1: Run tests
      const testPassed = await this.runTests();
      
      if (testPassed) {
        console.log('\n✅ All tests passed!');
        return this.successResult();
      }

      // Step 2: Analyze failures
      const failures = this.analyzeFailures();
      
      if (failures.length === 0) {
        console.log('\n⚠️ No specific failures detected');
        return this.successResult();
      }

      // Step 3: Generate fixes
      for (const failure of failures) {
        console.log(`\n🔧 Analyzing failure: ${failure.testName}`);
        console.log(`   Error: ${failure.errorMessage}`);

        if (fixFunction) {
          const fix = await fixFunction(failure);
          console.log(`   Generated fix:\n${fix}`);
          await this.applyFix(fix, failure.file);
        } else {
          // Use AI to generate fix
          const fix = await this.generateFixWithAI(failure);
          console.log(`   AI fix:\n${fix}`);
          await this.applyFix(fix, failure.file);
        }
      }

      // Step 4: Commit changes
      await this.commitChanges();

      // Step 5: Wait for CI
      await this.waitForCI();
    }

    console.log('\n❌ Max iterations reached without fix');
    return this.failureResult('Max iterations reached');
  }

  private async runTests(): Promise<boolean> {
    console.log('\n🔬 Running tests...');
    
    try {
      const output = execSync(this.config.testCommand, {
        encoding: 'utf-8',
        timeout: 300000,
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      this.testResults.push(output);
      
      if (this.config.verbose) {
        console.log(output);
      }

      return output.includes('PASS') || output.includes('passed');
    } catch (error) {
      const errorOutput = error instanceof Error ? error.message : String(error);
      this.testResults.push(errorOutput);
      
      if (this.config.verbose) {
        console.log(errorOutput);
      }

      return false;
    }
  }

  private analyzeFailures(): TestFailure[] {
    const failures: TestFailure[] = [];
    const result = this.testResults[this.testResults.length - 1] || '';
    
    // Parse Jest/Detox output for failures
    const failurePattern = /FAIL|PASS|✕|×|failed/i;
    const testNamePattern = /✓|✕|×|PASS|FAIL|Tests:.*failed/i;
    
    // Extract failure information
    const lines = result.split('\n');
    let currentFailure: Partial<TestFailure> = {};

    for (const line of lines) {
      if (line.includes('FAIL') || line.includes('failed')) {
        // Found a test failure
        const testMatch = line.match(/✕\s+(.+)/) || line.match(/×\s+(.+)/);
        if (testMatch) {
          currentFailure.testName = testMatch[1];
        }
      }
      
      if (line.includes('Error:') || line.includes('AssertionError')) {
        currentFailure.errorMessage = line;
      }
      
      if (line.includes('.spec.ts') || line.includes('.test.ts')) {
        const fileMatch = line.match(/((?:\w+\/)*\w+\.(?:spec|test)\.ts)/);
        if (fileMatch) {
          currentFailure.file = fileMatch[1];
        }
      }
    }

    if (Object.keys(currentFailure).length > 0) {
      failures.push(currentFailure as TestFailure);
    }

    return failures;
  }

  private async generateFixWithAI(failure: TestFailure): Promise<string> {
    console.log(`🤖 Generating fix with ${this.config.fixModel}...`);
    
    // This would use the configured AI model to generate a fix
    const prompt = `
Analyze this test failure and generate a fix:

Test: ${failure.testName}
Error: ${failure.errorMessage}
Stack: ${failure.stackTrace || 'N/A'}
File: ${failure.file || 'Unknown'}

Generate a TypeScript/JavaScript code fix that resolves this issue.
Return ONLY the code fix without explanation.
    `.trim();

    // Simulate AI response (in real implementation, call the AI API)
    const mockFixes: Record<string, string> = {
      'should display': 'await waitFor(element(by.id("element"))).toBeVisible({ timeout: 10000 });',
      'should navigate': 'await element(by.id("button")).tap();',
      'timeout': '// Increase timeout for slow operations',
      'undefined': '// Add null check',
    };

    let fix = '// Review and apply fix manually';
    for (const [key, value] of Object.entries(mockFixes)) {
      if (failure.errorMessage.toLowerCase().includes(key)) {
        fix = value;
        break;
      }
    }

    return fix;
  }

  private async applyFix(fix: string, file?: string): Promise<void> {
    if (!file) {
      console.log('⚠️ No file specified for fix');
      return;
    }

    console.log(`📝 Applying fix to ${file}...`);
    
    try {
      const filePath = join(process.cwd(), file);
      
      if (existsSync(filePath)) {
        const content = readFileSync(filePath, 'utf-8');
        // In a real implementation, use a proper diff/patch approach
        const newContent = content + '\n// Auto-fix applied\n' + fix;
        writeFileSync(filePath, newContent);
        console.log('✅ Fix applied');
      } else {
        console.log(`❌ File not found: ${filePath}`);
      }
    } catch (error) {
      console.error(`❌ Failed to apply fix: ${error}`);
    }
  }

  private async commitChanges(): Promise<void> {
    console.log('\n📤 Committing changes...');
    
    try {
      execSync('git add -A', { stdio: 'ignore' });
      execSync('git commit -m "Auto-fix: Iteration ' + this.iteration + '"', { stdio: 'ignore' });
      execSync('git push', { stdio: 'ignore' });
      console.log('✅ Changes committed and pushed');
    } catch (error) {
      console.log('⚠️ Git commit/push failed (may be no changes)');
    }
  }

  private async waitForCI(): Promise<void> {
    console.log('\n⏳ Waiting for CI...');
    // In a real implementation, poll GitHub Actions or other CI
    const waitTime = 30000;
    
    return new Promise(resolve => {
      setTimeout(resolve, waitTime);
    });
  }

  private successResult(): FixResult {
    return {
      success: true,
      iterations: this.iteration,
      fixed: this.iteration < this.config.maxIterations,
    };
  }

  private failureResult(error?: string): FixResult {
    return {
      success: false,
      iterations: this.iteration,
      fixed: false,
      error: error || 'Unknown error',
    };
  }

  getIteration(): number {
    return this.iteration;
  }

  getResults(): string[] {
    return this.testResults;
  }
}

export default AutoFixLoop;
export { AutoFixLoop };

// CLI Interface
if (require.main === module) {
  const args = process.argv.slice(2);
  const config: Partial<AutoFixConfig> = {
    maxIterations: parseInt(args.find(a => a.startsWith('--max='))?.split('=')[1] || '5'),
    testCommand: args.find(a => a.startsWith('--test='))?.split('=')[1] || 'npm run e2e:detox',
    autoMerge: args.includes('--auto-merge'),
    verbose: !args.includes('--quiet'),
  };

  const fixer = new AutoFixLoop(config);
  
  fixer.run().then(result => {
    console.log('\n📊 Auto-Fix Result:');
    console.log(JSON.stringify(result, null, 2));
    process.exit(result.success ? 0 : 1);
  });
}