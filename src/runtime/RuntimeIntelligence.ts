/**
 * Runtime Intelligence Library
 *
 * Central runtime intelligence layer for:
 * - Container decision making
 * - Bridge validation between containers
 * - Pattern matching and learning side-channel
 * - Telemetry and observability
 * - Guard chains for runtime validation
 * - Circuit breaker isolation
 * - Runtime health snapshots
 *
 * Rule decisions remain sourced from the real runtime rule grammar.
 * Learning and telemetry are side-channel intelligence, never fake truth.
 *
 * @module runtime/RuntimeIntelligence
 */

import { useCallback, useEffect, useState } from 'react';

import {
  decideContainerAction,
  type ContainerDecision,
  type ContainerDecisionRule,
} from '../features/product/runtime/containerDecisionGrammar';

import {
  assertContainerIntelligenceCoverageValid,
  buildContainerIntelligenceCoverageReport,
  CONTAINER_INTELLIGENCE_COVERAGE,
  listContainerIntelligenceGaps,
  type ContainerIntelligenceCoverageEntry,
  type ContainerIntelligenceCoverageReport,
} from '../features/product/runtime/containerIntelligenceCoverage';

import {
  validateFullPipeline,
  type FullPipelineBridge as ImportedFullPipelineBridge,
} from '../features/product/runtime/containerBridgeValidation';

import {
  applyContainerDecisionOutcome,
  getContainerDecisionLearningHistory,
  getContainerDecisionLearningStats,
  type ContainerDecisionLearningSignal,
} from '../features/product/runtime/containerDecisionLearning';

import {
  matchMobileWorkflowPattern,
  MOBILE_WORKFLOW_PATTERN_RULES,
  type MobileWorkflowPatternMatch,
} from '../mobile-workflow-pattern-rules';

export type { FullPipelineBridge } from '../features/product/runtime/containerBridgeValidation';

type FullPipelineBridge = ImportedFullPipelineBridge;

// ============================================================================
// Core Types
// ============================================================================

export type TraceId = string;

export interface TraceIdProvider {
  (): TraceId;
}

export interface RuntimeContext {
  traceId: TraceId;
  timestamp: number;
  containerId?: string;
  operationId?: string;
}

export interface RuntimeDecisionAlternative {
  ruleId: string;
  matchedSignals: string[];
  score: number;
}

export interface RuntimeDecisionExplanation {
  winningRuleId?: string;
  matchedSignals: string[];
  alternatives: RuntimeDecisionAlternative[];
  confidenceReason: string;
  inputTruncated: boolean;
  inputLength: number;
  normalizedInputLength: number;
}

export interface RuntimeLearningInfluence {
  recommendation: 'confirm' | 'caution' | 'insufficient-data';
  matchingSignals: number;
  accepted: number;
  rejected: number;
  confidenceDelta: number;
  reason: string;
}

