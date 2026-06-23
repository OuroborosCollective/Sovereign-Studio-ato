/**
 * Error Computer
 *
 * Prediction error computation module for the predictive coding layer.
 * Computes the error ε(t) = x(t) - x̂(t) and determines whether
 * errors should propagate through the network.
 *
 * Mathematical Foundation:
 * - Prediction Error: ε(t) = x(t) - x̂(t)
 * - Absolute Error: |ε(t)| = |x(t) - x̂(t)|
 * - Propagated if: |ε(t)| > threshold
 *
 * @module predictive/errorComputer
 */

import type {
  Signal,
  Prediction,
  PredictionError,
  TraceId,
  PredictiveLayerConfig,
} from './types';

import { DEFAULT_PREDICTIVE_CONFIG } from './types';

// ============================================================================
// Sequence Counter
// ============================================================================

let errorSequence = 0;

function generateErrorId(): string {
  errorSequence = (errorSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `err-${errorSequence.toString(36).padStart(8, '0')}`;
}

// ============================================================================
// Error Computer
// ============================================================================

export interface ErrorComputerConfig {
  /** Error propagation threshold */
  threshold: number;
  /** Weight factor for error magnitude */
  propagationWeight: number;
  /** Enable temporal error smoothing */
  temporalSmoothing: boolean;
  /** Smoothing window size */
  smoothingWindow: number;
}

export interface ErrorStats {
  totalErrors: number;
  propagatedErrors: number;
  suppressedErrors: number;
  averageError: number;
  averageAbsoluteError: number;
  maxError: number;
  minError: number;
}

/**
 * Computes prediction errors and determines error propagation.
 */
export class ErrorComputer {
  private threshold: number;
  private propagationWeight: number;
  private temporalSmoothing: boolean;
  private smoothingWindow: number;
  private errorHistory: Map<string, PredictionError[]> = new Map();
  private globalStats: ErrorStats;
  private config: ErrorComputerConfig;

  constructor(config: Partial<ErrorComputerConfig> = {}) {
    const defaultConfig: ErrorComputerConfig = {
      threshold: DEFAULT_PREDICTIVE_CONFIG.error.threshold,
      propagationWeight: DEFAULT_PREDICTIVE_CONFIG.error.propagationWeight,
      temporalSmoothing: true,
      smoothingWindow: 5,
      ...config,
    };

    this.threshold = defaultConfig.threshold;
    this.propagationWeight = defaultConfig.propagationWeight;
    this.temporalSmoothing = defaultConfig.temporalSmoothing;
    this.smoothingWindow = defaultConfig.smoothingWindow;
    this.config = defaultConfig;

    this.globalStats = this.createEmptyStats();
  }

  /**
   * Create empty stats object.
   */
  private createEmptyStats(): ErrorStats {
    return {
      totalErrors: 0,
      propagatedErrors: 0,
      suppressedErrors: 0,
      averageError: 0,
      averageAbsoluteError: 0,
      maxError: -Infinity,
      minError: Infinity,
    };
  }

  /**
   * Compute error for a signal-prediction pair.
   * ε(t) = x(t) - x̂(t)
   */
  computeError(
    signal: Signal,
    prediction: Prediction,
    traceId: TraceId,
  ): PredictionError {
    const actual = signal.value;
    const predicted = prediction.predictedValue;

    // Base error calculation
    let error = actual - predicted;

    // Apply temporal smoothing if enabled
    if (this.temporalSmoothing) {
      error = this.applyTemporalSmoothing(signal.node, error);
    }

    const absoluteError = Math.abs(error);

    // Determine if error should propagate
    const propagated = absoluteError + Number.EPSILON >= this.threshold;

    // Calculate error weight (higher for larger errors)
    const weight = this.calculateErrorWeight(absoluteError);

    const predictionError: PredictionError = {
      id: generateErrorId(),
      actual,
      predicted,
      error,
      absoluteError,
      propagated,
      node: signal.node,
      timestamp: Date.now(),
      traceId,
      weight,
    };

    // Store in history
    this.addToHistory(signal.node, predictionError);

    // Update global stats
    this.updateGlobalStats(predictionError);

    return predictionError;
  }

  /**
   * Apply temporal smoothing to reduce oscillation.
   * Uses exponential moving average.
   */
  private applyTemporalSmoothing(node: string, newError: number): number {
    const history = this.errorHistory.get(node);
    if (!history || history.length === 0) {
      return newError;
    }

    // Get recent errors
    const recentErrors = history.slice(-this.smoothingWindow);
    const alpha = 0.3; // Smoothing factor

    // Calculate weighted average
    const smoothedError = recentErrors.reduce((sum, e, i) => {
      const weight = Math.pow(alpha, recentErrors.length - 1 - i);
      return sum + e.error * weight;
    }, 0);

    const weightSum = recentErrors.reduce((sum, _, i) => {
      return sum + Math.pow(alpha, recentErrors.length - 1 - i);
    }, 0);

    const ema = smoothedError / weightSum;

    // Blend new error with EMA
    return 0.7 * newError + 0.3 * ema;
  }

  /**
   * Calculate error weight based on magnitude.
   * Larger errors get higher weights for learning.
   */
  private calculateErrorWeight(absoluteError: number): number {
    // Scale weight logarithmically to prevent extreme weights
    const logError = Math.log1p(absoluteError);
    const scaledWeight = Math.min(logError / 10, 1.0);
    return scaledWeight * this.propagationWeight;
  }

  /**
   * Store error in history.
   */
  private addToHistory(node: string, error: PredictionError): void {
    const history = this.errorHistory.get(node) ?? [];
    history.push(error);

    // Keep last 100 errors per node
    if (history.length > 100) {
      history.shift();
    }

    this.errorHistory.set(node, history);
  }

  /**
   * Update global statistics.
   */
  private updateGlobalStats(error: PredictionError): void {
    const stats = this.globalStats;

    stats.totalErrors++;

    if (error.propagated) {
      stats.propagatedErrors++;
    } else {
      stats.suppressedErrors++;
    }

    // Update moving averages
    const n = stats.totalErrors;
    stats.averageError = (stats.averageError * (n - 1) + error.error) / n;
    stats.averageAbsoluteError = (stats.averageAbsoluteError * (n - 1) + error.absoluteError) / n;

    // Update min/max
    if (error.error > stats.maxError) stats.maxError = error.error;
    if (error.error < stats.minError) stats.minError = error.error;
  }

  /**
   * Get error history for a node.
   */
  getHistory(nodeId: string): PredictionError[] {
    return this.errorHistory.get(nodeId) ?? [];
  }

  /**
   * Get global statistics.
   */
  getStats(): ErrorStats {
    return { ...this.globalStats };
  }

  /**
   * Get error rate (propagated / total).
   */
  getErrorRate(): number {
    if (this.globalStats.totalErrors === 0) return 0;
    return this.globalStats.propagatedErrors / this.globalStats.totalErrors;
  }

  /**
   * Get suppression rate (suppressed / total).
   */
  getSuppressionRate(): number {
    if (this.globalStats.totalErrors === 0) return 0;
    return this.globalStats.suppressedErrors / this.globalStats.totalErrors;
  }

  /**
   * Reset all statistics.
   */
  reset(): void {
    this.errorHistory.clear();
    this.globalStats = this.createEmptyStats();
  }

  /**
   * Set propagation threshold.
   */
  setThreshold(threshold: number): void {
    this.threshold = Math.max(0, threshold);
  }

  /**
   * Get current threshold.
   */
  getThreshold(): number {
    return this.threshold;
  }

  /**
   * Batch compute errors for multiple signal-prediction pairs.
   */
  computeBatchErrors(
    pairs: Array<{ signal: Signal; prediction: Prediction }>,
    traceId: TraceId,
  ): PredictionError[] {
    return pairs.map(({ signal, prediction }) =>
      this.computeError(signal, prediction, traceId),
    );
  }

  /**
   * Filter errors that should propagate.
   */
  getPropagatedErrors(errors: PredictionError[]): PredictionError[] {
    return errors.filter((e) => e.propagated);
  }

  /**
   * Get errors above a specific threshold.
   */
  getErrorsAboveThreshold(errors: PredictionError[], threshold: number): PredictionError[] {
    return errors.filter((e) => e.absoluteError + Number.EPSILON >= threshold);
  }

  /**
   * Get recent errors with highest magnitude.
   */
  getTopErrors(nodeId: string, k: number = 10): PredictionError[] {
    const history = this.errorHistory.get(nodeId) ?? [];
    return [...history]
      .sort((a, b) => b.absoluteError - a.absoluteError)
      .slice(0, k);
  }
}

// ============================================================================
// Default Factory
// ============================================================================

export function createErrorComputer(
  config?: Partial<ErrorComputerConfig>,
): ErrorComputer {
  return new ErrorComputer(config);
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Calculate prediction accuracy from a set of errors.
 * Returns percentage of predictions within threshold.
 */
export function calculateAccuracy(errors: PredictionError[], threshold: number): number {
  if (errors.length === 0) return 0;
  const accurate = errors.filter((e) => e.absoluteError <= threshold).length;
  return accurate / errors.length;
}

/**
 * Calculate mean squared error (MSE).
 */
export function calculateMSE(errors: PredictionError[]): number {
  if (errors.length === 0) return 0;
  const sumSquared = errors.reduce((sum, e) => sum + e.error * e.error, 0);
  return sumSquared / errors.length;
}

/**
 * Calculate root mean squared error (RMSE).
 */
export function calculateRMSE(errors: PredictionError[]): number {
  return Math.sqrt(calculateMSE(errors));
}
