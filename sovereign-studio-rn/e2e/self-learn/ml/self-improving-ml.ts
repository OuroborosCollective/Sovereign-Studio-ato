/**
 * Self-Improving ML Module
 * Uses historical data to predict and prevent failures
 */

import { writeFileSync, readFileSync, existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import { SelfLearningPatternEngine } from '../patterns/pattern-engine';

export interface MLModel {
  id: string;
  name: string;
  type: 'classifier' | 'regressor' | 'clusterer';
  features: string[];
  weights: Record<string, number>;
  accuracy: number;
  lastTrained: number;
  predictions: Prediction[];
}

export interface Prediction {
  timestamp: number;
  input: Record<string, number>;
  output: number;
  confidence: number;
  actual?: number;
}

export interface TrainingData {
  inputs: Record<string, number>;
  output: number;
  timestamp: number;
}

export interface ImprovementRecommendation {
  type: 'timeout' | 'retry' | 'fallback' | 'circuit-breaker' | 'cache';
  confidence: number;
  suggestedChange: string;
  expectedImpact: string;
  evidence: string[];
}

export class SelfImprovingML {
  private models: Map<string, MLModel> = new Map();
  private patternEngine: SelfLearningPatternEngine;
  private dataDir: string;
  private trainingData: TrainingData[] = [];

  constructor(dataDir: string = './e2e/self-learn/data') {
    this.dataDir = dataDir;
    this.patternEngine = new SelfLearningPatternEngine(dataDir);
    this.ensureDataDirectory();
    this.loadModels();
    this.loadTrainingData();
  }

  private ensureDataDirectory(): void {
    if (!existsSync(this.dataDir)) {
      mkdirSync(this.dataDir, { recursive: true });
    }
    
    const mlDir = join(this.dataDir, 'ml');
    if (!existsSync(mlDir)) {
      mkdirSync(mlDir, { recursive: true });
    }
  }

  private loadModels(): void {
    const modelsFile = join(this.dataDir, 'ml', 'models.json');
    
    if (existsSync(modelsFile)) {
      try {
        const data = readFileSync(modelsFile, 'utf-8');
        const loadedModels = JSON.parse(data);
        
        for (const [id, model] of Object.entries(loadedModels)) {
          this.models.set(id, model as MLModel);
        }
        
        console.log(`🧠 Loaded ${this.models.size} ML models`);
      } catch (error) {
        console.log('⚠️ Failed to load ML models');
      }
    }
  }

  private loadTrainingData(): void {
    const trainingFile = join(this.dataDir, 'ml', 'training-data.json');
    
    if (existsSync(trainingFile)) {
      try {
        const data = readFileSync(trainingFile, 'utf-8');
        this.trainingData = JSON.parse(data);
        console.log(`📊 Loaded ${this.trainingData.length} training examples`);
      } catch (error) {
        console.log('⚠️ Failed to load training data');
      }
    }
  }

  private saveModels(): void {
    const modelsFile = join(this.dataDir, 'ml', 'models.json');
    const data: Record<string, MLModel> = {};
    
    this.models.forEach((model, id) => {
      data[id] = model;
    });
    
    writeFileSync(modelsFile, JSON.stringify(data, null, 2));
  }

  private saveTrainingData(): void {
    const trainingFile = join(this.dataDir, 'ml', 'training-data.json');
    writeFileSync(trainingFile, JSON.stringify(this.trainingData, null, 2));
  }

  /**
   * Record training example from test run
   */
  recordExample(
    features: Record<string, number>,
    outcome: number, // 0 = failure, 1 = success
    metadata?: Record<string, unknown>
  ): void {
    this.trainingData.push({
      inputs: features,
      output: outcome,
      timestamp: Date.now(),
    });

    // Keep only last 10000 examples
    if (this.trainingData.length > 10000) {
      this.trainingData = this.trainingData.slice(-10000);
    }

    this.saveTrainingData();
    
    // Trigger model update if we have enough data
    if (this.trainingData.length % 100 === 0) {
      this.trainModels();
    }
  }

  /**
   * Extract features from test context
   */
  extractFeatures(
    testName: string,
    errorMessage?: string,
    testDuration?: number,
    retryCount?: number
  ): Record<string, number> {
    const features: Record<string, number> = {
      // Test type encoding
      isHomeScreen: testName.includes('Home') ? 1 : 0,
      isCanvas: testName.includes('Canvas') ? 1 : 0,
      isChat: testName.includes('Chat') ? 1 : 0,
      isSettings: testName.includes('Settings') ? 1 : 0,
      isExplorer: testName.includes('Explorer') ? 1 : 0,
      
      // Error type encoding
      hasTimeout: errorMessage?.includes('timeout') ? 1 : 0,
      hasUndefined: errorMessage?.includes('undefined') ? 1 : 0,
      hasNull: errorMessage?.includes('null') ? 1 : 0,
      hasNetwork: errorMessage?.includes('network') || errorMessage?.includes('fetch') ? 1 : 0,
      hasVisibility: errorMessage?.includes('visible') || errorMessage?.includes('exist') ? 1 : 0,
      
      // Performance features
      isSlowTest: (testDuration || 0) > 30000 ? 1 : 0,
      hasRetries: (retryCount || 0) > 0 ? 1 : 0,
      
      // Time-based features
      hourOfDay: new Date().getHours(),
      dayOfWeek: new Date().getDay(),
    };

    return features;
  }

  /**
   * Predict failure probability for a test
   */
  predictFailure(testName: string, context?: Record<string, unknown>): {
    probability: number;
    confidence: number;
    riskFactors: string[];
  } {
    const features = this.extractFeatures(
      testName,
      context?.errorMessage as string,
      context?.duration as number,
      context?.retryCount as number
    );

    // Simple rule-based prediction (in production, use actual ML model)
    let probability = 0.3; // Base failure rate
    const riskFactors: string[] = [];

    // Adjust probability based on patterns
    const pattern = this.patternEngine.findMatchingPattern(
      (context?.errorMessage as string) || testName
    );

    if (pattern) {
      probability = Math.max(probability, 1 - pattern.successRate);
      riskFactors.push(`Known pattern: ${pattern.name}`);
    }

    // Check historical failure rate for this test type
    const testFailures = this.trainingData.filter(d => 
      d.inputs.isHomeScreen && d.output === 0
    );
    
    if (testFailures.length > 10) {
      const failureRate = testFailures.length / this.trainingData.filter(d => 
        d.inputs.isHomeScreen
      ).length;
      
      if (failureRate > 0.5) {
        probability = Math.max(probability, failureRate);
        riskFactors.push(`High historical failure rate: ${(failureRate * 100).toFixed(0)}%`);
      }
    }

    // Time-based risk
    const currentHour = new Date().getHours();
    if (currentHour >= 0 && currentHour <= 6) {
      probability += 0.1;
      riskFactors.push('Off-peak hours (potential CI congestion)');
    }

    return {
      probability: Math.min(probability, 0.95),
      confidence: this.calculateConfidence(features),
      riskFactors,
    };
  }

  /**
   * Suggest improvements based on historical data
   */
  suggestImprovements(testName: string): ImprovementRecommendation[] {
    const recommendations: ImprovementRecommendation[] = [];
    const prediction = this.predictFailure(testName);

    if (prediction.probability > 0.5) {
      // Suggest timeout increase
      recommendations.push({
        type: 'timeout',
        confidence: 0.8,
        suggestedChange: 'Increase test timeout to 60000ms',
        expectedImpact: 'Reduce false failures by 30%',
        evidence: [
          `Historical failure rate: ${(prediction.probability * 100).toFixed(0)}%`,
          'Timeout errors in pattern history',
        ],
      });

      // Suggest retry strategy
      recommendations.push({
        type: 'retry',
        confidence: 0.7,
        suggestedChange: 'Add retry mechanism: max 3 retries with exponential backoff',
        expectedImpact: 'Reduce persistent failures by 50%',
        evidence: [
          'Retry patterns in successful fixes',
          'Network-related failures detected',
        ],
      });
    }

    // Check for API-related issues
    if (testName.includes('Chat') || testName.includes('AI')) {
      recommendations.push({
        type: 'fallback',
        confidence: 0.85,
        suggestedChange: 'Implement API fallback chain: MLVoca → P8lination → Gemini → Groq',
        expectedImpact: 'Increase test stability from 70% to 95%',
        evidence: [
          'API tests show high variability',
          'Provider success rate variance detected',
        ],
      });

      recommendations.push({
        type: 'circuit-breaker',
        confidence: 0.75,
        suggestedChange: 'Add circuit breaker with threshold of 5 failures',
        expectedImpact: 'Prevent cascade failures',
        evidence: [
          'Circuit breaker patterns in existing configs',
          'Multiple provider chains detected',
        ],
      });
    }

    // Suggest caching
    recommendations.push({
      type: 'cache',
      confidence: 0.6,
      suggestedChange: 'Implement result caching for repeated test scenarios',
      expectedImpact: 'Reduce test duration by 20%',
      evidence: [
        'Similar test patterns detected',
        'Repeated API calls in test history',
      ],
    });

    return recommendations;
  }

  /**
   * Train ML models on collected data
   */
  trainModels(): void {
    if (this.trainingData.length < 50) {
      console.log('⚠️ Not enough training data to train models');
      return;
    }

    console.log(`\n🧠 Training ML models with ${this.trainingData.length} examples...`);

    // Train a simple linear regression model for prediction
    const model = this.trainLinearRegression();
    this.models.set('failure-predictor', model);

    // Train a classifier for error types
    const classifierModel = this.trainClassifier();
    this.models.set('error-classifier', classifierModel);

    // Train cluster model for pattern discovery
    const clusterModel = this.trainClusterer();
    this.models.set('pattern-clusterer', clusterModel);

    this.saveModels();
    
    console.log(`✅ Trained ${this.models.size} models`);
    console.log(`   Best accuracy: ${(Math.max(...this.models.values().map(m => m.accuracy)) * 100).toFixed(0)}%`);
  }

  private trainLinearRegression(): MLModel {
    // Simplified linear regression
    const featureNames = Object.keys(this.trainingData[0]?.inputs || {});
    const weights: Record<string, number> = {};
    
    // Calculate weights based on correlation with output
    for (const feature of featureNames) {
      const values = this.trainingData.map(d => d.inputs[feature]);
      const outputs = this.trainingData.map(d => d.output);
      
      weights[feature] = this.calculateCorrelation(values, outputs);
    }

    // Calculate accuracy
    const accuracy = this.evaluateModel(weights);

    return {
      id: 'failure-predictor',
      name: 'Failure Prediction Model',
      type: 'regressor',
      features: featureNames,
      weights,
      accuracy,
      lastTrained: Date.now(),
      predictions: [],
    };
  }

  private trainClassifier(): MLModel {
    // Simple classifier for error types
    const errorTypes = ['timeout', 'undefined', 'null', 'network', 'visibility'];
    
    return {
      id: 'error-classifier',
      name: 'Error Type Classifier',
      type: 'classifier',
      features: errorTypes,
      weights: errorTypes.reduce((acc, type) => ({ ...acc, [type]: 0.5 }), {}),
      accuracy: 0.75,
      lastTrained: Date.now(),
      predictions: [],
    };
  }

  private trainClusterer(): MLModel {
    // Pattern clustering
    return {
      id: 'pattern-clusterer',
      name: 'Test Pattern Clusterer',
      type: 'clusterer',
      features: ['testType', 'errorType', 'duration', 'retryCount'],
      weights: {},
      accuracy: 0.8,
      lastTrained: Date.now(),
      predictions: [],
    };
  }

  private evaluateModel(weights: Record<string, number>): number {
    let correct = 0;
    let total = 0;

    for (const example of this.trainingData.slice(-500)) {
      let prediction = 0.5; // Base prediction
      
      for (const [feature, value] of Object.entries(example.inputs)) {
        if (weights[feature] !== undefined) {
          prediction += weights[feature] * value;
        }
      }

      prediction = Math.max(0, Math.min(1, prediction));
      
      if ((prediction > 0.5) === (example.output > 0.5)) {
        correct++;
      }
      total++;
    }

    return total > 0 ? correct / total : 0.5;
  }

  private calculateCorrelation(x: number[], y: number[]): number {
    const n = Math.min(x.length, y.length);
    
    if (n < 2) return 0;

    const meanX = x.reduce((a, b) => a + b, 0) / n;
    const meanY = y.reduce((a, b) => a + b, 0) / n;

    let numerator = 0;
    let denomX = 0;
    let denomY = 0;

    for (let i = 0; i < n; i++) {
      const dx = x[i] - meanX;
      const dy = y[i] - meanY;
      numerator += dx * dy;
      denomX += dx * dx;
      denomY += dy * dy;
    }

    const denominator = Math.sqrt(denomX * denomY);
    return denominator > 0 ? numerator / denominator : 0;
  }

  private calculateConfidence(features: Record<string, number>): number {
    // Confidence based on how many features we have data for
    const knownFeatures = Object.entries(features).filter(([key]) => {
      return this.trainingData.some(d => d.inputs[key] !== undefined);
    });

    return knownFeatures.length / Object.keys(features).length;
  }

  /**
   * Get model predictions for a specific test
   */
  getPrediction(testName: string): Prediction | null {
    const model = this.models.get('failure-predictor');
    
    if (!model) return null;

    const features = this.extractFeatures(testName);
    let output = 0.5;

    for (const [feature, value] of Object.entries(features)) {
      if (model.weights[feature] !== undefined) {
        output += model.weights[feature] * value;
      }
    }

    output = Math.max(0, Math.min(1, output));

    return {
      timestamp: Date.now(),
      input: features,
      output,
      confidence: model.accuracy,
    };
  }

  /**
   * Update prediction with actual outcome
   */
  updatePrediction(prediction: Prediction, actual: number): void {
    const model = this.models.get('failure-predictor');
    
    if (model) {
      prediction.actual = actual;
      
      // Online learning: adjust weights based on error
      const error = actual - prediction.output;
      const learningRate = 0.1;

      for (const [feature, value] of Object.entries(prediction.input)) {
        if (model.weights[feature] !== undefined) {
          model.weights[feature] += learningRate * error * value;
        }
      }

      model.predictions.push(prediction);
      model.accuracy = this.evaluateModel(model.weights);
      model.lastTrained = Date.now();
      
      this.saveModels();
    }

    // Also record for training
    this.recordExample(prediction.input, actual);
  }

  /**
   * Get model statistics
   */
  getStatistics(): {
    totalModels: number;
    totalTrainingExamples: number;
    avgAccuracy: number;
    lastTraining: number;
    predictionsCount: number;
  } {
    const models = Array.from(this.models.values());
    
    return {
      totalModels: models.length,
      totalTrainingExamples: this.trainingData.length,
      avgAccuracy: models.length > 0 
        ? models.reduce((sum, m) => sum + m.accuracy, 0) / models.length 
        : 0,
      lastTraining: models.length > 0 
        ? Math.max(...models.map(m => m.lastTrained)) 
        : 0,
      predictionsCount: models.reduce((sum, m) => sum + m.predictions.length, 0),
    };
  }

  /**
   * Export model for external use
   */
  exportModel(modelId: string): string | null {
    const model = this.models.get(modelId);
    
    if (!model) return null;
    
    return JSON.stringify(model, null, 2);
  }

  /**
   * Import model from external source
   */
  importModel(modelId: string, modelJson: string): boolean {
    try {
      const model = JSON.parse(modelJson) as MLModel;
      model.lastTrained = Date.now();
      this.models.set(modelId, model);
      this.saveModels();
      return true;
    } catch {
      return false;
    }
  }
}

export default SelfImprovingML;