export interface RuntimeDecision {
  decision: ContainerDecision;
  context: RuntimeContext;
  confidence: number;
  matchedSignals: string[];
  explanation: RuntimeDecisionExplanation;
  learningInfluence: RuntimeLearningInfluence;
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

export interface Guard {
  name: string;
  check: (ctx: RuntimeContext & Record<string, unknown>) => Promise<RuntimeGuardResult>;
}

export interface GuardChainConfig {
  preFlight: Guard[];
  main: Guard[];
  postFlight: Guard[];
  timeoutMs?: number;
  failFast?: boolean;
}

export interface RuntimeTelemetryConfig {
  enabled?: boolean;
  redactionEnabled?: boolean;
  consoleLogging?: boolean;
  maxEvents?: number;
  maxPropertyDepth?: number;
  maxStringLength?: number;
}

export interface RuntimeCircuitBreakerDefaults {
  threshold?: number;
  timeoutMs?: number;
}

export interface RuntimeIntelligenceConfig {
  telemetry?: RuntimeTelemetry;
  traceIdProvider?: TraceIdProvider;
  maxVisibleTextLength?: number;
  guardTimeoutMs?: number;
  circuitBreakerDefaults?: RuntimeCircuitBreakerDefaults;
}

export interface RuntimeGuardExecutionOptions {
  timeoutMs?: number;
}

export interface UseRuntimeIntelligenceOptions {
  autoTrack?: boolean;
  flushInterval?: number;
}

export type RuntimeCircuitBreakerState = 'closed' | 'open' | 'half-open';

export interface RuntimeCircuitBreakerSnapshot {
  name: string;
  state: RuntimeCircuitBreakerState;
  failures: number;
  threshold: number;
  timeoutMs: number;
  lastFailure: number;
  halfOpenProbeInFlight: boolean;
}

export interface RuntimeTelemetrySnapshot {
  enabled: boolean;
  bufferedEvents: number;
  droppedEvents: number;
  openTraces: number;
  maxEvents: number;
}

export interface RuntimeHealthSnapshot {
  status: 'green' | 'yellow' | 'red';
  traceId: TraceId;
  timestamp: number;
  telemetry: RuntimeTelemetrySnapshot;
  circuitBreakers: RuntimeCircuitBreakerSnapshot[];
  coverage: {
    valid: boolean;
    gaps: ContainerIntelligenceCoverageEntry[];
  };
  learning: {
    totalSignals: number;
    accepted: number;
    rejected: number;
  };
  reasons: string[];
}

interface NormalizedRuntimeText {
  text: string;
  rawLength: number;
  normalizedLength: number;
  truncated: boolean;
}

interface GuardRunOptions {
  timeoutMs: number;
  telemetry: RuntimeTelemetry;
}

// ============================================================================
// Runtime Constants
// ============================================================================

const DEFAULT_MAX_VISIBLE_TEXT_LENGTH = 60000;
const DEFAULT_GUARD_TIMEOUT_MS = 10000;
const DEFAULT_CIRCUIT_THRESHOLD = 5;
const DEFAULT_CIRCUIT_TIMEOUT_MS = 30000;
const DEFAULT_TELEMETRY_MAX_EVENTS = 1000;
const DEFAULT_TELEMETRY_MAX_PROPERTY_DEPTH = 12;
const DEFAULT_TELEMETRY_MAX_STRING_LENGTH = 20000;

let runtimeTraceSequence = 0;

// ============================================================================
// Runtime Clock / Trace Helpers
// ============================================================================

function runtimeNow(): number {
  return Date.now();
}

function runtimePerfNow(): number {
  const perf = globalThis.performance;
  return perf && typeof perf.now === 'function' ? perf.now() : runtimeNow();
}

/**
 * Default trace IDs are deterministic by call order.
 * Tests can inject a fixed TraceIdProvider for exact assertions.
 */
export function defaultTraceIdProvider(): TraceId {
  runtimeTraceSequence = (runtimeTraceSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `rt-${runtimeTraceSequence.toString(36).padStart(8, '0')}`;
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;

  try {
    return JSON.stringify(error);
  } catch {
    return 'Unknown runtime error';
  }
}

function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}

function normalizeVisibleText(input: unknown, maxLength: number): NormalizedRuntimeText {
  const raw = typeof input === 'string' ? input : String(input ?? '');
  const rawLength = raw.length;
  const truncated = rawLength > maxLength;
  const clipped = truncated ? raw.slice(0, maxLength) : raw;

  const text = clipped
    .replace(/\u0000/g, '')
    .replace(/\s+/g, ' ')
    .trim();

  return {
    text,
    rawLength,
    normalizedLength: text.length,
    truncated,
  };
}

// ============================================================================
// Telemetry Redaction
// ============================================================================

const REDACTION_PATTERNS: { pattern: RegExp; replacement: string }[] = [
  { pattern: /ghp_[a-zA-Z0-9]{36}/g, replacement: '[GITHUB_TOKEN]' },
  { pattern: /gho_[a-zA-Z0-9]{36}/g, replacement: '[GITHUB_TOKEN]' },
  { pattern: /ghu_[a-zA-Z0-9]{36}/g, replacement: '[GITHUB_TOKEN]' },
  { pattern: /github_pat_[a-zA-Z0-9_.]{22,}/g, replacement: '[GITHUB_TOKEN]' },
  { pattern: /ghs_[a-zA-Z0-9]{36}/g, replacement: '[GITHUB_TOKEN]' },
  { pattern: /ghr_[a-zA-Z0-9]{36}/g, replacement: '[GITHUB_TOKEN]' },
  { pattern: /AIza[a-zA-Z0-9_-]{30,}/g, replacement: '[GEMINI_KEY]' },
  { pattern: /sk-[a-zA-Z0-9_-]{20,}/g, replacement: '[AI_KEY]' },
  { pattern: /gsk_[a-zA-Z0-9_-]{20,}/g, replacement: '[GROQ_KEY]' },
  {
    pattern: /api[_-]?key["']?\s*[:=]\s*["']?[a-zA-Z0-9_-]{20,}/gi,
    replacement: 'api_key=[API_KEY]',
  },
  {
    pattern: /Bearer\s+[a-zA-Z0-9_+\-./=]{20,}/gi,
    replacement: 'Bearer [TOKEN]',
  },
  {
    pattern: /["']?(secret|password|passwd|pwd)["']?\s*[:=]\s*["']?[a-zA-Z0-9_@#$%^&*.\-]{8,}/gi,
    replacement: '[SECRET]',
  },
  {
    pattern: /authorization["']?\s*[:=]\s*["']?[a-zA-Z0-9_+\-./= ]+/gi,
    replacement: 'authorization: [REDACTED]',
  },
];

const SENSITIVE_KEY_PATTERN =
  /(^|_|-)(token|secret|password|passwd|pwd|auth|authorization|credential|apikey|api_key|privatekey|private_key)($|_|-)/i;

function redactSensitiveData(
  data: unknown,
  seen: WeakSet<object>,
  depth: number,
  maxDepth: number,
  maxStringLength: number,
): unknown {
  if (data === null || data === undefined) return data;

  if (depth > maxDepth) return '[MAX_DEPTH]';

  if (typeof data === 'string') {
    let result = data;

    for (const { pattern, replacement } of REDACTION_PATTERNS) {
      result = result.replace(pattern, replacement);
    }

    if (result.length > maxStringLength) {
      return `${result.slice(0, maxStringLength)}…[TRUNCATED]`;
    }

    return result;
  }

  if (typeof data === 'number' || typeof data === 'boolean' || typeof data === 'bigint') {
    return data;
  }

  if (data instanceof Date) {
    return data.toISOString();
  }

  if (Array.isArray(data)) {
    return data.map((item) =>
      redactSensitiveData(item, seen, depth + 1, maxDepth, maxStringLength),
    );
  }

  if (typeof data === 'object') {
    if (seen.has(data)) return '[CIRCULAR]';
    seen.add(data);

    const redacted: Record<string, unknown> = {};

    for (const [key, value] of Object.entries(data)) {
      redacted[key] = SENSITIVE_KEY_PATTERN.test(key)
        ? '[REDACTED]'
        : redactSensitiveData(value, seen, depth + 1, maxDepth, maxStringLength);
    }

    return redacted;
  }

  return String(data);
}

function sanitizeTelemetryProperties(
  properties: Record<string, unknown>,
  maxDepth: number,
  maxStringLength: number,
): Record<string, unknown> {
  const redacted = redactSensitiveData(
    properties,
    new WeakSet<object>(),
    0,
    maxDepth,
    maxStringLength,
  );

  return redacted && typeof redacted === 'object' && !Array.isArray(redacted)
    ? (redacted as Record<string, unknown>)
    : {};
}

// ============================================================================
// Telemetry Service
// ============================================================================

export class RuntimeTelemetry {
  private events: TelemetryEvent[] = [];
  private droppedEvents = 0;
  private readonly traceStack: Map<TraceId, { operation: string; startTime: number }> = new Map();
  private enabled: boolean;
  private readonly redactionEnabled: boolean;
  private readonly consoleLogging: boolean;
  private readonly maxEvents: number;
  private readonly maxPropertyDepth: number;
  private readonly maxStringLength: number;

  constructor(config: RuntimeTelemetryConfig = {}) {
    this.enabled = config.enabled ?? true;
    this.redactionEnabled = config.redactionEnabled ?? true;
    this.consoleLogging = config.consoleLogging ?? false;
    this.maxEvents = Math.max(1, config.maxEvents ?? DEFAULT_TELEMETRY_MAX_EVENTS);
    this.maxPropertyDepth = Math.max(
      1,
      config.maxPropertyDepth ?? DEFAULT_TELEMETRY_MAX_PROPERTY_DEPTH,
    );
    this.maxStringLength = Math.max(
      100,
      config.maxStringLength ?? DEFAULT_TELEMETRY_MAX_STRING_LENGTH,
    );
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  isEnabled(): boolean {
    return this.enabled;
  }

  track(event: TelemetryEvent): void {
    if (!this.enabled) return;

    const safeProperties = this.redactionEnabled
      ? sanitizeTelemetryProperties(event.properties, this.maxPropertyDepth, this.maxStringLength)
      : event.properties;

    const safeEvent: TelemetryEvent = {
      ...event,
      properties: safeProperties,
    };

    if (this.events.length >= this.maxEvents) {
      const removeCount = this.events.length - this.maxEvents + 1;
      this.events.splice(0, removeCount);
      this.droppedEvents += removeCount;
    }

    this.events.push(safeEvent);

    if (this.consoleLogging && typeof console !== 'undefined' && typeof console.debug === 'function') {
      console.debug(`[RuntimeIntel] ${safeEvent.name}`, {
        traceId: safeEvent.traceId,
        ...safeEvent.properties,
      });
    }
  }

  startTrace(traceId: TraceId, operation: string): void {
    this.traceStack.set(traceId, { operation, startTime: runtimePerfNow() });

    this.track({
      name: 'trace_started',
      properties: { operation },
      timestamp: runtimeNow(),
      traceId,
    });
  }

  endTrace(traceId: TraceId, success = true, error?: string): void {
    const entry = this.traceStack.get(traceId);
    if (!entry) return;

    const durationMs = Math.round(runtimePerfNow() - entry.startTime);

    this.track({
      name: 'trace_completed',
      properties: {
        operation: entry.operation,
        durationMs,
        success,
        error,
      },
      timestamp: runtimeNow(),
      traceId,
    });

    this.traceStack.delete(traceId);
  }

  peek(): TelemetryEvent[] {
    return [...this.events];
  }

  flush(): TelemetryEvent[] {
    const events = [...this.events];
    this.events = [];
    return events;
  }

  snapshot(): RuntimeTelemetrySnapshot {
    return {
      enabled: this.enabled,
      bufferedEvents: this.events.length,
      droppedEvents: this.droppedEvents,
      openTraces: this.traceStack.size,
      maxEvents: this.maxEvents,
    };
  }
}

const globalTelemetry = new RuntimeTelemetry();

// ============================================================================
// Circuit Breaker
// ============================================================================

export class RuntimeCircuitBreaker {
  private failures = 0;
  private lastFailure = 0;
  private state: RuntimeCircuitBreakerState = 'closed';
  private halfOpenProbeInFlight = false;
  private readonly safeThreshold: number;
  private readonly safeTimeoutMs: number;

  constructor(
    threshold = DEFAULT_CIRCUIT_THRESHOLD,
    timeoutMs = DEFAULT_CIRCUIT_TIMEOUT_MS,
    private readonly name = 'default',
    private readonly traceIdProvider: TraceIdProvider = defaultTraceIdProvider,
    private readonly telemetry: RuntimeTelemetry = globalTelemetry,
  ) {
    this.safeThreshold = Math.max(1, Math.floor(threshold));
    this.safeTimeoutMs = Math.max(1, Math.floor(timeoutMs));
  }

  async call<T>(fn: () => Promise<T>, inheritedTraceId?: TraceId): Promise<T> {
    const traceId = inheritedTraceId ?? this.traceIdProvider();

    if (this.state === 'open') {
      const canProbe = runtimeNow() - this.lastFailure > this.safeTimeoutMs;

      if (!canProbe) {
        this.telemetry.track({
          name: 'circuit_breaker_rejected',
          properties: { name: this.name, reason: 'open' },
          timestamp: runtimeNow(),
          traceId,
        });

        throw new Error(`Circuit breaker open for ${this.name}`);
      }

      if (this.halfOpenProbeInFlight) {
        this.telemetry.track({
          name: 'circuit_breaker_rejected',
          properties: { name: this.name, reason: 'half_open_probe_in_flight' },
          timestamp: runtimeNow(),
          traceId,
        });

        throw new Error(`Circuit breaker half-open probe already running for ${this.name}`);
      }

      this.state = 'half-open';
      this.halfOpenProbeInFlight = true;

      this.telemetry.track({
        name: 'circuit_breaker_half_open',
        properties: { name: this.name },
        timestamp: runtimeNow(),
        traceId,
      });
    }

    try {
      const result = await fn();

      this.failures = 0;
      this.state = 'closed';
      this.halfOpenProbeInFlight = false;

      this.telemetry.track({
        name: 'circuit_breaker_success',
        properties: { name: this.name },
        timestamp: runtimeNow(),
        traceId,
      });

      return result;
    } catch (error) {
      this.failures += 1;
      this.lastFailure = runtimeNow();
      this.halfOpenProbeInFlight = false;

      this.telemetry.track({
        name: 'circuit_breaker_failure',
        properties: {
          name: this.name,
          failures: this.failures,
          threshold: this.safeThreshold,
          error: toErrorMessage(error),
        },
        timestamp: runtimeNow(),
        traceId,
      });

      if (this.failures >= this.safeThreshold || this.state === 'half-open') {
        this.state = 'open';

        this.telemetry.track({
          name: 'circuit_breaker_opened',
          properties: { name: this.name },
          timestamp: runtimeNow(),
          traceId,
        });
      }

      throw error;
    }
  }

  getState(): RuntimeCircuitBreakerState {
    return this.state;
  }

  getFailureCount(): number {
    return this.failures;
  }

  reset(): void {
    this.failures = 0;
    this.lastFailure = 0;
    this.state = 'closed';
    this.halfOpenProbeInFlight = false;
  }

  snapshot(): RuntimeCircuitBreakerSnapshot {
    return {
      name: this.name,
      state: this.state,
      failures: this.failures,
      threshold: this.safeThreshold,
      timeoutMs: this.safeTimeoutMs,
      lastFailure: this.lastFailure,
      halfOpenProbeInFlight: this.halfOpenProbeInFlight,
    };
  }
}

// ============================================================================
// Guard Chain
// ============================================================================

function createGuardTimeoutResult(
  guardName: string,
  traceId: TraceId,
  timeoutMs: number,
  durationMs: number,
): RuntimeGuardResult {
  return {
    pass: false,
    guardName,
    traceId,
    durationMs,
    reason: `Guard timed out after ${timeoutMs}ms`,
    remediation: 'Reduce guard work, split the operation, or raise guardTimeoutMs explicitly.',
  };
}

async function runSingleGuard(
  guard: Guard,
  ctx: RuntimeContext & Record<string, unknown>,
  options: GuardRunOptions,
): Promise<RuntimeGuardResult> {
  const start = runtimePerfNow();

  let timeoutHandle: ReturnType<typeof setTimeout> | undefined;

  const timeoutPromise = new Promise<RuntimeGuardResult>((resolve) => {
    timeoutHandle = setTimeout(() => {
      resolve(
        createGuardTimeoutResult(
          guard.name,
          ctx.traceId,
          options.timeoutMs,
          Math.round(runtimePerfNow() - start),
        ),
      );
    }, options.timeoutMs);
  });

  const guardPromise = guard
    .check({ ...ctx })
    .then((result) => ({
      ...result,
      guardName: result.guardName || guard.name,
      traceId: result.traceId || ctx.traceId,
      durationMs: Math.round(runtimePerfNow() - start),
    }))
    .catch((error: unknown) => ({
      pass: false,
      guardName: guard.name,
      reason: toErrorMessage(error),
      remediation: 'Inspect guard implementation and runtime input.',
      traceId: ctx.traceId,
      durationMs: Math.round(runtimePerfNow() - start),
    }));

  const result = await Promise.race([guardPromise, timeoutPromise]);

  if (timeoutHandle !== undefined) {
    clearTimeout(timeoutHandle);
  }

  options.telemetry.track({
    name: 'guard_executed',
    properties: {
      guardName: result.guardName,
      pass: result.pass,
      durationMs: result.durationMs,
      reason: result.reason,
    },
    timestamp: runtimeNow(),
    traceId: ctx.traceId,
  });

  return result;
}

export async function runGuardChain(
  ctx: RuntimeContext,
  chain: GuardChainConfig,
  telemetry: RuntimeTelemetry = globalTelemetry,
): Promise<{ pass: boolean; results: RuntimeGuardResult[] }> {
  const orderedGuards = [...chain.preFlight, ...chain.main, ...chain.postFlight];
  const timeoutMs = Math.max(1, chain.timeoutMs ?? DEFAULT_GUARD_TIMEOUT_MS);
  const failFast = chain.failFast ?? true;
  const results: RuntimeGuardResult[] = [];

  telemetry.track({
    name: 'guard_chain_started',
    properties: {
      guardCount: orderedGuards.length,
      timeoutMs,
      failFast,
    },
    timestamp: runtimeNow(),
    traceId: ctx.traceId,
  });

  for (const guard of orderedGuards) {
    const result = await runSingleGuard(
      guard,
      { ...ctx },
      {
        timeoutMs,
        telemetry,
      },
    );

    results.push(result);

    if (!result.pass) {
      telemetry.track({
        name: 'guard_failed',
        properties: {
          guardName: result.guardName,
          reason: result.reason,
          remediation: result.remediation,
        },
        timestamp: runtimeNow(),
        traceId: ctx.traceId,
      });

      if (failFast) {
        return { pass: false, results };
      }
    }
  }

  const pass = results.every((result) => result.pass);

  telemetry.track({
    name: pass ? 'guard_chain_passed' : 'guard_chain_failed',
    properties: {
      totalGuards: results.length,
      failedGuards: results.filter((result) => !result.pass).length,
    },
    timestamp: runtimeNow(),
    traceId: ctx.traceId,
  });

  return { pass, results };
}

// ============================================================================
// Decision Explainability / Learning Side-Channel
// ============================================================================

function getMatchedSignals(visibleText: string, rule: ContainerDecisionRule): string[] {
  const lowerText = visibleText.toLowerCase();
  const signals = Array.isArray(rule.signals) ? rule.signals : [];

  return signals.filter((signal) => lowerText.includes(signal.toLowerCase()));
}

function buildDecisionAlternatives(
  visibleText: string,
  rules: ContainerDecisionRule[],
): RuntimeDecisionAlternative[] {
  return rules
    .map((rule) => {
      const matchedSignals = getMatchedSignals(visibleText, rule);

      return {
        ruleId: rule.id,
        matchedSignals,
        score: matchedSignals.length,
      };
    })
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);
}

function explainConfidence(confidence: number, matchedSignals: string[], inputTruncated: boolean): string {
  if (inputTruncated && matchedSignals.length === 0) {
    return 'Low confidence because input was truncated and no rule signal matched.';
  }

  if (matchedSignals.length === 0) {
    return 'Low confidence because no explicit rule signal matched.';
  }

  if (confidence >= 0.8) {
    return 'High confidence because the winning rule produced a strong score with matching signals.';
  }

  if (confidence >= 0.4) {
    return 'Medium confidence because at least one rule signal matched.';
  }

  return 'Low confidence because the rule score is weak.';
}

function readLearningOutcome(signal: ContainerDecisionLearningSignal): 'accepted' | 'rejected' | 'unknown' {
  const record = signal as unknown as Record<string, unknown>;

  if (record.accepted === true) return 'accepted';
  if (record.accepted === false) return 'rejected';

  const outcome = String(record.outcome ?? record.result ?? record.status ?? '').toLowerCase();

  if (['accepted', 'accept', 'success', 'confirmed', 'approved', 'true'].includes(outcome)) {
    return 'accepted';
  }

  if (['rejected', 'reject', 'failed', 'failure', 'denied', 'false'].includes(outcome)) {
    return 'rejected';
  }

  return 'unknown';
}

function buildLearningInfluence(
  containerId: string,
  decision: ContainerDecision,
): RuntimeLearningInfluence {
  const history = getContainerDecisionLearningHistory();
  const decisionAction = String(decision.action);

  const matching = history.filter((signal) => {
    const record = signal as unknown as Record<string, unknown>;
    return record.containerId === containerId && String(record.action) === decisionAction;
  });

  let accepted = 0;
  let rejected = 0;

  for (const signal of matching) {
    const outcome = readLearningOutcome(signal);
    if (outcome === 'accepted') accepted += 1;
    if (outcome === 'rejected') rejected += 1;
  }

  const known = accepted + rejected;

  if (known === 0) {
    return {
      recommendation: 'insufficient-data',
      matchingSignals: matching.length,
      accepted: 0,
      rejected: 0,
      confidenceDelta: 0,
      reason: 'No accepted/rejected learning history exists for this container/action pair.',
    };
  }

  const ratio = accepted / known;
  const confidenceDelta = clampNumber((ratio - 0.5) * 0.3, -0.15, 0.15);

  if (ratio >= 0.7) {
    return {
      recommendation: 'confirm',
      matchingSignals: matching.length,
      accepted,
      rejected,
      confidenceDelta,
      reason: 'Historical operator outcomes mostly accepted this container/action pair.',
    };
  }

  if (ratio <= 0.3) {
    return {
      recommendation: 'caution',
      matchingSignals: matching.length,
      accepted,
      rejected,
      confidenceDelta,
      reason: 'Historical operator outcomes mostly rejected this container/action pair.',
    };
  }

  return {
    recommendation: 'insufficient-data',
    matchingSignals: matching.length,
    accepted,
    rejected,
    confidenceDelta,
    reason: 'Historical outcomes are mixed and should not influence the truth path.',
  };
}

// ============================================================================
// Main Runtime Intelligence Class
// ============================================================================

export class RuntimeIntelligence {
  private readonly telemetry: RuntimeTelemetry;
  private readonly traceIdProvider: TraceIdProvider;
  private readonly circuitBreakers: Map<string, RuntimeCircuitBreaker> = new Map();
  private readonly maxVisibleTextLength: number;
  private readonly guardTimeoutMs: number;
  private readonly circuitBreakerDefaults: Required<RuntimeCircuitBreakerDefaults>;

  constructor(config: RuntimeIntelligenceConfig = {}) {
    this.telemetry = config.telemetry ?? globalTelemetry;
    this.traceIdProvider = config.traceIdProvider ?? defaultTraceIdProvider;
    this.maxVisibleTextLength = Math.max(
      1,
      config.maxVisibleTextLength ?? DEFAULT_MAX_VISIBLE_TEXT_LENGTH,
    );
    this.guardTimeoutMs = Math.max(1, config.guardTimeoutMs ?? DEFAULT_GUARD_TIMEOUT_MS);
    this.circuitBreakerDefaults = {
      threshold: config.circuitBreakerDefaults?.threshold ?? DEFAULT_CIRCUIT_THRESHOLD,
      timeoutMs: config.circuitBreakerDefaults?.timeoutMs ?? DEFAULT_CIRCUIT_TIMEOUT_MS,
    };
  }

  static createTraceId(): TraceId {
    return defaultTraceIdProvider();
  }

  decide(
    containerId: string,
    visibleText: string,
    rules: ContainerDecisionRule[] = [],
  ): RuntimeDecision {
    const traceId = this.traceIdProvider();
    const startTime = runtimePerfNow();
    const normalized = normalizeVisibleText(visibleText, this.maxVisibleTextLength);

    this.telemetry.track({
      name: 'container_decision_started',
      properties: {
        containerId,
        rawTextLength: normalized.rawLength,
        normalizedTextLength: normalized.normalizedLength,
        truncated: normalized.truncated,
        ruleCount: rules.length,
      },
      timestamp: runtimeNow(),
      traceId,
    });

    const decision = decideContainerAction(containerId, normalized.text, rules);
    const matchedSignals = this.extractMatchedSignals(decision, normalized.text, rules);
    const confidence = this.calculateConfidence(decision);
    const learningInfluence = buildLearningInfluence(containerId, decision);
    const alternatives = buildDecisionAlternatives(normalized.text, rules);
    const durationMs = Math.round(runtimePerfNow() - startTime);

    this.telemetry.track({
      name: 'container_decision_completed',
      properties: {
        containerId,
        decision: decision.action,
        lamp: decision.lamp,
        ruleId: decision.ruleId,
        score: decision.score,
        confidence,
        learningRecommendation: learningInfluence.recommendation,
        durationMs,
      },
      timestamp: runtimeNow(),
      traceId,
    });

    return {
      decision,
      context: {
        traceId,
        timestamp: runtimeNow(),
        containerId,
      },
      confidence,
      matchedSignals,
      explanation: {
        winningRuleId: decision.ruleId,
        matchedSignals,
        alternatives,
        confidenceReason: explainConfidence(confidence, matchedSignals, normalized.truncated),
        inputTruncated: normalized.truncated,
        inputLength: normalized.rawLength,
        normalizedInputLength: normalized.normalizedLength,
      },
      learningInfluence,
    };
  }

  matchMobilePattern(visibleText: string): MobileWorkflowPatternMatch {
    const traceId = this.traceIdProvider();
    const normalized = normalizeVisibleText(visibleText, this.maxVisibleTextLength);

    this.telemetry.track({
      name: 'mobile_pattern_matching',
      properties: {
        rawTextLength: normalized.rawLength,
        normalizedTextLength: normalized.normalizedLength,
        truncated: normalized.truncated,
      },
      timestamp: runtimeNow(),
      traceId,
    });

    const match = matchMobileWorkflowPattern(normalized.text, MOBILE_WORKFLOW_PATTERN_RULES);

    this.telemetry.track({
      name: 'mobile_pattern_matched',
      properties: {
        matched: Boolean(match),
      },
      timestamp: runtimeNow(),
      traceId,
    });

    return match;
  }

  validatePipeline(bridge: FullPipelineBridge): { overallValid: boolean; criticalErrors: string[] } {
    const traceId = this.traceIdProvider();

    this.telemetry.track({
      name: 'pipeline_validation_started',
      properties: {
        hasRepoToBuilder: Boolean(bridge.repoToBuilder),
        hasBuilderToWorkflow: Boolean(
          (bridge as unknown as Record<string, unknown>).builderToWorkflow,
        ),
      },
      timestamp: runtimeNow(),
      traceId,
    });

    const result = validateFullPipeline(bridge);

    this.telemetry.track({
      name: 'pipeline_validation_completed',
      properties: {
        valid: result.overallValid,
        errorCount: result.criticalErrors.length,
      },
      timestamp: runtimeNow(),
      traceId,
    });

    return result;
  }

  getCoverageReport(): ContainerIntelligenceCoverageReport {
    return buildContainerIntelligenceCoverageReport(CONTAINER_INTELLIGENCE_COVERAGE);
  }

  assertCoverageValid(): void {
    assertContainerIntelligenceCoverageValid();
  }

  getCoverageGaps(): ContainerIntelligenceCoverageEntry[] {
    return listContainerIntelligenceGaps(CONTAINER_INTELLIGENCE_COVERAGE);
  }

  addLearning(signal: Omit<ContainerDecisionLearningSignal, 'timestamp'>): void {
    const fullSignal: ContainerDecisionLearningSignal = {
      ...signal,
      timestamp: runtimeNow(),
    } as ContainerDecisionLearningSignal;

    applyContainerDecisionOutcome(fullSignal);

    this.telemetry.track({
      name: 'learning_signal_added',
      properties: {
        containerId: signal.containerId,
        action: signal.action,
      },
      timestamp: runtimeNow(),
      traceId: this.traceIdProvider(),
    });
  }

  getLearningStats(): { totalSignals: number; accepted: number; rejected: number } {
    const stats = getContainerDecisionLearningStats();

    return {
      totalSignals: stats.total,
      accepted: stats.accepted,
      rejected: stats.rejected,
    };
  }

  getRecentLearning(limit = 10): ContainerDecisionLearningSignal[] {
    return getContainerDecisionLearningHistory().slice(-Math.max(0, limit));
  }

  getCircuitBreaker(
    name: string,
    threshold = this.circuitBreakerDefaults.threshold,
    timeoutMs = this.circuitBreakerDefaults.timeoutMs,
  ): RuntimeCircuitBreaker {
    const existing = this.circuitBreakers.get(name);
    if (existing) return existing;

    const breaker = new RuntimeCircuitBreaker(
      threshold,
      timeoutMs,
      name,
      this.traceIdProvider,
      this.telemetry,
    );

    this.circuitBreakers.set(name, breaker);
    return breaker;
  }

  resetCircuitBreaker(name: string): void {
    this.circuitBreakers.get(name)?.reset();
  }

  getCircuitBreakerSnapshots(): RuntimeCircuitBreakerSnapshot[] {
    return Array.from(this.circuitBreakers.values()).map((breaker) => breaker.snapshot());
  }

  async withGuard<T>(
    name: string,
    fn: () => Promise<T>,
    guards: Guard[],
    options: RuntimeGuardExecutionOptions = {},
  ): Promise<{ result: T; guardResults: RuntimeGuardResult[] }> {
    const traceId = this.traceIdProvider();

    const ctx: RuntimeContext & Record<string, unknown> = {
      traceId,
      timestamp: runtimeNow(),
      operationId: name,
    };

    this.telemetry.startTrace(traceId, name);

    try {
      const guardResults: RuntimeGuardResult[] = [];
      const timeoutMs = Math.max(1, options.timeoutMs ?? this.guardTimeoutMs);

      for (const guard of guards) {
        const result = await runSingleGuard(guard, ctx, {
          timeoutMs,
          telemetry: this.telemetry,
        });

        guardResults.push(result);

        if (!result.pass) {
          this.telemetry.endTrace(traceId, false, result.reason);
          throw new RuntimeGuardError(name, result);
        }
      }

      const circuitBreaker = this.getCircuitBreaker(name);
      const result = await circuitBreaker.call(fn, traceId);

      this.telemetry.endTrace(traceId, true);

      return { result, guardResults };
    } catch (error) {
      this.telemetry.endTrace(traceId, false, toErrorMessage(error));
      throw error;
    }
  }

  async runGuardChain(
    ctx: RuntimeContext,
    chain: GuardChainConfig,
  ): Promise<{ pass: boolean; results: RuntimeGuardResult[] }> {
    return runGuardChain(
      ctx,
      {
        ...chain,
        timeoutMs: chain.timeoutMs ?? this.guardTimeoutMs,
      },
      this.telemetry,
    );
  }

  getRuntimeHealth(): RuntimeHealthSnapshot {
    const traceId = this.traceIdProvider();
    const reasons: string[] = [];

    let gaps: ContainerIntelligenceCoverageEntry[] = [];
    let coverageValid = true;

    try {
      gaps = this.getCoverageGaps();
      coverageValid = gaps.length === 0;
    } catch (error) {
      coverageValid = false;
      reasons.push(`Coverage check failed: ${toErrorMessage(error)}`);
    }

    if (!coverageValid) {
      reasons.push(`Coverage gaps detected: ${gaps.length}`);
    }

    const telemetrySnapshot = this.telemetry.snapshot();

    if (telemetrySnapshot.droppedEvents > 0) {
      reasons.push(`Telemetry dropped ${telemetrySnapshot.droppedEvents} event(s) because buffer is bounded.`);
    }

    if (telemetrySnapshot.openTraces > 0) {
      reasons.push(`Open traces detected: ${telemetrySnapshot.openTraces}`);
    }

    const circuitSnapshots = this.getCircuitBreakerSnapshots();
    const openBreakers = circuitSnapshots.filter((snapshot) => snapshot.state === 'open');
    const halfOpenBreakers = circuitSnapshots.filter((snapshot) => snapshot.state === 'half-open');

    if (openBreakers.length > 0) {
      reasons.push(`Open circuit breakers: ${openBreakers.map((snapshot) => snapshot.name).join(', ')}`);
    }

    if (halfOpenBreakers.length > 0) {
      reasons.push(
        `Half-open circuit breakers: ${halfOpenBreakers.map((snapshot) => snapshot.name).join(', ')}`,
      );
    }

    const learning = this.getLearningStats();

    const status: RuntimeHealthSnapshot['status'] =
      openBreakers.length > 0 || !coverageValid
        ? 'red'
        : reasons.length > 0 || halfOpenBreakers.length > 0
          ? 'yellow'
          : 'green';

    return {
      status,
      traceId,
      timestamp: runtimeNow(),
      telemetry: telemetrySnapshot,
      circuitBreakers: circuitSnapshots,
      coverage: {
        valid: coverageValid,
        gaps,
      },
      learning,
      reasons,
    };
  }

  flushTelemetry(): TelemetryEvent[] {
    return this.telemetry.flush();
  }

  peekTelemetry(): TelemetryEvent[] {
    return this.telemetry.peek();
  }

  private calculateConfidence(decision: ContainerDecision): number {
    const score = Number.isFinite(decision.score) ? decision.score : 0;
    return clampNumber(score / 5, 0, 1);
  }

  private extractMatchedSignals(
    decision: ContainerDecision,
    visibleText: string,
    rules: ContainerDecisionRule[],
  ): string[] {
    const rule = rules.find((candidate) => candidate.id === decision.ruleId);
    if (!rule) return [];

    return getMatchedSignals(visibleText, rule);
  }
}

// ============================================================================
// Runtime Guard Error
// ============================================================================

export class RuntimeGuardError extends Error {
  constructor(
    public readonly operation: string,
    public readonly result: RuntimeGuardResult,
  ) {
    super(`Guard failed for ${operation}: ${result.reason ?? 'unknown reason'}`);
    this.name = 'RuntimeGuardError';
  }
}

// ============================================================================
// Utility Functions
// ============================================================================

export function createRuntimeIntelligence(config?: RuntimeIntelligenceConfig): RuntimeIntelligence {
  return new RuntimeIntelligence(config);
}

export const runtimeIntelligence = new RuntimeIntelligence();

// ============================================================================
// Observable Wrapper for React
// ============================================================================

export function useRuntimeIntelligence(options: UseRuntimeIntelligenceOptions = {}) {
  const { autoTrack = true, flushInterval = 30000 } = options;
  const [instance] = useState(() => createRuntimeIntelligence());
  const [events, setEvents] = useState<TelemetryEvent[]>([]);
  const [health, setHealth] = useState<RuntimeHealthSnapshot>(() => instance.getRuntimeHealth());

  useEffect(() => {
    if (!autoTrack || flushInterval <= 0) return undefined;

    const interval = setInterval(() => {
      const flushed = instance.flushTelemetry();

      if (flushed.length > 0) {
        setEvents((previous) => [...previous, ...flushed].slice(-100));

        const posthog = typeof window !== 'undefined'
          ? (window as unknown as {
              posthog?: {
                capture: (name: string, props: Record<string, unknown>) => void;
              };
            }).posthog
          : undefined;

        if (posthog) {
          for (const event of flushed) {
            posthog.capture(event.name, {
              ...event.properties,
              traceId: event.traceId,
              timestamp: event.timestamp,
            });
          }
        }
      }

      setHealth(instance.getRuntimeHealth());
    }, flushInterval);

    return () => clearInterval(interval);
  }, [autoTrack, flushInterval, instance]);

  const decide = useCallback(
    (containerId: string, visibleText: string, rules: ContainerDecisionRule[] = []) => {
      return instance.decide(containerId, visibleText, rules);
    },
    [instance],
  );

  const matchMobilePattern = useCallback(
    (visibleText: string) => {
      return instance.matchMobilePattern(visibleText);
    },
    [instance],
  );

  const validatePipeline = useCallback(
    (bridge: FullPipelineBridge) => {
      return instance.validatePipeline(bridge);
    },
    [instance],
  );

  const getRuntimeHealth = useCallback(() => {
    const snapshot = instance.getRuntimeHealth();
    setHealth(snapshot);
    return snapshot;
  }, [instance]);

  const flush = useCallback(() => {
    return instance.flushTelemetry();
  }, [instance]);

  return {
    instance,
    decide,
    matchMobilePattern,
    validatePipeline,
    events,
    health,
    getRuntimeHealth,
    flush,
  };
      }
