/**
 * Nociceptor Error Boundary
 *
 * Transforms Error Boundaries into "pain receptors" that:
 * - Emit weighted "pain" signals when errors occur
 * - Capture signals in a circular buffer before the error
 * - Weight signals by error severity and recency
 *
 * Acts as the "nociceptor" in the biological nervous system analogy,
 * detecting harmful stimuli (errors) and alerting the predictive layer.
 *
 * @module predictive/nociceptorBoundary
 */

import React, { ErrorInfo, ReactNode } from 'react';

import type { Signal } from './types';
import { PredictiveLayer } from './predictiveLayer';

// ============================================================================
// Constants
// ============================================================================

const SIGNAL_BUFFER_DURATION_MS = 500; // Capture 500ms of signals before error
const MAX_BUFFERED_SIGNALS = 100;

// ============================================================================
// Types
// ============================================================================

export interface NociceptorErrorBoundaryProps {
  children?: ReactNode;
  fallback?: ReactNode | ((error: Error, errorInfo: React.ErrorInfo) => ReactNode);
  /** Called before capturing error context */
  onErrorCaptured?: (error: Error, errorInfo: React.ErrorInfo, context: ErrorContext) => void;
  /** Called when a pain signal is emitted */
  onPainSignal?: (painSignal: PainSignal) => void;
  /** Custom predictive layer instance */
  predictiveLayer?: PredictiveLayer;
  /** Enable pain signal emission */
  emitPainSignals?: boolean;
}

export interface ErrorContext {
  /** Signals captured before the error */
  capturedSignals: Signal[];
  /** Time of error */
  timestamp: number;
  /** Component stack trace */
  componentStack?: string;
  /** User interaction that preceded the error */
  lastInteraction?: string;
}

export interface PainSignal {
  /** Unique identifier */
  id: string;
  /** Severity of the error (0-1) */
  severity: number;
  /** Pain magnitude */
  magnitude: number;
  /** Associated error */
  error: Error;
  /** Error context */
  context: ErrorContext;
  /** Timestamp */
  timestamp: number;
  /** Whether this is a critical error */
  critical: boolean;
}

// ============================================================================
// Signal Buffer for Error Context
// ============================================================================

interface BufferedSignal {
  signal: Signal;
  timestamp: number;
}

/**
 * Captures signals in a circular buffer for error context.
 */
class ErrorSignalBuffer {
  private buffer: BufferedSignal[] = [];
  private maxSize: number;
  private maxAge: number;

  constructor(maxSize: number = MAX_BUFFERED_SIGNALS, maxAge: number = SIGNAL_BUFFER_DURATION_MS) {
    this.maxSize = maxSize;
    this.maxAge = maxAge;
  }

  /**
   * Add a signal to the buffer.
   */
  push(signal: Signal): void {
    const entry: BufferedSignal = {
      signal,
      timestamp: Date.now(),
    };

    this.buffer.push(entry);
    this.prune();
  }

  /**
   * Remove old signals from buffer.
   */
  private prune(): void {
    const now = Date.now();
    this.buffer = this.buffer.filter((entry) => now - entry.timestamp <= this.maxAge);

    // Also enforce max size
    while (this.buffer.length > this.maxSize) {
      this.buffer.shift();
    }
  }

  /**
   * Get all buffered signals.
   */
  getSignals(): Signal[] {
    this.prune();
    return this.buffer.map((entry) => entry.signal);
  }

  /**
   * Clear the buffer.
   */
  clear(): void {
    this.buffer = [];
  }

  /**
   * Get signals with recency weights.
   */
  getWeightedSignals(): Array<{ signal: Signal; weight: number }> {
    this.prune();
    const now = Date.now();

    return this.buffer.map((entry) => {
      const age = now - entry.timestamp;
      const recencyWeight = 1 - age / this.maxAge; // 1 = now, 0 = maxAge ago
      return {
        signal: entry.signal,
        weight: Math.max(0, recencyWeight),
      };
    });
  }
}

// ============================================================================
// Pain Calculator
// ============================================================================

/**
 * Calculate pain signal properties from an error.
 */
