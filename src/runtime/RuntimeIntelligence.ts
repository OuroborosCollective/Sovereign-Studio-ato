/**
 * Runtime Intelligence Library
 * 
 * A unified runtime system that orchestrates:
 * - Container decision making
 * - Bridge validation between containers
 * - Pattern matching and learning
 * - Telemetry and observability
 * - Guard chains for runtime validation
 * 
 * @module runtime/RuntimeIntelligence
 */

import { 
  decideContainerAction, 
  type ContainerDecision, 
  type ContainerDecisionRule,
  KNOWN_CONTAINER_IDS 
} from '../features/product/runtime/containerDecisionGrammar';

import { 
  buildContainerIntelligenceCoverageReport,
  assertContainerIntelligenceCoverageValid,
  listContainerIntelligenceGaps,
  type ContainerIntelligenceCoverageEntry,
  type ContainerIntelligenceCoverageReport,
  CONTAINER_INTELLIGENCE_COVERAGE
} from '../features/product/runtime/containerIntelligenceCoverage';

import {
  validateFullPipeline,
  type FullPipelineBridge,
  type BridgeValidationResult
} from '../features/product/runtime/containerBridgeValidation';

import {
  createContainerDecisionLearningSignal,
  getContainerDecisionLearningHistory,
  getContainerDecisionLearningStats,
  applyContainerDecisionOutcome,
  type ContainerDecisionLearningSignal
} from '../features/product/runtime/containerDecisionLearning';

import {
  MOBILE_WORKFLOW_PATTERN_RULES,
  matchMobileWorkflowPattern,
  type MobileWorkflowPatternMatch
} from '../mobile-workflow-pattern-rules';

// ============================================================================
// Core Types
// ============================================================================

export type TraceId = string;

export interface RuntimeContext {
  traceId: TraceId;
  timestamp: number;
  containerId?: string;
  operationId?: string;
}

export interface RuntimeDecision {
  decision: ContainerDecision;
  context: RuntimeContext;
  confidence: number;
  matchedSignals: string[];
}

export interface RuntimeGuardResult {
  pass: boolean;
  guardName: string;
  reason?: string;
  remediation?: string;
  traceId: TraceId;
  durationMs: number;
}

export interface TelemetryEvent {
  name: string;
  properties: Record<string, unknown>;
  timestamp: number;
  traceId: TraceId;
}

// ============================================================================
// Telemetry Service
// ============================================================================

class RuntimeTelemetry {
  private events: TelemetryEvent[] = [];
  private traceStack: Map<TraceId, { operation: string; startTime: number }> = new Map();

  constructor(private enabled = true) {}

  track(event: TelemetryEvent): void {
    if (!this.enabled) return;
    this.events.push(event);
    
    // Also log to console in development
    if (typeof window !== 'undefined' || process.env.NODE_ENV === 'development') {
      console.debug(`[RuntimeIntel] ${event.name}`, {
        traceId: event.traceId,
        ...event.properties
      });
    }
  }

  startTrace(traceId: TraceId, operation: string): void {
    this.traceStack.set(traceId, { operation, startTime: performance.now() });
    this.track({
      name: 'trace_started',
      properties: { operation },
      timestamp: Date.now(),
      traceId
    });
  }

  endTrace(traceId: TraceId, success = true, error?: string): void {
    const entry = this.traceStack.get(traceId);
    if (entry) {
      const duration = performance.now() - entry.startTime;
      this.track({
        name: 'trace_completed',
        properties: {
          operation: entry.operation,
          durationMs: Math.round(duration),
          success,
          error
        },
        timestamp: Date.now(),
        traceId
      });
      this.traceStack.delete(traceId);
    }
  }

  flush(): TelemetryEvent[] {
    const events = [...this.events];
    this.events = [];
    return events;
  }
}

const globalTelemetry = new RuntimeTelemetry();

// ============================================================================
// Circuit Breaker
// ============================================================================

export class RuntimeCircuitBreaker {
  private failures = 0;
  private lastFailure = 0;
  private state: 'closed' | 'open' | 'half-open' = 'closed';

  constructor(
    private threshold = 5,
    private timeoutMs = 30000,
    private name = 'default'
  ) {}

