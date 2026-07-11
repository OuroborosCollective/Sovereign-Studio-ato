/**
 * Tool Predictive Bridge
 * 
 * Integrates the Sovereign Agent Tool System with the Predictive Layer.
 * Tool executions are emitted as signals for learning and prediction.
 * Prediction is advisory only and never grants execution permission.
 * 
 * @module predictive/toolPredictiveBridge
 */

import type { Signal } from './types';
import { getDefaultPredictiveLayer } from './predictiveLayer';

export interface ToolExecutionEvent {
  toolName: string;
  toolType: 'file' | 'git' | 'shell' | 'diff' | 'test' | 'mcp' | 'custom';
  status: 'success' | 'error' | 'blocked';
  durationMs: number;
  parameters: Record<string, unknown>;
  workspaceId?: string;
  jobId?: string;
  traceId?: string;
}

export interface ToolPredictiveConfig {
  enabled: boolean;
  emitSignals: boolean;
  learnFromResults: boolean;
  confidenceThreshold: number;
}

// Default configuration for evidence collection only.
const DEFAULT_CONFIG: ToolPredictiveConfig = {
  enabled: true,
  emitSignals: true,
  learnFromResults: true,
  confidenceThreshold: 0.5,
};

let bridgeConfig: ToolPredictiveConfig = { ...DEFAULT_CONFIG };

/**
 * Configure the tool-predictive bridge.
 * Tools remain unrestricted - this only controls signal emission.
 */
export function configureToolPredictiveBridge(config: Partial<ToolPredictiveConfig>): void {
  bridgeConfig = { ...bridgeConfig, ...config };
}

/**
 * Get current bridge configuration.
 */
export function getToolPredictiveConfig(): ToolPredictiveConfig {
  return { ...bridgeConfig };
}

/**
 * Emit a tool execution as a signal to the predictive layer.
 * Tool execution continues regardless of signal emission.
 */
export function emitToolSignal(event: ToolExecutionEvent): void {
  if (!bridgeConfig.enabled || !bridgeConfig.emitSignals) {
    return;
  }

  try {
    const layer = getDefaultPredictiveLayer();
    if (!layer.isEnabled()) {
      return;
    }

    // Map tool type to node namespace
    const nodeNamespace = `tool.${event.toolType}.${event.toolName}`;
    
    // Signal value based on outcome (1 = success, 0 = error/blocked)
    const value = event.status === 'success' ? 1 : 0;
    
    // Create a traceable telemetry signal without a random decision identity.
    const timestamp = Date.now();
    const traceId = event.traceId?.trim() || `tool-${event.toolType}-${event.toolName}-${timestamp}`;
    const signal: Signal = {
      id: `${traceId}:${event.status}:${Math.round(event.durationMs)}`,
      node: nodeNamespace,
      value,
      timestamp,
      traceId,
      metadata: {
        toolType: event.toolType,
        toolName: event.toolName,
        status: event.status,
        durationMs: event.durationMs,
        workspaceId: event.workspaceId,
        jobId: event.jobId,
        paramCount: Object.keys(event.parameters).length,
      },
    };

    // Emit asynchronously - don't block tool execution
    layer.emitSignal(nodeNamespace, value, signal.metadata);

    // Process synchronously for learning if enabled
    if (bridgeConfig.learnFromResults) {
      layer.processSignal(signal).catch(() => {
        // Silently ignore predictive errors - tool must succeed
      });
    }
  } catch {
    // Silently ignore bridge errors - tools work freely
  }
}

/**
 * Get tool execution predictions from the predictive layer.
 * Returns advisory predictions only - tools operate freely regardless.
 */
