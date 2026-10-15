import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  emitToolSignal,
  getToolPredictions,
  registerToolNode,
  withToolSignals,
  withToolSignalsAsync,
  configureToolPredictiveBridge,
} from './toolPredictiveBridge';
import * as predictiveLayer from './predictiveLayer';

vi.mock('./predictiveLayer', () => ({
  getDefaultPredictiveLayer: vi.fn(),
}));

describe('toolPredictiveBridge', () => {
  let mockLayer: any;

  beforeEach(() => {
    vi.clearAllMocks();
    mockLayer = {
      isEnabled: vi.fn().mockReturnValue(true),
      emitSignal: vi.fn(),
      processSignal: vi.fn().mockResolvedValue(undefined),
      registerNode: vi.fn(),
      getLatentSpace: vi.fn().mockReturnValue({
        findTopK: vi.fn().mockReturnValue([]),
      }),
    };
    (predictiveLayer.getDefaultPredictiveLayer as any).mockReturnValue(mockLayer);

    // reset config
    configureToolPredictiveBridge({
      enabled: true,
      emitSignals: true,
      learnFromResults: true,
      confidenceThreshold: 0.5,
    });
  });

  describe('emitToolSignal', () => {
    it('emits success signal correctly', () => {
      emitToolSignal({
        toolName: 'test-tool',
        toolType: 'mcp',
        status: 'success',
        durationMs: 150,
        parameters: { foo: 'bar' },
        workspaceId: 'ws-1',
        jobId: 'job-1',
        traceId: 'test-trace',
      });

      expect(mockLayer.emitSignal).toHaveBeenCalledWith(
        'tool.mcp.test-tool',
        1,
        expect.objectContaining({
          toolType: 'mcp',
          toolName: 'test-tool',
          status: 'success',
          durationMs: 150,
          workspaceId: 'ws-1',
          jobId: 'job-1',
          paramCount: 1,
        })
      );
      expect(mockLayer.processSignal).toHaveBeenCalled();
    });

    it('emits error signal correctly', () => {
      emitToolSignal({
        toolName: 'test-tool',
        toolType: 'mcp',
        status: 'error',
        durationMs: 50,
        parameters: {},
      });

      expect(mockLayer.emitSignal).toHaveBeenCalledWith(
        'tool.mcp.test-tool',
        0, // 0 for error
        expect.any(Object)
      );
    });

    it('does nothing if bridge is disabled', () => {
      configureToolPredictiveBridge({ enabled: false });
      emitToolSignal({
        toolName: 'test-tool',
        toolType: 'mcp',
        status: 'success',
        durationMs: 10,
        parameters: {},
      });
      expect(mockLayer.emitSignal).not.toHaveBeenCalled();
    });

    it('does nothing if predictive layer is disabled', () => {
      mockLayer.isEnabled.mockReturnValue(false);
      emitToolSignal({
        toolName: 'test-tool',
        toolType: 'mcp',
        status: 'success',
        durationMs: 10,
        parameters: {},
      });
      expect(mockLayer.emitSignal).not.toHaveBeenCalled();
    });
  });

  describe('registerToolNode', () => {
    it('registers a sensor node', () => {
      registerToolNode('test-tool', 'mcp');
      expect(mockLayer.registerNode).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'tool.mcp.test-tool',
          name: 'mcp:test-tool',
          nodeType: 'sensor',
        })
      );
    });

    it('does not register if disabled', () => {
       configureToolPredictiveBridge({ enabled: false });
       registerToolNode('test-tool', 'mcp');
       expect(mockLayer.registerNode).not.toHaveBeenCalled();
    });
  });

  describe('getToolPredictions', () => {
    it('returns empty predictions if layer is disabled', async () => {
      mockLayer.isEnabled.mockReturnValue(false);
      const result = await getToolPredictions('mcp', 'test-tool');
      expect(result.predictedSuccessRate).toBe(0);
      expect(result.recommendations).toContain('Predictive Layer ist deaktiviert; keine Runtime-Evidence vorhanden.');
    });

    it('returns predictions based on latent space', async () => {
      mockLayer.getLatentSpace().findTopK.mockReturnValue([
        { pattern: { signalValue: 1, avgConfidence: 0.8 } },
        { pattern: { signalValue: 1, avgConfidence: 0.7 } },
        { pattern: { signalValue: 0, avgConfidence: 0.6 } },
      ]);

      const result = await getToolPredictions('mcp', 'test-tool');
      expect(result.predictedSuccessRate).toBeCloseTo(0.666, 2); // 2/3 success
      expect(result.confidence).toBeCloseTo(0.7, 2); // (0.8+0.7+0.6)/3
    });

    it('handles zero patterns', async () => {
      mockLayer.getLatentSpace().findTopK.mockReturnValue([]);
      const result = await getToolPredictions('mcp', 'test-tool');
      expect(result.predictedSuccessRate).toBe(0);
      expect(result.recommendations).toContain('Keine bestätigten historischen Tool-Ergebnisse vorhanden.');
    })
  });

  describe('withToolSignals', () => {
    it('wraps sync function and emits success', () => {
      const fn = vi.fn().mockReturnValue('result');
      const wrapped = withToolSignals('test-tool', 'mcp', fn);

      const res = wrapped('arg1', 'arg2');
      expect(res).toBe('result');
      expect(mockLayer.emitSignal).toHaveBeenCalledWith(
        'tool.mcp.test-tool',
        1,
        expect.objectContaining({ status: 'success' })
      );
    });

    it('wraps sync function and emits error on throw', () => {
      const fn = vi.fn().mockImplementation(() => { throw new Error('fail'); });
      const wrapped = withToolSignals('test-tool', 'mcp', fn);

      expect(() => wrapped('arg1')).toThrow('fail');
      expect(mockLayer.emitSignal).toHaveBeenCalledWith(
        'tool.mcp.test-tool',
        0,
        expect.objectContaining({ status: 'error' })
      );
    });
  });

  describe('withToolSignalsAsync', () => {
    it('wraps async function and emits success', async () => {
      const fn = vi.fn().mockResolvedValue('result');
      const wrapped = withToolSignalsAsync('test-tool', 'mcp', fn);

      const res = await wrapped('arg1');
      expect(res).toBe('result');
      expect(mockLayer.emitSignal).toHaveBeenCalledWith(
        'tool.mcp.test-tool',
        1,
        expect.objectContaining({ status: 'success' })
      );
    });

    it('wraps async function and emits error on throw', async () => {
      const fn = vi.fn().mockRejectedValue(new Error('fail'));
      const wrapped = withToolSignalsAsync('test-tool', 'mcp', fn);

      await expect(wrapped('arg1')).rejects.toThrow('fail');
      expect(mockLayer.emitSignal).toHaveBeenCalledWith(
        'tool.mcp.test-tool',
        0,
        expect.objectContaining({ status: 'error' })
      );
    });
  });
});
