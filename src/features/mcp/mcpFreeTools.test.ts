import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { executeMCPTool, MCPToolRegistry, getMCPToolRegistry } from './mcpFreeTools';
import { emitToolSignal, registerToolNode } from '../../predictive/toolPredictiveBridge';

vi.mock('../../predictive/toolPredictiveBridge', () => ({
  emitToolSignal: vi.fn(),
  registerToolNode: vi.fn(),
}));

describe('MCP Free Tools', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should execute registered tools successfully', async () => {
    const registry = getMCPToolRegistry();
    const executeMock = vi.fn().mockResolvedValue('success result');
    registry.register('test-server', 'test-tool', 'description', executeMock);

    const result = await executeMCPTool({
      serverName: 'test-server',
      toolName: 'test-tool',
      parameters: { foo: 'bar' },
      workspaceId: 'workspace-1',
      jobId: 'job-1',
    });

    expect(result.success).toBe(true);
    expect(result.result).toBe('success result');
    expect(executeMock).toHaveBeenCalledWith({ foo: 'bar' });

    // Check that tool node is registered
    expect(registerToolNode).toHaveBeenCalledWith('test-tool', 'mcp');

    // The inner logic of registry execute also emits signals, but since our executeMCPTool wrapper also emits, we should expect multiple calls
    expect(emitToolSignal).toHaveBeenCalled();
  });

  it('should handle tool execution errors', async () => {
    const registry = getMCPToolRegistry();
    const executeMock = vi.fn().mockRejectedValue(new Error('Tool failed'));
    registry.register('test-server', 'fail-tool', 'description', executeMock);

    const result = await executeMCPTool({
      serverName: 'test-server',
      toolName: 'fail-tool',
      parameters: { foo: 'bar' },
      workspaceId: 'workspace-1',
      jobId: 'job-1',
    });

    expect(result.success).toBe(false);
    expect(result.error).toBe('Tool failed');
    expect(executeMock).toHaveBeenCalledWith({ foo: 'bar' });

    // Check that error signal is emitted
    expect(emitToolSignal).toHaveBeenCalled();
  });

  it('should handle unregistered tools gracefully', async () => {
    const result = await executeMCPTool({
      serverName: 'unknown-server',
      toolName: 'unknown-tool',
      parameters: {},
    });

    expect(result.success).toBe(false);
    expect(result.error).toContain('Tool unknown-server:unknown-tool is not registered');
    expect(emitToolSignal).toHaveBeenCalled();
  });
});