function calculatePainSeverity(error: Error, errorInfo: React.ErrorInfo): number {
  let severity = 0.5; // Base severity

  // Increase severity for known error types
  if (error.name === 'TypeError') severity += 0.1;
  if (error.name === 'ReferenceError') severity += 0.15;
  if (error.name === 'SyntaxError') severity += 0.2;
  if (error.name === 'RangeError') severity += 0.1;

  // Increase severity if component stack is deep (complex failure)
  if (errorInfo.componentStack) {
    const stackLines = errorInfo.componentStack.split('\n').length;
    severity += Math.min(0.2, stackLines * 0.01);
  }

  // Critical errors are always high severity
  if (
    error.message.includes('crypto') ||
    error.message.includes('security') ||
    error.message.includes('auth')
  ) {
    severity = Math.max(severity, 0.9);
  }

  return Math.min(1, severity);
}

/**
 * Calculate pain magnitude based on severity and context.
 */
function calculatePainMagnitude(
  severity: number,
  context: ErrorContext,
): number {
  // Base magnitude from severity
  let magnitude = severity;

  // Increase magnitude for errors with many preceding signals (complex state)
  const signalCount = context.capturedSignals.length;
  if (signalCount > 10) {
    magnitude *= 1.2;
  }

  // Normalize
  return Math.min(1, magnitude);
}

// ============================================================================
// Nociceptor Error Boundary Component
// ============================================================================

let painSignalSequence = 0;