export async function getToolPredictions(
  toolType: string,
  toolName: string
): Promise<{
  predictedSuccessRate: number;
  avgDurationMs: number;
  confidence: number;
  recommendations: string[];
}> {
  const layer = getDefaultPredictiveLayer();
  
  if (!layer.isEnabled()) {
    return {
      predictedSuccessRate: 0,
      avgDurationMs: 0,
      confidence: 0,
      recommendations: ['Predictive Layer ist deaktiviert; keine Runtime-Evidence vorhanden.'],
    };
  }

  const nodeNamespace = `tool.${toolType}.${toolName}`;
  const patterns = layer
    .getLatentSpace()
    .findTopK(1, nodeNamespace, 5)
    .map((match) => match.pattern);

  if (patterns.length === 0) {
    return {
      predictedSuccessRate: 0,
      avgDurationMs: 0,
      confidence: 0,
      recommendations: ['Keine bestätigten historischen Tool-Ergebnisse vorhanden.'],
    };
  }

  // Calculate success rate from patterns
  const successCount = patterns.filter(p => p.signalValue > 0.5).length;
  const predictedSuccessRate = successCount / patterns.length;
  
  // Calculate average confidence
  const avgConfidence = patterns.reduce((sum, p) => sum + p.avgConfidence, 0) / patterns.length;
  
  // Generate recommendations
  const recommendations: string[] = [];
  if (predictedSuccessRate < 0.5) {
    recommendations.push('Consider reviewing tool parameters');
  }
  if (avgConfidence < 0.3) {
    recommendations.push('Limited historical data for this tool');
  }

  return {
    predictedSuccessRate,
    // PatternEmbedding stores no measured duration. Do not synthesize one.
    avgDurationMs: 0,
    confidence: avgConfidence,
    recommendations,
  };
}

/**
 * Register a tool with the predictive layer for pattern learning.
 * Tools work freely regardless of registration.
 */
export function registerToolNode(
  toolName: string,
  toolType: 'file' | 'git' | 'shell' | 'diff' | 'test' | 'mcp' | 'custom'
): void {
  if (!bridgeConfig.enabled) {
    return;
  }

  try {
    const layer = getDefaultPredictiveLayer();
    if (!layer.isEnabled()) {
      return;
    }

    layer.registerNode({
      id: `tool.${toolType}.${toolName}`,
      name: `${toolType}:${toolName}`,
      activation: 0.5,
      previousActivation: 0,
      incomingSynapses: [],
      outgoingSynapses: [],
      signalHistory: [],
      predictionHistory: [],
      errorHistory: [],
      nodeType: 'sensor',
      lastActivity: Date.now(),
    });
  } catch {
    // Silently ignore - tool registration is optional
  }
}

/**
 * Create a tool execution wrapper that emits signals.
 * The wrapped tool executes normally - signals are advisory only.
 */
export function withToolSignals<T extends unknown[], R>(
  toolName: string,
  toolType: string,
  fn: (...args: T) => R
): (...args: T) => R {
  return (...args: T): R => {
    const startTime = performance.now();
    let result: R;
    let status: 'success' | 'error' = 'success';

    try {
      result = fn(...args);
      return result;
    } catch (error) {
      status = 'error';
      throw error;
    } finally {
      const durationMs = performance.now() - startTime;
      
      emitToolSignal({
        toolName,
        toolType: toolType as ToolExecutionEvent['toolType'],
        status,
        durationMs,
        parameters: { argCount: args.length },
      });
    }
  };
}

/**
 * Async version of tool signal wrapper.
 */
export function withToolSignalsAsync<T extends unknown[], R>(
  toolName: string,
  toolType: string,
  fn: (...args: T) => Promise<R>
): (...args: T) => Promise<R> {
  return async (...args: T): Promise<R> => {
    const startTime = performance.now();
    let status: 'success' | 'error' | 'blocked' = 'success';

    try {
      const result = await fn(...args);
      return result;
    } catch (error) {
      status = 'error';
      throw error;
    } finally {
      const durationMs = performance.now() - startTime;
      
      emitToolSignal({
        toolName,
        toolType: toolType as ToolExecutionEvent['toolType'],
        status,
        durationMs,
        parameters: { argCount: args.length },
      });
    }
  };
}

// Re-export tool execution types for convenience
export type { ToolExecutionEvent as ToolEvent };
