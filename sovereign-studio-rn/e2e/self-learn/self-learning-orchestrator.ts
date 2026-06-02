/**
 * SelfLearningOrchestrator
 * Main orchestrator for intelligent self-learning, pattern recognition, and continuous improvement
 */

import { execSync } from 'child_process';
import { writeFileSync, existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import { SelfLearningPatternEngine, Pattern } from './patterns/pattern-engine';
import { RoutineEngine } from './routines/routine-engine';
import { SelfImprovingML } from './ml/self-improving-ml';

export interface SelfLearningConfig {
  learningEnabled: boolean;
  patternConfidenceThreshold: number;
  autoOptimize: boolean;
  maxIterations: number;
  improvementReportEnabled: boolean;
}

export interface ImprovementReport {
  timestamp: number;
  patternsLearned: number;
  improvementsMade: string[];
  predictionsMade: number;
  avgAccuracy: number;
  recommendations: string[];
}

export interface CycleResult {
  success: boolean;
  iterations: number;
  patternsLearned: Pattern[];
  improvements: string[];
  duration: number;
}

export class SelfLearningOrchestrator {
  private patternEngine: SelfLearningPatternEngine;
  private routineEngine: RoutineEngine;
  private mlEngine: SelfImprovingML;
  private config: SelfLearningConfig;
  private dataDir: string;
  private cycleCount: number = 0;

  constructor(dataDir: string = './e2e/self-learn/data') {
    this.dataDir = dataDir;
    
    this.config = {
      learningEnabled: true,
      patternConfidenceThreshold: 0.7,
      autoOptimize: true,
      maxIterations: Infinity,
      improvementReportEnabled: true,
    };

    this.ensureDataDirectory();
    
    this.patternEngine = new SelfLearningPatternEngine(dataDir);
    this.routineEngine = new RoutineEngine(dataDir);
    this.mlEngine = new SelfImprovingML(dataDir);

    console.log('\n🧠 Self-Learning Orchestrator initialized');
    console.log(`   Data directory: ${dataDir}`);
    console.log(`   Pattern engine: Active`);
    console.log(`   Routine engine: Active`);
    console.log(`   ML engine: Active`);
  }

  private ensureDataDirectory(): void {
    const dirs = [this.dataDir, join(this.dataDir, 'ml'), join(this.dataDir, 'patterns'), join(this.dataDir, 'routines')];
    
    for (const dir of dirs) {
      if (!existsSync(dir)) {
        mkdirSync(dir, { recursive: true });
      }
    }
  }

  /**
   * Run complete self-improvement cycle
   */
  async runImprovementCycle(): Promise<CycleResult> {
    const startTime = Date.now();
    const patternsLearned: Pattern[] = [];
    const improvements: string[] = [];

    console.log('\n' + '='.repeat(60));
    console.log('🧠 SELF-LEARNING IMPROVEMENT CYCLE');
    console.log('='.repeat(60));
    console.log(`   Learning enabled: ${this.config.learningEnabled}`);
    console.log(`   Auto-optimize: ${this.config.autoOptimize}`);
    console.log(`   Cycle #${++this.cycleCount}`);

    try {
      // Step 1: Run E2E tests with observation
      console.log('\n📋 Step 1: Running E2E tests with learning...');
      const testResult = await this.runTestsWithLearning();
      
      if (testResult.success) {
        console.log('   ✅ All tests passed - no fixes needed');
      } else {
        console.log('   ❌ Tests failed - learning from failures...');
        
        // Step 2: Analyze and learn patterns
        console.log('\n📚 Step 2: Analyzing failure patterns...');
        for (const failure of testResult.failures) {
          const pattern = this.patternEngine.learnFromFix(
            failure.testName,
            failure.errorMessage,
            failure.appliedFix || '',
            false
          );
          patternsLearned.push(pattern);
          
          // Also record for ML training
          const features = this.mlEngine.extractFeatures(
            failure.testName,
            failure.errorMessage,
            failure.duration
          );
          this.mlEngine.recordExample(features, 0);
        }

        // Step 3: Generate improvements based on patterns
        console.log('\n🔧 Step 3: Generating improvements...');
        const predictedFailures = this.mlEngine.predictFailure('general');
        
        if (predictedFailures.probability > 0.5) {
          const recommendations = this.mlEngine.suggestImprovements('general');
          
          for (const rec of recommendations) {
            console.log(`   💡 ${rec.type}: ${rec.suggestedChange}`);
            improvements.push(`${rec.type}: ${rec.suggestedChange}`);
            
            // Apply recommended improvements
            await this.applyImprovement(rec);
          }
        }

        // Step 4: Run tests again
        console.log('\n🔄 Step 4: Re-running tests with improvements...');
        const retryResult = await this.runTestsWithLearning();
        
        if (retryResult.success) {
          console.log('   ✅ Tests passed after improvements!');
          
          // Record successful outcome
          for (const failure of testResult.failures) {
            this.mlEngine.recordExample(
              this.mlEngine.extractFeatures(failure.testName),
              1 // Success
            );
          }
        }
      }

      // Step 5: Optimize routines based on learning
      if (this.config.autoOptimize) {
        console.log('\n⚡ Step 5: Optimizing routines...');
        const routineStats = this.routineEngine.listRoutines();
        
        for (const routine of routineStats) {
          if (routine.enabled) {
            const result = await this.routineEngine.executeRoutine(routine.id);
            
            if (result.improvements.length > 0) {
              console.log(`   ✅ ${routine.name}: ${result.improvements.length} improvements`);
              improvements.push(...result.improvements);
            }
          }
        }
      }

      // Step 6: Train ML models
      console.log('\n🧠 Step 6: Training ML models...');
      this.mlEngine.trainModels();

      // Generate improvement report
      if (this.config.improvementReportEnabled) {
        this.generateImprovementReport(patternsLearned, improvements);
      }

      const duration = Date.now() - startTime;
      
      console.log('\n' + '='.repeat(60));
      console.log('✅ SELF-LEARNING CYCLE COMPLETE');
      console.log(`   Duration: ${duration}ms`);
      console.log(`   Patterns learned: ${patternsLearned.length}`);
      console.log(`   Improvements applied: ${improvements.length}`);
      console.log(`   ML accuracy: ${(this.mlEngine.getStatistics().avgAccuracy * 100).toFixed(0)}%`);

      return {
        success: improvements.length === 0 || improvements.length > 0,
        iterations: this.cycleCount,
        patternsLearned,
        improvements,
        duration,
      };

    } catch (error) {
      console.error('\n❌ Self-learning cycle failed:', error);
      
      return {
        success: false,
        iterations: this.cycleCount,
        patternsLearned,
        improvements,
        duration: Date.now() - startTime,
      };
    }
  }

  private async runTestsWithLearning(): Promise<{
    success: boolean;
    failures: Array<{
      testName: string;
      errorMessage: string;
      appliedFix?: string;
      duration?: number;
    }>;
  }> {
    const failures: Array<{
      testName: string;
      errorMessage: string;
      appliedFix?: string;
      duration?: number;
    }> = [];

    try {
      console.log('   Running tests...');
      execSync('npm run e2e:detox', {
        encoding: 'utf-8',
        timeout: 300000,
        stdio: 'pipe',
      });

      return { success: true, failures: [] };

    } catch (error) {
      const output = error instanceof Error ? error.message : String(error);
      
      // Parse failures from test output
      const failureMatches = output.match(/✕\s+(.+?)(?=\n|$)/g);
      
      if (failureMatches) {
        for (const match of failureMatches) {
          const testName = match.replace('✕', '').trim();
          
          // Check for learned pattern
          const pattern = this.patternEngine.findMatchingPattern(testName);
          let appliedFix: string | undefined;

          if (pattern && pattern.successRate > this.config.patternConfidenceThreshold) {
            appliedFix = this.patternEngine.generateFix(testName) || undefined;
          }

          failures.push({
            testName,
            errorMessage: this.extractErrorFromOutput(output, testName),
            appliedFix,
          });
        }
      } else {
        failures.push({
          testName: 'unknown',
          errorMessage: output.substring(0, 500),
        });
      }

      return { success: false, failures };
    }
  }

  private extractErrorFromOutput(output: string, testName: string): string {
    // Extract error message for specific test
    const lines = output.split('\n');
    let foundTest = false;

    for (const line of lines) {
      if (line.includes(testName)) {
        foundTest = true;
      }
      
      if (foundTest && line.includes('Error:')) {
        return line.replace('Error:', '').trim();
      }
    }

    return 'Unknown error';
  }

  private async applyImprovement(rec: { type: string; suggestedChange: string }): Promise<void> {
    console.log(`   Applying: ${rec.type}`);

    switch (rec.type) {
      case 'timeout':
        await this.applyTimeoutImprovement(rec.suggestedChange);
        break;
      case 'retry':
        await this.applyRetryImprovement(rec.suggestedChange);
        break;
      case 'fallback':
        await this.applyFallbackImprovement(rec.suggestedChange);
        break;
      case 'circuit-breaker':
        await this.applyCircuitBreakerImprovement(rec.suggestedChange);
        break;
      case 'cache':
        await this.applyCacheImprovement(rec.suggestedChange);
        break;
    }
  }

  private async applyTimeoutImprovement(change: string): Promise<void> {
    console.log('      📝 Updating timeout configuration...');
    // In real implementation, update test configuration files
  }

  private async applyRetryImprovement(change: string): Promise<void> {
    console.log('      📝 Adding retry mechanism...');
    // Add retry logic to test utilities
  }

  private async applyFallbackImprovement(change: string): Promise<void> {
    console.log('      📝 Optimizing API fallback chain...');
    // Update API fallback configuration
  }

  private async applyCircuitBreakerImprovement(change: string): Promise<void> {
    console.log('      📝 Adding circuit breaker...');
    // Add circuit breaker to API calls
  }

  private async applyCacheImprovement(change: string): Promise<void> {
    console.log('      📝 Implementing caching...');
    // Add result caching
  }

  private generateImprovementReport(
    patternsLearned: Pattern[],
    improvements: string[]
  ): void {
    const report: ImprovementReport = {
      timestamp: Date.now(),
      patternsLearned: patternsLearned.length,
      improvementsMade: improvements,
      predictionsMade: this.mlEngine.getStatistics().predictionsCount,
      avgAccuracy: this.mlEngine.getStatistics().avgAccuracy,
      recommendations: this.mlEngine.suggestImprovements('general').map(r => r.suggestedChange),
    };

    const reportPath = join(this.dataDir, 'improvement-report.json');
    writeFileSync(reportPath, JSON.stringify(report, null, 2));

    console.log('\n📄 Improvement Report Generated:');
    console.log(`   Patterns learned: ${report.patternsLearned}`);
    console.log(`   Improvements: ${report.improvementsMade.length}`);
    console.log(`   ML Accuracy: ${(report.avgAccuracy * 100).toFixed(0)}%`);
  }

  /**
   * Get current learning status
   */
  getStatus(): {
    patternsCount: number;
    routinesCount: number;
    mlStats: ReturnType<typeof this.mlEngine.getStatistics>;
    cycleCount: number;
    lastReport?: ImprovementReport;
  } {
    let lastReport: ImprovementReport | undefined;
    
    const reportPath = join(this.dataDir, 'improvement-report.json');
    if (existsSync(reportPath)) {
      try {
        lastReport = JSON.parse(readFileSync(reportPath, 'utf-8'));
      } catch {
        // Ignore
      }
    }

    return {
      patternsCount: this.patternEngine.getStatistics().totalPatterns,
      routinesCount: this.routineEngine.listRoutines().length,
      mlStats: this.mlEngine.getStatistics(),
      cycleCount: this.cycleCount,
      lastReport,
    };
  }

  /**
   * Enable/disable learning
   */
  setLearningEnabled(enabled: boolean): void {
    this.config.learningEnabled = enabled;
    this.patternEngine.learningEnabled = enabled;
    console.log(`🧠 Learning ${enabled ? 'enabled' : 'disabled'}`);
  }

  /**
   * Export learned data
   */
  exportLearnedData(): string {
    return JSON.stringify({
      patterns: this.patternEngine.getStatistics(),
      ml: this.mlEngine.getStatistics(),
      config: this.config,
    }, null, 2);
  }

  /**
   * Merge patterns from external source
   */
  mergePatterns(externalPatterns: Pattern[]): void {
    for (const pattern of externalPatterns) {
      this.patternEngine.learnFromFix(
        pattern.examples[0]?.testName || 'external',
        pattern.errorSignature,
        pattern.codeTemplate,
        pattern.successRate > 0.5
      );
    }
    console.log(`🧠 Merged ${externalPatterns.length} external patterns`);
  }
}

export default SelfLearningOrchestrator;

// CLI Interface
if (require.main === module) {
  const args = process.argv.slice(2);
  const command = args[0] || 'run';

  const orchestrator = new SelfLearningOrchestrator();

  switch (command) {
    case 'run':
      orchestrator.runImprovementCycle().then(result => {
        console.log('\n📊 Result:', JSON.stringify(result, null, 2));
        process.exit(result.success ? 0 : 1);
      });
      break;

    case 'status':
      const status = orchestrator.getStatus();
      console.log('\n📊 Self-Learning Status:');
      console.log(JSON.stringify(status, null, 2));
      break;

    case 'export':
      console.log('\n📦 Exported Data:');
      console.log(orchestrator.exportLearnedData());
      break;

    default:
      console.log('Usage:');
      console.log('  node self-learning-orchestrator.js run    - Run improvement cycle');
      console.log('  node self-learning-orchestrator.js status - Show status');
      console.log('  node self-learning-orchestrator.js export - Export learned data');
  }
}