/**
 * Self-Learning Pattern Engine
 * Analyzes test failures and learns successful fix patterns
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join } from 'path';

export interface Pattern {
  id: string;
  name: string;
  errorSignature: string; // Regex pattern to match error
  fixStrategy: string;    // Description of fix approach
  codeTemplate: string;   // Template code for fix
  successRate: number;   // 0-1 based on historical success
  usageCount: number;     // How many times used
  lastUsed: number;      // Timestamp
  tags: string[];        // Categorization tags
  examples: Array<{
    testName: string;
    errorMessage: string;
    appliedFix: string;
    success: boolean;
    timestamp: number;
  }>;
}

export interface PatternLearner {
  patterns: Pattern[];
  learningEnabled: boolean;
  minConfidence: number;
}

export class SelfLearningPatternEngine {
  private patterns: Pattern[] = [];
  private dataDir: string;
  private learningEnabled: boolean = true;
  private minConfidence: number = 0.7;

  constructor(dataDir: string = './e2e/self-learn/data') {
    this.dataDir = dataDir;
    this.ensureDataDirectory();
    this.loadPatterns();
  }

  private ensureDataDirectory(): void {
    if (!existsSync(this.dataDir)) {
      mkdirSync(this.dataDir, { recursive: true });
    }
  }

  private loadPatterns(): void {
    const patternsFile = join(this.dataDir, 'patterns.json');
    
    if (existsSync(patternsFile)) {
      try {
        const data = readFileSync(patternsFile, 'utf-8');
        this.patterns = JSON.parse(data);
        console.log(`📚 Loaded ${this.patterns.length} learned patterns`);
      } catch (error) {
        console.log('⚠️ Failed to load patterns, starting fresh');
        this.patterns = [];
      }
    }
  }

  private savePatterns(): void {
    const patternsFile = join(this.dataDir, 'patterns.json');
    writeFileSync(patternsFile, JSON.stringify(this.patterns, null, 2));
  }

  /**
   * Find matching pattern for an error
   */
  findMatchingPattern(errorMessage: string, testName?: string): Pattern | null {
    if (!this.learningEnabled) return null;

    for (const pattern of this.patterns) {
      try {
        const regex = new RegExp(pattern.errorSignature, 'i');
        if (regex.test(errorMessage) || errorMessage.includes(pattern.errorSignature)) {
          console.log(`🎯 Found matching pattern: ${pattern.name} (${(pattern.successRate * 100).toFixed(0)}% confidence)`);
          pattern.lastUsed = Date.now();
          pattern.usageCount++;
          return pattern;
        }
      } catch (e) {
        // Invalid regex, skip
        continue;
      }
    }

    return null;
  }

  /**
   * Learn from successful fix
   */
  learnFromFix(
    testName: string,
    errorMessage: string,
    appliedFix: string,
    success: boolean
  ): Pattern {
    // Check if similar pattern already exists
    const existingPattern = this.patterns.find(p => 
      this.calculateSimilarity(errorMessage, p.errorSignature) > 0.8
    );

    if (existingPattern) {
      // Update existing pattern
      existingPattern.usageCount++;
      existingPattern.lastUsed = Date.now();
      
      if (success) {
        existingPattern.successRate = 
          (existingPattern.successRate * (existingPattern.usageCount - 1) + 1) / existingPattern.usageCount;
      }

      existingPattern.examples.push({
        testName,
        errorMessage,
        appliedFix,
        success,
        timestamp: Date.now(),
      });

      // Keep only last 50 examples
      if (existingPattern.examples.length > 50) {
        existingPattern.examples = existingPattern.examples.slice(-50);
      }

      this.savePatterns();
      return existingPattern;
    }

    // Create new pattern
    const newPattern: Pattern = {
      id: this.generatePatternId(),
      name: this.generatePatternName(errorMessage),
      errorSignature: this.extractErrorSignature(errorMessage),
      fixStrategy: this.extractFixStrategy(appliedFix),
      codeTemplate: this.extractCodeTemplate(appliedFix),
      successRate: success ? 1 : 0,
      usageCount: 1,
      lastUsed: Date.now(),
      tags: this.extractTags(errorMessage, testName),
      examples: [{
        testName,
        errorMessage,
        appliedFix,
        success,
        timestamp: Date.now(),
      }],
    };

    this.patterns.push(newPattern);
    this.savePatterns();
    
    console.log(`🧠 New pattern learned: ${newPattern.name}`);
    return newPattern;
  }

  /**
   * Generate fix based on learned patterns
   */
  generateFix(errorMessage: string, testName?: string): string | null {
    const pattern = this.findMatchingPattern(errorMessage, testName);
    
    if (!pattern) return null;

    // If confidence is high enough, use the pattern's template
    if (pattern.successRate >= this.minConfidence) {
      return this.applyTemplate(pattern.codeTemplate, {
        errorMessage,
        testName: testName || 'unknown',
        timestamp: Date.now(),
      });
    }

    return null;
  }

  /**
   * Get most successful patterns for a category
   */
  getTopPatterns(category: string, limit: number = 5): Pattern[] {
    return this.patterns
      .filter(p => p.tags.includes(category))
      .sort((a, b) => b.successRate - a.successRate)
      .slice(0, limit);
  }

  /**
   * Update pattern confidence based on outcomes
   */
  updatePatternConfidence(patternId: string, success: boolean): void {
    const pattern = this.patterns.find(p => p.id === patternId);
    
    if (pattern) {
      const totalAttempts = pattern.usageCount;
      const currentSuccesses = pattern.successRate * totalAttempts;
      const newSuccessRate = success 
        ? (currentSuccesses + 1) / (totalAttempts + 1)
        : currentSuccesses / (totalAttempts + 1);

      pattern.successRate = newSuccessRate;
      pattern.usageCount++;
      this.savePatterns();
    }
  }

  /**
   * Merge similar patterns to reduce noise
   */
  mergeSimilarPatterns(threshold: number = 0.9): void {
    const toRemove: string[] = [];
    
    for (let i = 0; i < this.patterns.length; i++) {
      for (let j = i + 1; j < this.patterns.length; j++) {
        const similarity = this.calculateSimilarity(
          this.patterns[i].errorSignature,
          this.patterns[j].errorSignature
        );

        if (similarity >= threshold) {
          // Merge into the more successful pattern
          const keep = this.patterns[i].successRate > this.patterns[j].successRate 
            ? this.patterns[i] 
            : this.patterns[j];
          const remove = keep === this.patterns[i] ? this.patterns[j] : this.patterns[i];

          keep.usageCount += remove.usageCount;
          keep.examples.push(...remove.examples);
          keep.successRate = (keep.successRate + remove.successRate) / 2;

          toRemove.push(remove.id);
        }
      }
    }

    this.patterns = this.patterns.filter(p => !toRemove.includes(p.id));
    this.savePatterns();
    
    console.log(`🔗 Merged ${toRemove.length} similar patterns`);
  }

  private generatePatternId(): string {
    return `pattern_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private generatePatternName(errorMessage: string): string {
    const keywords = this.extractKeywords(errorMessage);
    return keywords.length > 0 
      ? `fix_${keywords.slice(0, 3).join('_')}`
      : `fix_${Date.now()}`;
  }

  private extractErrorSignature(errorMessage: string): string {
    // Extract key parts of the error that would match similar errors
    const patterns = [
      /([A-Z][a-z]+Error)/g,           // Error types
      /([\w]+(?=\s))/g,                 // Words before space
      /undefined|null|NaN/g,            // Common issues
      /cannot read|is not|timed out/g,  // Common phrases
    ];

    let signature = errorMessage;
    
    // Simplify by removing specific values
    signature = signature.replace(/[0-9]+/g, 'N');
    signature = signature.replace(/"[^"]*"/g, '"X"');
    signature = signature.replace(/\[[^\]]+\]/g, '[X]');
    
    // Take first 100 chars
    return signature.substring(0, 100);
  }

  private extractFixStrategy(appliedFix: string): string {
    // Extract the approach/strategy from the fix
    const strategies = [
      { pattern: /waitFor.*toBeVisible/, strategy: 'Wait for visibility with timeout' },
      { pattern: /reloadReactNative|launchApp/, strategy: 'Restart/Reload app' },
      { pattern: /tap\(\)/, strategy: 'Tap interaction' },
      { pattern: /typeText/, strategy: 'Type text input' },
      { pattern: /clearText/, strategy: 'Clear input' },
      { pattern: /waitFor.*toExist/, strategy: 'Wait for element to exist' },
    ];

    for (const { pattern, strategy } of strategies) {
      if (pattern.test(appliedFix)) {
        return strategy;
      }
    }

    return 'Custom fix strategy';
  }

  private extractCodeTemplate(appliedFix: string): string {
    // Simplify and generalize the fix code
    let template = appliedFix;
    
    // Replace specific IDs with placeholders
    template = template.replace(/by\.id\("([^"]+)"\)/g, 'by.id("$1")');
    
    // Replace specific values
    template = template.replace(/timeout:\s*\d+/g, 'timeout: 10000');
    
    // Normalize whitespace
    template = template.replace(/\s+/g, ' ').trim();
    
    return template;
  }

  private extractTags(errorMessage: string, testName?: string): string[] {
    const tags: string[] = [];
    
    if (errorMessage.includes('timeout')) tags.push('timeout');
    if (errorMessage.includes('undefined')) tags.push('undefined');
    if (errorMessage.includes('null')) tags.push('null');
    if (errorMessage.includes('visible') || errorMessage.includes('Visible')) tags.push('visibility');
    if (errorMessage.includes('tap') || errorMessage.includes('Tap')) tags.push('interaction');
    if (errorMessage.includes('navigation') || errorMessage.includes('navigate')) tags.push('navigation');
    if (errorMessage.includes('API') || errorMessage.includes('fetch')) tags.push('api');
    if (errorMessage.includes('memory') || errorMessage.includes('heap')) tags.push('memory');
    
    if (testName) {
      if (testName.includes('Home')) tags.push('home-screen');
      if (testName.includes('Canvas')) tags.push('canvas');
      if (testName.includes('Chat')) tags.push('chat');
      if (testName.includes('Settings')) tags.push('settings');
    }

    return [...new Set(tags)];
  }

  private extractKeywords(errorMessage: string): string[] {
    const words = errorMessage.split(/\s+/);
    const keywords = words
      .filter(w => w.length > 4 && /^[a-zA-Z]+$/.test(w))
      .map(w => w.toLowerCase().substring(0, 20));
    
    return [...new Set(keywords)].slice(0, 5);
  }

  private calculateSimilarity(str1: string, str2: string): number {
    const s1 = str1.toLowerCase();
    const s2 = str2.toLowerCase();
    
    if (s1 === s2) return 1;
    if (s1.includes(s2) || s2.includes(s1)) return 0.9;
    
    // Simple Jaccard similarity on words
    const words1 = new Set(s1.split(/\W+/));
    const words2 = new Set(s2.split(/\W+/));
    
    const intersection = new Set([...words1].filter(x => words2.has(x)));
    const union = new Set([...words1, ...words2]);
    
    return intersection.size / union.size;
  }

  private applyTemplate(template: string, context: Record<string, unknown>): string {
    let result = template;
    
    for (const [key, value] of Object.entries(context)) {
      result = result.replace(new RegExp(`\\{${key}\\}`, 'g'), String(value));
    }
    
    return result;
  }

  getStatistics(): {
    totalPatterns: number;
    avgSuccessRate: number;
    mostUsedCategory: string;
    recentlyLearned: number;
  } {
    const categories: Record<string, number> = {};
    
    for (const pattern of this.patterns) {
      for (const tag of pattern.tags) {
        categories[tag] = (categories[tag] || 0) + pattern.usageCount;
      }
    }

    const mostUsed = Object.entries(categories).sort((a, b) => b[1] - a[1])[0];

    return {
      totalPatterns: this.patterns.length,
      avgSuccessRate: this.patterns.length > 0 
        ? this.patterns.reduce((sum, p) => sum + p.successRate, 0) / this.patterns.length 
        : 0,
      mostUsedCategory: mostUsed?.[0] || 'none',
      recentlyLearned: this.patterns.filter(p => Date.now() - p.lastUsed < 86400000).length,
    };
  }

  enableLearning(): void {
    this.learningEnabled = true;
    console.log('🧠 Self-learning enabled');
  }

  disableLearning(): void {
    this.learningEnabled = false;
    console.log('📴 Self-learning disabled');
  }
}

export default SelfLearningPatternEngine;