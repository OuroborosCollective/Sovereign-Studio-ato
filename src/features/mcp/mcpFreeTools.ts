/**
 * MCP Tool Registry
 *
 * Only concretely registered executors may run. Missing transports and tools
 * fail closed; predictive signals report outcomes but never grant permission.
 *
 * @module features/mcp/mcpFreeTools
 */

import { emitToolSignal, registerToolNode } from '@/predictive/toolPredictiveBridge';
import type { ToolExecutionEvent } from '@/predictive/toolPredictiveBridge';

export interface MCPToolConfig {
  serverName: string;
  toolName: string;
  parameters: Record<string, unknown>;
  workspaceId?: string;
  jobId?: string;
}

/**
 * Execute an MCP tool freely - no restrictions.
 * Results are emitted as signals for learning only.
 */
export async function executeMCPTool(config: MCPToolConfig): Promise<{
  success: boolean;
  result: unknown;
  error?: string;
  durationMs: number;
}> {
  const startTime = performance.now();
  const { serverName, toolName, parameters, workspaceId, jobId } = config;

  // Register tool node for pattern learning
  registerToolNode(toolName, 'mcp');

  try {
    // Execute tool freely - no restrictions
    const result = await executeMCPToolInternal(serverName, toolName, parameters);
    const durationMs = performance.now() - startTime;

    // Emit success signal
    emitToolSignal(createToolEvent(toolName, 'success', durationMs, parameters, workspaceId, jobId));

    return {
      success: true,
      result,
      durationMs,
    };
  } catch (error) {
    const durationMs = performance.now() - startTime;

    // Emit error signal
    emitToolSignal(createToolEvent(
      toolName,
      'error',
      durationMs,
      parameters,
      workspaceId,
      jobId
    ));

    return {
      success: false,
      result: null,
      error: error instanceof Error ? error.message : String(error),
      durationMs,
    };
  }
}

async function executeMCPToolInternal(
  serverName: string,
  toolName: string,
  _parameters: Record<string, unknown>,
): Promise<never> {
  throw new Error(
    `MCP transport unavailable for ${serverName}/${toolName}. Register a concrete executor before use.`,
  );
}

function createToolEvent(
  toolName: string,
  status: ToolExecutionEvent['status'],
  durationMs: number,
  parameters: Record<string, unknown>,
  workspaceId?: string,
  jobId?: string
): ToolExecutionEvent {
  return {
    toolName,
    toolType: 'mcp',
    status,
    durationMs,
    parameters,
    workspaceId,
    jobId,
  };
}

export function getAvailableMCPTools(): {
  servers: string[];
  tools: Array<{ server: string; name: string; description: string }>;
} {
  const tools = getMCPToolRegistry().getAllTools();
  return {
    servers: [...new Set(tools.map(tool => tool.server))].sort(),
    tools,
  };
}

/**
 * MCP Tool Registry - freely accessible tools.
 */
export class MCPToolRegistry {
  private tools: Map<string, {
    server: string;
    name: string;
    description: string;
    execute: (params: Record<string, unknown>) => Promise<unknown>;
  }> = new Map();

  /**
   * Register a tool - no restrictions.
   */
  register(
    server: string,
    name: string,
    description: string,
    execute: (params: Record<string, unknown>) => Promise<unknown>
  ): void {
    const key = `${server}:${name}`;
    this.tools.set(key, { server, name, description, execute });
    registerToolNode(name, 'mcp');
  }

  /**
   * Get all tools - no filtering.
   */
  getAllTools(): Array<{ server: string; name: string; description: string }> {
    return Array.from(this.tools.values()).map(t => ({
      server: t.server,
      name: t.name,
      description: t.description,
    }));
  }

  async execute(
    server: string,
    name: string,
    params: Record<string, unknown>,
    workspaceId?: string,
    jobId?: string,
  ): Promise<{ success: boolean; result?: unknown; error?: string; durationMs: number }> {
    const key = `${server}:${name}`;
    const tool = this.tools.get(key);
    if (!tool) {
      return {
        success: false,
        error: `Tool ${server}:${name} is not registered`,
        durationMs: 0,
      };
    }

    const startedAt = performance.now();
    try {
      const result = await tool.execute(params);
      const durationMs = performance.now() - startedAt;
      emitToolSignal(createToolEvent(name, 'success', durationMs, params, workspaceId, jobId));
      return { success: true, result, durationMs };
    } catch (error) {
      const durationMs = performance.now() - startedAt;
      emitToolSignal(createToolEvent(name, 'error', durationMs, params, workspaceId, jobId));
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error),
        durationMs,
      };
    }
  }
}

// Singleton registry
let registry: MCPToolRegistry | null = null;

export function getMCPToolRegistry(): MCPToolRegistry {
  if (!registry) {
    registry = new MCPToolRegistry();
    initDefaultTools(registry);
  }
  return registry;
}

function initDefaultTools(_reg: MCPToolRegistry): void {
  // No live-path placeholders. Tools appear only after a real executor registers.
}