  async call<T>(fn: () => Promise<T>): Promise<T> {
    const traceId = generateTraceId();

    if (this.state === 'open') {
      if (Date.now() - this.lastFailure > this.timeoutMs) {
        globalTelemetry.track({
          name: 'circuit_breaker_half_open',
          properties: { name: this.name },
          timestamp: Date.now(),
          traceId
        });
        this.state = 'half-open';
      } else {
        globalTelemetry.track({
          name: 'circuit_breaker_rejected',
          properties: { name: this.name, reason: 'open' },
          timestamp: Date.now(),
          traceId
        });
        throw new Error(`Circuit breaker open for ${this.name}`);
      }
    }

    try {
      const result = await fn();
      this.failures = 0;
      this.state = 'closed';
      globalTelemetry.track({
        name: 'circuit_breaker_success',
        properties: { name: this.name },
        timestamp: Date.now(),
        traceId
      });
      return result;
    } catch (error) {
      this.failures++;
      this.lastFailure = Date.now();
      globalTelemetry.track({
        name: 'circuit_breaker_failure',
        properties: {
          name: this.name,
          failures: this.failures,
          threshold: this.threshold,
          error: (error as Error).message
        },
        timestamp: Date.now(),
        traceId
      });
      if (this.failures >= this.threshold) {
        this.state = 'open';
        globalTelemetry.track({
          name: 'circuit_breaker_opened',
          properties: { name: this.name },
          timestamp: Date.now(),
          traceId
        });
      }
      throw error;
    }
  }

  getState(): 'closed' | 'open' | 'half-open' {
    return this.state;
  }
}

// ============================================================================
// Guard Chain
// ============================================================================

export interface Guard {
  name: string;
  check: (ctx: RuntimeContext & Record<string, unknown>) => Promise<RuntimeGuardResult>;
}

export interface GuardChainConfig {
  preFlight: Guard[];
  main: Guard[];
  postFlight: Guard[];
}

export async function runGuardChain(
  ctx: RuntimeContext,
  chain: GuardChainConfig
): Promise<{ pass: boolean; results: RuntimeGuardResult[] }> {
  const results: RuntimeGuardResult[] = [];
  globalTelemetry.track({
    name: 'guard_chain_started',
    properties: { guardCount: chain.preFlight.length + chain.main.length + chain.postFlight.length },
    timestamp: Date.now(),
    traceId: ctx.traceId
  });

  for (const guard of [...chain.preFlight, ...chain.main, ...chain.postFlight]) {
    const start = performance.now();
    const result = await guard.check({ ...ctx });
    result.durationMs = Math.round(performance.now() - start);
    results.push(result);

    globalTelemetry.track({
      name: 'guard_executed',
      properties: {
        guardName: result.guardName,
        pass: result.pass,
        durationMs: result.durationMs
      },
      timestamp: Date.now(),
      traceId: ctx.traceId
    });

    if (!result.pass) {
      globalTelemetry.track({
        name: 'guard_failed',
        properties: { guardName: result.guardName, reason: result.reason },
        timestamp: Date.now(),
        traceId: ctx.traceId
      });
      return { pass: false, results };
    }
  }

  globalTelemetry.track({
    name: 'guard_chain_passed',
    properties: { totalGuards: results.length },
    timestamp: Date.now(),
    traceId: ctx.traceId
  });

  return { pass: true, results };
}

// ============================================================================
// Main Runtime Intelligence Class
// ============================================================================

export class RuntimeIntelligence {
  private telemetry: RuntimeTelemetry;
  private circuitBreakers: Map<string, RuntimeCircuitBreaker> = new Map();
  
  constructor(telemetry: RuntimeTelemetry = globalTelemetry) {
    this.telemetry = telemetry;
  }

  /**
   * Generate a unique trace ID
   */
  static createTraceId(): TraceId {
    return generateTraceId();
  }

