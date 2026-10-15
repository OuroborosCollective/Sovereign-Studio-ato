import { describe, it, expect, vi, beforeEach } from 'vitest';
import { executeMCPTool, getMCPToolRegistry, getAvailableMCPTools } from '@/features/mcp/mcpFreeTools';
import * as predictiveBridge from '@/predictive/toolPredictiveBridge';

vi.mock('@/predictive/toolPredictiveBridge', () => ({
  emitToolSignal: vi.fn(),
  registerToolNode: vi.fn(),
}));

describe('mcpFreeTools', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const registry = getMCPToolRegistry();
    // @ts-ignore
    registry.tools.clear();
  });

  it('should register and execute a tool successfully', async () => {
    const registry = getMCPToolRegistry();
    const mockExecute = vi.fn().mockResolvedValue('success result');

    registry.register('test-server', 'test-tool', 'A test tool', mockExecute);

    const result = await executeMCPTool({
      serverName: 'test-server',
      toolName: 'test-tool',
      parameters: { key: 'value' },
    });

    expect(mockExecute).toHaveBeenCalledWith({ key: 'value' });
    expect(result.success).toBe(true);
    expect(result.result).toBe('success result');
    expect(predictiveBridge.emitToolSignal).toHaveBeenCalled();
  });

  it('should handle tool execution errors gracefully', async () => {
    const registry = getMCPToolRegistry();
    const mockExecute = vi.fn().mockRejectedValue(new Error('Tool failed'));

    registry.register('test-server', 'failing-tool', 'A failing tool', mockExecute);

    const result = await executeMCPTool({
      serverName: 'test-server',
      toolName: 'failing-tool',
      parameters: {},
    });

    expect(result.success).toBe(false);
    expect(result.error).toBe('Tool failed');
    expect(predictiveBridge.emitToolSignal).toHaveBeenCalled();
  });

  it('should fail if tool is not registered', async () => {
    const result = await executeMCPTool({
      serverName: 'unknown-server',
      toolName: 'unknown-tool',
      parameters: {},
    });

    expect(result.success).toBe(false);
    expect(result.error).toContain('MCP transport unavailable');
  });

  it('should list available tools', () => {
    const registry = getMCPToolRegistry();
    registry.register('server1', 'tool1', 'desc1', vi.fn());
    registry.register('server2', 'tool2', 'desc2', vi.fn());

    const available = getAvailableMCPTools();
    expect(available.servers).toEqual(['server1', 'server2']);
    expect(available.tools).toHaveLength(2);
  });
});
