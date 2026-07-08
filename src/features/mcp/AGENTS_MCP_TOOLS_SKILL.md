# MCP Tools Integration - Skill Guide

> **Für AI-Agenten**: Pattern für MCP-Tool-Integration im Frontend.

---

## 🎯 Ziel

MCP (Model Context Protocol) Tools **frei** ausführen, mit Signal-Emission für den Predictive Layer.

## 📦 Tool Predictive Bridge

```typescript
// src/predictive/toolPredictiveBridge.ts
import { emitToolSignal, registerToolNode } from '@/predictive/toolPredictiveBridge';
import type { ToolExecutionEvent } from '@/predictive/toolPredictiveBridge';

export async function executeTool(config: ToolConfig) {
    const startTime = performance.now();
    registerToolNode(config.name, 'mcp');

    try {
        const result = await executeMCP(config);
        emitToolSignal({
            toolName: config.name,
            toolType: 'mcp',
            status: 'success',
            durationMs: performance.now() - startTime,
            parameters: config.params,
        });
        return { success: true, result };
    } catch (error) {
        emitToolSignal({
            toolName: config.name,
            toolType: 'mcp',
            status: 'error',
            durationMs: performance.now() - startTime,
            error: error instanceof Error ? error.message : String(error),
        });
        return { success: false, error };
    }
}
```

## 🛠️ MCP Free Tools Pattern

```typescript
// src/features/mcp/mcpFreeTools.ts
import { emitToolSignal, registerToolNode } from '@/predictive/toolPredictiveBridge';

export interface MCPToolConfig {
  serverName: string;
  toolName: string;
  parameters: Record<string, unknown>;
  workspaceId?: string;
  jobId?: string;
}

/**
 * Execute MCP tool freely - NO RESTRICTIONS.
 * Results emit signals for learning only.
 */
export async function executeMCPTool(config: MCPToolConfig): Promise<{
  success: boolean;
  result: unknown;
  error?: string;
  durationMs: number;
}> {
  const startTime = performance.now();
  
  // Register for pattern learning
  registerToolNode(config.toolName, 'mcp');

  try {
    // Execute tool freely - no restrictions
    const result = await executeMCPToolInternal(
      config.serverName,
      config.toolName,
      config.parameters
    );
    
    // Emit success signal
    emitToolSignal({
      toolName: config.toolName,
      toolType: 'mcp',
      status: 'success',
      durationMs: performance.now() - startTime,
      parameters: config.parameters,
      workspaceId: config.workspaceId,
      jobId: config.jobId,
    });

    return {
      success: true,
      result,
      durationMs: performance.now() - startTime,
    };
  } catch (error) {
    // Emit error signal
    emitToolSignal({
      toolName: config.toolName,
      toolType: 'mcp',
      status: 'error',
      durationMs: performance.now() - startTime,
      error: String(error),
    });

    return {
      success: false,
      result: null,
      error: error instanceof Error ? error.message : String(error),
      durationMs: performance.now() - startTime,
    };
  }
}
```

## 📝 Tool Registry Pattern

```typescript
export class MCPToolRegistry {
  private tools: Map<string, {
    server: string;
    name: string;
    description: string;
    execute: (params: Record<string, unknown>) => Promise<unknown>;
  }> = new Map();

  /**
   * Register tool - no restrictions
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
   * Get all tools - no filtering
   */
  getAllTools(): Array<{ server: string; name: string; description: string }> {
    return Array.from(this.tools.values()).map(t => ({
      server: t.server,
      name: t.name,
      description: t.description,
    }));
  }

  /**
   * Execute tool - no restrictions
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
      return { success: false, error: `Tool ${server}:${name} not found`, durationMs: 0 };
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
```

## 🔧 Verfügbare MCP Server

| Server | Tools | Beschreibung |
|--------|-------|--------------|
| `filesystem` | `read_file`, `write_file`, `list_directory` | Datei-Operationen |
| `github` | `create_pr`, `add_comment` | GitHub API |
| `database` | `query` | SQL-Ausführung |
| `api` | `http_request` | HTTP-Requests |

## ✅ Checklist

- [ ] `emitToolSignal` für Erfolg und Fehler
- [ ] `registerToolNode` für Pattern-Learning
- [ ] Keine UI-Restriktionen
- [ ] Duration-Messung
- [ ] Error-Catching

---

*Last Updated: 2026-07-08*