  /**
   * Make a container decision based on visible text
   */
  decide(
    containerId: string,
    visibleText: string,
    rules: ContainerDecisionRule[]
  ): RuntimeDecision {
    const traceId = generateTraceId();
    const startTime = performance.now();
    
    this.telemetry.track({
      name: 'container_decision_started',
      properties: { containerId, textLength: visibleText.length },
      timestamp: Date.now(),
      traceId
    });

    const decision = decideContainerAction(containerId, visibleText, rules);
    const duration = performance.now() - startTime;

    this.telemetry.track({
      name: 'container_decision_completed',
      properties: {
        containerId,
        decision: decision.action,
        lamp: decision.lamp,
        confidence: decision.score,
        durationMs: Math.round(duration)
      },
      timestamp: Date.now(),
      traceId
    });

    return {
      decision,
      context: { traceId, timestamp: Date.now(), containerId },
      confidence: this.calculateConfidence(decision),
      matchedSignals: this.extractMatchedSignals(decision, visibleText, rules)
    };
  }

  /**
   * Match mobile workflow patterns
   */
  matchMobilePattern(visibleText: string): MobileWorkflowPatternMatch {
    const traceId = generateTraceId();
    
    this.telemetry.track({
      name: 'mobile_pattern_matching',
      properties: { textLength: visibleText.length },
      timestamp: Date.now(),
      traceId
    });

    return matchMobileWorkflowPattern(visibleText, MOBILE_WORKFLOW_PATTERN_RULES);
  }

  /**
   * Validate the full pipeline bridge
   */
  validatePipeline(bridge: FullPipelineBridge): { overallValid: boolean; criticalErrors: string[] } {
    const traceId = generateTraceId();
    
    this.telemetry.track({
      name: 'pipeline_validation_started',
      properties: { hasRepoToBuilder: !!bridge.repoToBuilder },
      timestamp: Date.now(),
      traceId
    });

    const result = validateFullPipeline(bridge);

    this.telemetry.track({
      name: 'pipeline_validation_completed',
      properties: { valid: result.overallValid, errorCount: result.criticalErrors.length },
      timestamp: Date.now(),
      traceId
    });

    return result;
  }

  /**
   * Get coverage report for all containers
   */
  getCoverageReport(): ContainerIntelligenceCoverageReport {
    return buildContainerIntelligenceCoverageReport(CONTAINER_INTELLIGENCE_COVERAGE);
  }

  /**
   * Assert coverage is valid
   */
  assertCoverageValid(): void {
    assertContainerIntelligenceCoverageValid();
  }

  /**
   * Get list of coverage gaps
   */
  getCoverageGaps(): ContainerIntelligenceCoverageEntry[] {
    return listContainerIntelligenceGaps(CONTAINER_INTELLIGENCE_COVERAGE);
  }

  /**
   * Add a learning signal
   */
  addLearning(signal: Omit<ContainerDecisionLearningSignal, 'timestamp'>): void {
    const fullSignal = { ...signal, timestamp: Date.now() } as ContainerDecisionLearningSignal;
    applyContainerDecisionOutcome(fullSignal);
    this.telemetry.track({
      name: 'learning_signal_added',
      properties: { containerId: signal.containerId, action: signal.action },
      timestamp: Date.now(),
      traceId: generateTraceId()
    });
  }

  /**
   * Get learning statistics
   */
  getLearningStats(): { totalSignals: number; accepted: number; rejected: number } {
    const stats = getContainerDecisionLearningStats();
    return {
      totalSignals: stats.total,
      accepted: stats.accepted,
      rejected: stats.rejected
    };
  }

  /**
   * Get recent learning signals
   */
  getRecentLearning(limit = 10): ContainerDecisionLearningSignal[] {
    return getContainerDecisionLearningHistory().slice(-limit);
  }

  /**
   * Get or create a circuit breaker
   */
  getCircuitBreaker(name: string, threshold = 5, timeoutMs = 30000): RuntimeCircuitBreaker {
    if (!this.circuitBreakers.has(name)) {
      this.circuitBreakers.set(name, new RuntimeCircuitBreaker(threshold, timeoutMs, name));
    }
    return this.circuitBreakers.get(name)!;
  }

