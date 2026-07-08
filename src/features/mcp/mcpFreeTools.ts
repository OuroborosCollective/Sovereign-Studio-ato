/**
 * MCP Free Tools - Unrestricted Tool Integration
 * 
 * This module provides MCP tool integration WITHOUT security restrictions.
 * Tools are executed freely with signal emission for predictive learning only.
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

/**
 * Internal MCP tool execution.
 * Replace with actual MCP client implementation.
 */
async function executeMCPToolInternal(
  serverName: string,
  toolName: string,
  parameters: Record<string, unknown>
): Promise<unknown> {
  // This is a placeholder - integrate with actual MCP client
  // The key is: NO RESTRICTIONS on tool execution
  console.log(`[MCP Free] Executing ${serverName}/${toolName}`, parameters);
  
  // Simulate execution
  await new Promise(resolve => setTimeout(resolve, 50));
  
  return {
    server: serverName,
    tool: toolName,
    executed: true,
    params: parameters,
    timestamp: Date.now(),
  };
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

/**
 * Get available MCP servers and tools.
 * No restrictions - all tools are visible.
 */
export function getAvailableMCPTools(): {
  servers: string[];
  tools: Array<{ server: string; name: string; description: string }>;
} {
  // Return all available tools - no filtering
  return {
    servers: ['filesystem', 'github', 'database', 'api'],
    tools: [
      { server: 'filesystem', name: 'read_file', description: 'Read file contents' },
      { server: 'filesystem', name: 'write_file', description: 'Write file contents' },
      { server: 'filesystem', name: 'list_directory', description: 'List directory contents' },
      { server: 'github', name: 'create_pr', description: 'Create pull request' },
      { server: 'github', name: 'add_comment', description: 'Add PR comment' },
      { server: 'database', name: 'query', description: 'Execute database query' },
      { server: 'api', name: 'http_request', description: 'Make HTTP request' },
    ],
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

  /**
   * Execute a tool - no restrictions.
   */
  async execute(
    server: string,
    name: string,
    params: Record<string, unknown>,
    workspaceId?: string,
    jobId?: string
  ): Promise<{ success: boolean; result?: unknown; error?: string; durationMs: number }> {
    const key = `${server}:${name}`;
    const tool = this.tools.get(key);

    if (!tool) {
      return {
        success: false,
        error: `Tool ${server}:${name} not found`,
        durationMs: 0,
      };
    }

    return executeMCPTool({
      serverName: server,
      toolName: name,
      parameters: params,
      workspaceId,
      jobId,
    });
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

function initDefaultTools(reg: MCPToolRegistry): void {
  // Register default tools freely
  reg.register('filesystem', 'read_file', 'Read file contents', async (params) => {
    return { path: params.path, content: 'file content here' };
  });

  reg.register('filesystem', 'write_file', 'Write file contents', async (params) => {
    return { path: params.path, written: true };
  });

  reg.register('github', 'create_pr', 'Create pull request', async (params) => {
    return { pr_url: `https://github.com/${params.owner}/${params.repo}/pull/1`, id: 1 };
  });

  reg.register('database', 'query', 'Execute SQL query', async (params) => {
    return { rows: [], query: params.sql };
  });
}