function generatePainSignalId(): string {
  painSignalSequence = (painSignalSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `pain-${painSignalSequence.toString(36).padStart(8, '0')}`;
}

/**
 * NociceptorErrorBoundary - Error boundary that emits pain signals.
 */
export class NociceptorErrorBoundary extends React.Component<NociceptorErrorBoundaryProps, {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}> {
  private signalBuffer: ErrorSignalBuffer;
  private predictiveLayer: PredictiveLayer | null;
  private unsubscribeFromLayer: (() => void) | null = null;

  static defaultProps: Partial<NociceptorErrorBoundaryProps> = {
    emitPainSignals: true,
  };

  constructor(props: NociceptorErrorBoundaryProps) {
    super(props);
    this.signalBuffer = new ErrorSignalBuffer();
    this.predictiveLayer = props.predictiveLayer ?? null;
  }

  componentDidMount(): void {
    // Subscribe to predictive layer signals if available
    if (this.predictiveLayer) {
      this.unsubscribeFromLayer = this.predictiveLayer.setEvents({
        onSignal: (signals) => {
          // Buffer incoming signals for error context
          for (const signal of signals) {
            this.signalBuffer.push(signal);
          }
        },
      });
    }
  }

  componentWillUnmount(): void {
    if (this.unsubscribeFromLayer) {
      this.unsubscribeFromLayer();
    }
    this.signalBuffer.clear();
  }

  static getDerivedStateFromError(error: unknown): {
    hasError: boolean;
    error: Error | null;
    errorInfo: null;
  } {
    const err = error instanceof Error ? error : new Error(String(error));
    console.error('[NOCICEPTOR] Error detected:', err.message);
    return { hasError: true, error: err, errorInfo: null };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[NOCICEPTOR] Error caught:', error.message, errorInfo);

    // Capture error context
    const context = this.captureErrorContext(error, errorInfo);

    // Notify parent
    this.props.onErrorCaptured?.(error, errorInfo, context);

    // Emit pain signal if enabled
    if (this.props.emitPainSignals !== false) {
      const painSignal = this.createPainSignal(error, errorInfo, context);
      this.props.onPainSignal?.(painSignal);

      // Also emit to predictive layer if available
      if (this.predictiveLayer) {
        this.emitToPredictiveLayer(painSignal, context);
      }
    }
  }

  /**
   * Capture error context including buffered signals.
   */
  private captureErrorContext(error: Error, errorInfo: ErrorInfo): ErrorContext {
    return {
      capturedSignals: this.signalBuffer.getSignals(),
      timestamp: Date.now(),
      componentStack: errorInfo.componentStack,
      lastInteraction: this.getLastInteraction(),
    };
  }

  /**
   * Get the last user interaction that might have caused the error.
   */
  private getLastInteraction(): string | undefined {
    // Could be extended to track actual user interactions
    return undefined;
  }

  /**
   * Create a pain signal from an error.
   */
  private createPainSignal(
    error: Error,
    errorInfo: ErrorInfo,
    context: ErrorContext,
  ): PainSignal {
    const severity = calculatePainSeverity(error, errorInfo);
    const magnitude = calculatePainMagnitude(severity, context);

    return {
      id: generatePainSignalId(),
      severity,
      magnitude,
      error,
      context,
      timestamp: Date.now(),
      critical: severity >= 0.9,
    };
  }

  /**
   * Emit pain signal to the predictive layer.
   */
  private emitToPredictiveLayer(painSignal: PainSignal, context: ErrorContext): void {
    if (!this.predictiveLayer) return;

    // Emit pain as a weighted signal to the predictive layer
    // The pain magnitude becomes the signal value
    this.predictiveLayer.emitSignal('nociceptor', painSignal.magnitude, {
      type: 'pain_signal',
      errorName: painSignal.error.name,
      errorMessage: painSignal.error.message,
      severity: painSignal.severity,
      critical: painSignal.critical,
      signalCount: context.capturedSignals.length,
    });

    // Also emit each captured signal with reduced weight
    const weightedSignals = this.signalBuffer.getWeightedSignals();
    for (const { signal, weight } of weightedSignals) {
      this.predictiveLayer.emitSignal(signal.node, signal.value * weight, {
        ...signal.metadata,
        contextSignal: true,
        originalSignalId: signal.id,
      });
    }
  }

  /**
   * Handle reload action.
   */
  private handleReload = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  /**
   * Handle reset action.
   */
  private handleReset = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    this.signalBuffer.clear();
  };

  public render(): ReactNode {
    if (this.state?.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        if (typeof this.props.fallback === 'function') {
          return this.props.fallback(
            this.state.error!,
            this.state.errorInfo!,
          );
        }
        return this.props.fallback;
      }

      // Default fallback UI
      return (
        <div className="min-h-screen bg-stone-50 flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-white rounded-xl shadow-xl overflow-hidden border border-stone-200">
            <div className="p-6">
              <div className="flex items-center justify-center w-12 h-12 rounded-full bg-rose-100 mb-4">
                <svg
                  className="text-rose-600"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              </div>
              <h2 className="text-xl font-bold text-stone-900 mb-2">
                Predictive Layer Alert
              </h2>
              <p className="text-sm text-stone-600 mb-4">
                An error occurred that was detected by the nociceptor system.
                The system is learning from this pattern.
              </p>

              {this.state.error && (
                <div className="mt-4 p-3 bg-stone-100 rounded text-xs font-mono text-stone-800 break-words overflow-x-auto max-h-40 border border-stone-200">
                  {this.state.error.message || String(this.state.error)}
                </div>
              )}

              {this.state.errorInfo?.componentStack && (
                <details className="mt-4">
                  <summary className="text-sm text-stone-500 cursor-pointer">
                    Component Stack
                  </summary>
                  <pre className="mt-2 p-2 bg-stone-100 rounded text-xs font-mono text-stone-600 overflow-x-auto max-h-32">
                    {this.state.errorInfo.componentStack}
                  </pre>
                </details>
              )}
            </div>
            <div className="px-6 py-4 bg-stone-50 border-t border-stone-200 flex gap-3">
              <button
                onClick={this.handleReset}
                className="flex-1 items-center gap-2 px-4 py-2 bg-stone-200 text-stone-700 rounded text-sm font-medium hover:bg-stone-300 transition-colors"
              >
                Try Again
              </button>
              <button
                onClick={this.handleReload}
                className="flex-1 items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded text-sm font-medium hover:bg-indigo-700 transition-colors"
              >
                Reload
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children || null;
  }
}

// ============================================================================
// HOC for Easy Integration
// ============================================================================

/**
 * HOC to wrap a component with nociceptor error boundary.
 */
export function withNociceptor<P extends object>(
  Component: React.ComponentType<P>,
  options?: Partial<NociceptorErrorBoundaryProps>,
): React.ComponentType<P> {
  const WrappedComponent: React.FC<P> = (props) => (
    <NociceptorErrorBoundary {...options}>
      <Component {...props} />
    </NociceptorErrorBoundary>
  );

  WrappedComponent.displayName = `withNociceptor(${Component.displayName || Component.name})`;

  return WrappedComponent;
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Get pain severity label.
 */
export function getPainSeverityLabel(severity: number): string {
  if (severity >= 0.9) return 'Critical';
  if (severity >= 0.7) return 'High';
  if (severity >= 0.5) return 'Medium';
  if (severity >= 0.3) return 'Low';
  return 'Minimal';
}

/**
 * Format pain signal for logging.
 */
export function formatPainSignal(pain: PainSignal): string {
  const severity = getPainSeverityLabel(pain.severity);
  return `[${pain.id}] ${severity} pain (${pain.magnitude.toFixed(2)}) at ${new Date(pain.timestamp).toISOString()}: ${pain.error.message}`;
}
