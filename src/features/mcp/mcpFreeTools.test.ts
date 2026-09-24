import { describe, expect, it, vi, beforeEach } from 'vitest';
import { executeMCPTool, MCPToolRegistry, getMCPToolRegistry, getAvailableMCPTools } from './mcpFreeTools';
import * as predictiveBridge from '@/predictive/toolPredictiveBridge';

vi.mock('@/predictive/toolPredictiveBridge', () => ({
  emitToolSignal: vi.fn(),
  registerToolNode: vi.fn(),
}));

describe('mcpFreeTools', () => {
  let registry: MCPToolRegistry;

  beforeEach(() => {
    vi.clearAllMocks();
    registry = getMCPToolRegistry();
    // clear internal tools
    // @ts-ignore
    registry.tools.clear();
  });

  it('registers and retrieves available tools', () => {
    registry.register('test-server', 'test-tool', 'Test Tool', async () => 'success');
    registry.register('test-server-2', 'test-tool-2', 'Test Tool 2', async () => 'success');

    const result = getAvailableMCPTools();

    expect(result.servers).toEqual(['test-server', 'test-server-2']);
    expect(result.tools).toHaveLength(2);
    expect(result.tools[0].server).toBe('test-server');
    expect(result.tools[0].name).toBe('test-tool');
  });

  it('executes tools successfully', async () => {
    const executeMock = vi.fn().mockResolvedValue('test-result');
    registry.register('test-server', 'test-tool', 'Test Tool', executeMock);

    const params = { foo: 'bar' };
    const result = await executeMCPTool({
      serverName: 'test-server',
      toolName: 'test-tool',
      parameters: params,
    });

    expect(result.success).toBe(true);
    expect(result.result).toBe('test-result');
    expect(executeMock).toHaveBeenCalledWith(params);

    expect(predictiveBridge.registerToolNode).toHaveBeenCalledWith('test-tool', 'mcp');
    expect(predictiveBridge.emitToolSignal).toHaveBeenCalledWith(
      expect.objectContaining({
        toolName: 'test-tool',
        status: 'success',
        parameters: params,
      })
    );
  });

  it('handles tool execution errors gracefully', async () => {
    const executeMock = vi.fn().mockRejectedValue(new Error('test error'));
    registry.register('test-server', 'test-tool', 'Test Tool', executeMock);

    const params = { foo: 'bar' };
    const result = await executeMCPTool({
      serverName: 'test-server',
      toolName: 'test-tool',
      parameters: params,
    });

    expect(result.success).toBe(false);
    expect(result.error).toBe('test error');

    expect(predictiveBridge.emitToolSignal).toHaveBeenCalledWith(
      expect.objectContaining({
        toolName: 'test-tool',
        status: 'error',
      })
    );
  });

  it('fails if tool is not registered', async () => {
    const params = { foo: 'bar' };
    const result = await executeMCPTool({
      serverName: 'unknown-server',
      toolName: 'unknown-tool',
      parameters: params,
    });

    expect(result.success).toBe(false);
    expect(result.error).toContain('MCP transport unavailable');
  });

  it('registry execute delegates to executeMCPTool', async () => {
      const executeMock = vi.fn().mockResolvedValue('test-result');
      registry.register('test-server', 'test-tool', 'Test Tool', executeMock);

      const params = { foo: 'bar' };
      const result = await registry.execute('test-server', 'test-tool', params);

      expect(result.success).toBe(true);
      expect(result.result).toBe('test-result');
      expect(executeMock).toHaveBeenCalledWith(params);
  })
});
