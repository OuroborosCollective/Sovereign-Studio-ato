import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  createTelemetryFeedback,
  createHealthGateTelemetryEvent,
  publishRuntimeTelemetryFeedback,
} from './publishRuntimeTelemetryFeedback';

describe('publishRuntimeTelemetryFeedback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('createTelemetryFeedback', () => {
    it('returns green lamp when allowed and healthy', () => {
      const result = {
        allowed: true,
        status: 'green' as const,
        reason: 'All checks passed.',
        recommendations: [],
      };

      const feedback = createTelemetryFeedback(result);

      expect(feedback.lamp).toBe('green');
      expect(feedback.title).toBe('Runtime ready');
      expect(feedback.message).toBe('All checks passed.');
      expect(feedback.source).toBe('health-gate');
      expect(feedback.thinking).toBe(false);
    });

    it('returns red lamp when not allowed', () => {
      const result = {
        allowed: false,
        status: 'red' as const,
        reason: 'Runtime validation failed.',
        recommendations: ['Check logs'],
      };

      const feedback = createTelemetryFeedback(result);

      expect(feedback.lamp).toBe('red');
      expect(feedback.title).toBe('Runtime needs attention');
      expect(feedback.action).toBe('Check logs');
    });

    it('returns yellow lamp for warning status', () => {
      const result = {
        allowed: true,
        status: 'warning' as const,
        reason: 'Some checks have warnings.',
        recommendations: ['Review warnings'],
      };

      const feedback = createTelemetryFeedback(result);

      expect(feedback.lamp).toBe('yellow');
      expect(feedback.action).toBe('Review warnings');
    });

    it('returns yellow lamp for idle status', () => {
      const result = {
        allowed: true,
        status: 'idle' as const,
        reason: 'Runtime is idle.',
        recommendations: [],
      };

      const feedback = createTelemetryFeedback(result);

      expect(feedback.lamp).toBe('yellow');
    });

    it('includes first recommendation as action when available', () => {
      const result = {
        allowed: true,
        status: 'green' as const,
        reason: 'Checks passed.',
        recommendations: ['First action', 'Second action'],
      };

      const feedback = createTelemetryFeedback(result);

      expect(feedback.action).toBe('First action');
    });

    it('uses default action when no recommendations', () => {
      const result = {
        allowed: true,
        status: 'green' as const,
        reason: 'Checks passed.',
        recommendations: [],
      };

      const feedback = createTelemetryFeedback(result);

      expect(feedback.action).toBe('Continue with review.');
    });

    it('uses error action when not allowed and no recommendations', () => {
      const result = {
        allowed: false,
        status: 'red' as const,
        reason: 'Failed.',
        recommendations: [],
      };

      const feedback = createTelemetryFeedback(result);

      expect(feedback.action).toBe('Open Health and Telemetry.');
    });

    it('uses custom timestamp when provided', () => {
      const customTime = 1700000000000;
      const result = {
        allowed: true,
        status: 'green' as const,
        reason: 'OK',
        recommendations: [],
      };

      const feedback = createTelemetryFeedback(result, customTime);

      expect(feedback.updatedAt).toBe(customTime);
    });
  });

  describe('createHealthGateTelemetryEvent', () => {
    it('includes metadata when provided', () => {
      const result = {
        allowed: true,
        status: 'green' as const,
        reason: 'OK',
        recommendations: [],
      };
      const metadata = { fileCount: 42, guardDuration: 150 };

      const event = createHealthGateTelemetryEvent(result, metadata);

      expect(event.metadata).toEqual(metadata);
      expect(event.lamp).toBe('green');
    });

    it('returns undefined metadata when not provided', () => {
      const result = {
        allowed: true,
        status: 'green' as const,
        reason: 'OK',
        recommendations: [],
      };

      const event = createHealthGateTelemetryEvent(result);

      expect(event.metadata).toBeUndefined();
    });
  });

  describe('publishRuntimeTelemetryFeedback', () => {
    it('dispatches CustomEvent to window when available', () => {
      const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent');
      const result = {
        allowed: true,
        status: 'green' as const,
        reason: 'OK',
        recommendations: [],
      };

      publishRuntimeTelemetryFeedback(result);

      expect(dispatchEventSpy).toHaveBeenCalledTimes(1);
      
      const event = dispatchEventSpy.mock.calls[0][0] as CustomEvent;
      expect(event.type).toBe('sovereign:runtime-coach-state');
      expect(event.detail.lamp).toBe('green');
    });

    it('does not throw when window is undefined', () => {
      const originalWindow = globalThis.window;
      // Simulate no window environment
      const mockWindow = undefined;
      Object.defineProperty(globalThis, 'window', {
        get: () => mockWindow,
        configurable: true,
      });

      const result = {
        allowed: true,
        status: 'green' as const,
        reason: 'OK',
        recommendations: [],
      };

      expect(() => publishRuntimeTelemetryFeedback(result)).not.toThrow();

      Object.defineProperty(globalThis, 'window', {
        get: () => originalWindow,
        configurable: true,
      });
    });
  });
});
