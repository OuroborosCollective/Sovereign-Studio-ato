import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useToolchain } from './useToolchain';
import { toolchainClient, ToolchainRequestError } from './toolchainClient';

vi.mock('./toolchainClient', () => ({
  ToolchainRequestError: class extends Error {
    type: string;
    constructor(message: string, type: string) {
      super(message);
      this.type = type;
    }
  },
  toolchainClient: {
    manifest: vi.fn(),
    invoke: vi.fn(),
  }
}));

describe('useToolchain', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads tools successfully on mount', async () => {
    const mockTools = [{ name: 'test-tool', description: 'A test tool', input_schema: {} }];
    (toolchainClient.manifest as any).mockResolvedValue({ tools: mockTools });

    const { result, unmount } = renderHook(() => useToolchain());

    expect(result.current.loading).toBe(true);

    // wait for useEffect
    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.serverOnline).toBe(true);
    expect(result.current.tools).toEqual(mockTools);
    expect(result.current.error).toBeNull();

    unmount();
  });

  it('handles server offline/error on mount', async () => {
    (toolchainClient.manifest as any).mockRejectedValue(new Error('Network offline'));

    const { result } = renderHook(() => useToolchain());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.serverOnline).toBe(false);
    expect(result.current.tools).toEqual([]);
    expect(result.current.error).toBeInstanceOf(ToolchainRequestError);
  });

  it('invokes a tool and handles success', async () => {
    (toolchainClient.manifest as any).mockResolvedValue({ tools: [] });
    (toolchainClient.invoke as any).mockResolvedValue({ ok: true, tool: 'test-tool', result: 'success' });

    const { result } = renderHook(() => useToolchain());

    await act(async () => {
      await Promise.resolve();
    });

    let res;
    await act(async () => {
      res = await result.current.invoke('test-tool', { arg: 1 });
    });

    expect(toolchainClient.invoke).toHaveBeenCalledWith('test-tool', { arg: 1 });
    expect(res).toEqual({ ok: true, tool: 'test-tool', result: 'success' });
    expect(result.current.lastResult).toEqual({ ok: true, tool: 'test-tool', result: 'success' });
  });

  it('invokes a tool and handles failure', async () => {
    (toolchainClient.manifest as any).mockResolvedValue({ tools: [] });
    (toolchainClient.invoke as any).mockRejectedValue(new Error('Tool failed'));

    const { result } = renderHook(() => useToolchain());

    await act(async () => {
      await Promise.resolve();
    });

    let res;
    await act(async () => {
      res = await result.current.invoke('test-tool', { arg: 1 });
    });

    expect(res).toEqual({ ok: false, tool: 'test-tool', error: 'Error: Tool failed' });
    expect(result.current.lastResult).toEqual({ ok: false, tool: 'test-tool', error: 'Error: Tool failed' });
  });
});