  /**
   * Run a guarded operation with circuit breaker
   */
  async withGuard<T>(
    name: string,
    fn: () => Promise<T>,
    guards: Guard[]
  ): Promise<{ result: T; guardResults: RuntimeGuardResult[] }> {
    const traceId = generateTraceId();
    const ctx = { traceId, timestamp: Date.now(), containerId: undefined, operationId: undefined } as RuntimeContext & Record<string, unknown>;

    this.telemetry.startTrace(traceId, name);

    try {
      // Run pre-flight guards
      const guardResults: RuntimeGuardResult[] = [];
      for (const guard of guards) {
        const start = performance.now();
        const result = await guard.check(ctx);
        result.durationMs = Math.round(performance.now() - start);
        guardResults.push(result);
        
        if (!result.pass) {
          this.telemetry.endTrace(traceId, false, result.reason);
          throw new RuntimeGuardError(name, result);
        }
      }

      // Get circuit breaker and run operation
      const cb = this.getCircuitBreaker(name);
      const result = await cb.call(fn);

      this.telemetry.endTrace(traceId, true);
      
      return { result, guardResults };
    } catch (error) {
      this.telemetry.endTrace(traceId, false, (error as Error).message);
      throw error;
    }
  }

  /**
   * Flush telemetry events
   */
  flushTelemetry(): TelemetryEvent[] {
    return this.telemetry.flush();
  }

  // Private helpers
  private calculateConfidence(decision: ContainerDecision): number {
    return Math.min(1, decision.score / 5);
  }

  private extractMatchedSignals(
    decision: ContainerDecision,
    visibleText: string,
    rules: ContainerDecisionRule[]
  ): string[] {
    const rule = rules.find(r => r.id === decision.ruleId);
    if (!rule) return [];
    
    const lowerText = visibleText.toLowerCase();
    return rule.signals.filter(s => lowerText.includes(s.toLowerCase()));
  }
}

/**
 * Runtime Guard Error
 */
export class RuntimeGuardError extends Error {
  constructor(
    public readonly operation: string,
    public readonly result: RuntimeGuardResult
  ) {
    super(`Guard failed for ${operation}: ${result.reason}`);
    this.name = 'RuntimeGuardError';
  }
}

// ============================================================================
// Utility Functions
// ============================================================================

function generateTraceId(): TraceId {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Create a new RuntimeIntelligence instance
 */
export function createRuntimeIntelligence(telemetry?: RuntimeTelemetry): RuntimeIntelligence {
  return new RuntimeIntelligence(telemetry);
}

/**
 * Default singleton instance
 */
export const runtimeIntelligence = new RuntimeIntelligence();

// ============================================================================
// Observable Wrapper for React
// ============================================================================

import { useState, useEffect, useCallback } from 'react';

export interface UseRuntimeIntelligenceOptions {
  autoTrack?: boolean;
  flushInterval?: number;
}

export function useRuntimeIntelligence(options: UseRuntimeIntelligenceOptions = {}) {
  const { autoTrack = true, flushInterval = 30000 } = options;
  const [instance] = useState(() => createRuntimeIntelligence());
  const [events, setEvents] = useState<TelemetryEvent[]>([]);

  useEffect(() => {
    if (autoTrack && flushInterval > 0) {
      const interval = setInterval(() => {
        const flushed = instance.flushTelemetry();
        if (flushed.length > 0) {
          setEvents(prev => [...prev, ...flushed].slice(-100)); // Keep last 100
          
          // If PostHog is available, send events
          if (typeof window !== 'undefined' && 'posthog' in window) {
            flushed.forEach(event => {
              (window as unknown as { posthog: { capture: (name: string, props: Record<string, unknown>) => void } }).posthog.capture(event.name, {
                ...event.properties,
                traceId: event.traceId,
                timestamp: event.timestamp
              });
            });
          }
        }
      }, flushInterval);

      return () => clearInterval(interval);
    }
  }, [autoTrack, flushInterval, instance]);

  const decide = useCallback((containerId: string, visibleText: string, rules?: ContainerDecisionRule[]) => {
    return instance.decide(containerId, visibleText, rules || []);
  }, [instance]);

  const matchMobilePattern = useCallback((visibleText: string) => {
    return instance.matchMobilePattern(visibleText);
  }, [instance]);

  const validatePipeline = useCallback((bridge: FullPipelineBridge) => {
    return instance.validatePipeline(bridge);
  }, [instance]);

  return {
    instance,
    decide,
    matchMobilePattern,
    validatePipeline,
    events,
    flush: instance.flushTelemetry.bind(instance)
  };
}
