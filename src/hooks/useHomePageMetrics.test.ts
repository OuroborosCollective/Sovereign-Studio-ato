import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useHomePageMetrics } from './useHomePageMetrics';
import type { SovereignHealthReport } from '../features/product/runtime/sovereignHealth';

describe('useHomePageMetrics', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('current time', () => {
    it('returns a valid time string format HH:MM:SS', () => {
      const fixedDate = new Date('2024-01-15T14:30:45');
      vi.setSystemTime(fixedDate);

      const { result } = renderHook(() => useHomePageMetrics(null));

      expect(result.current.currentTime).toMatch(/^\d{2}:\d{2}:\d{2}$/);
      expect(result.current.currentTime).toBe('14:30:45');
    });

    it('updates time every second', () => {
      const startDate = new Date('2024-01-15T14:30:45');
      vi.setSystemTime(startDate);

      const { result } = renderHook(() => useHomePageMetrics(null));

      expect(result.current.currentTime).toBe('14:30:45');

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      expect(result.current.currentTime).toBe('14:30:46');
    });
  });

  describe('demo metrics', () => {
    it('returns demo metrics when no health report is provided', () => {
      const { result } = renderHook(() => useHomePageMetrics(null));

      expect(result.current.isDemo).toBe(true);
      expect(result.current.metrics.length).toBeGreaterThan(0);
      result.current.metrics.forEach((metric) => {
        expect(metric.isDemo).toBe(true);
        expect(metric.source).toBe('demo');
      });
    });

    it('includes neural, latency, and load demo metrics', () => {
      const { result } = renderHook(() => useHomePageMetrics(null));

      const labels = result.current.metrics.map((m) => m.label);
      expect(labels).toContain('Neural');
      expect(labels).toContain('Latency');
      expect(labels).toContain('Load');
    });
  });

  describe('runtime metrics from health report', () => {
    it('returns runtime metrics when health report is available', () => {
      const healthReport: SovereignHealthReport = {
        status: 'green',
        criticalRisks: 0,
        totalIssues: 5,
        repairsLogged: 2,
        branchDelta: -1,
        summary: 'Health green: 0 critical risk(s)',
        recommendations: [],
      };

      const { result } = renderHook(() => useHomePageMetrics(healthReport));

      expect(result.current.isDemo).toBe(false);
      
      const healthMetric = result.current.metrics.find((m) => m.label === 'Health');
      expect(healthMetric).toBeDefined();
      expect(healthMetric?.value).toBe('GREEN');
      expect(healthMetric?.isDemo).toBe(false);
      expect(healthMetric?.source).toBe('runtime');

      const issuesMetric = result.current.metrics.find((m) => m.label === 'Issues');
      expect(issuesMetric).toBeDefined();
      expect(issuesMetric?.value).toBe('5');
      expect(issuesMetric?.isDemo).toBe(false);
      expect(issuesMetric?.source).toBe('runtime');

      const repairsMetric = result.current.metrics.find((m) => m.label === 'Repairs');
      expect(repairsMetric).toBeDefined();
      expect(repairsMetric?.value).toBe('2');
      expect(repairsMetric?.isDemo).toBe(false);
      expect(repairsMetric?.source).toBe('runtime');
    });

    it('shows critical risks when present', () => {
      const healthReport: SovereignHealthReport = {
        status: 'red',
        criticalRisks: 3,
        totalIssues: 10,
        repairsLogged: 0,
        branchDelta: 1,
        summary: 'Health red: 3 critical risk(s)',
        recommendations: [],
      };

      const { result } = renderHook(() => useHomePageMetrics(healthReport));

      const criticalMetric = result.current.metrics.find((m) => m.label === 'Critical');
      expect(criticalMetric).toBeDefined();
      expect(criticalMetric?.value).toBe('3');
      expect(criticalMetric?.isDemo).toBe(false);
      expect(criticalMetric?.source).toBe('runtime');
    });

    it('returns demo metrics when health report has no issues', () => {
      const healthReport: SovereignHealthReport = {
        status: 'idle',
        criticalRisks: 0,
        totalIssues: 0,
        repairsLogged: 0,
        branchDelta: 0,
        summary: 'Health idle',
        recommendations: [],
      };

      const { result } = renderHook(() => useHomePageMetrics(healthReport));

      expect(result.current.isDemo).toBe(true);
      expect(result.current.metrics.length).toBeGreaterThan(0);
    });
  });

  describe('state updates', () => {
    it('updates when health report changes', () => {
      const { result, rerender } = renderHook(
        ({ health }) => useHomePageMetrics(health),
        { initialProps: { health: null as SovereignHealthReport | null } }
      );

      expect(result.current.isDemo).toBe(true);

      const newHealth: SovereignHealthReport = {
        status: 'green',
        criticalRisks: 0,
        totalIssues: 1,
        repairsLogged: 0,
        branchDelta: 0,
        summary: 'Health green',
        recommendations: [],
      };

      rerender({ health: newHealth });

      expect(result.current.isDemo).toBe(false);
      const issuesMetric = result.current.metrics.find((m) => m.label === 'Issues');
      expect(issuesMetric?.value).toBe('1');
    });

    it('tracks lastUpdated timestamp', () => {
      vi.setSystemTime(new Date('2024-01-15T10:00:00'));

      const { result } = renderHook(() => useHomePageMetrics(null));

      expect(result.current.lastUpdated).toBe(1705312800000);

      act(() => {
        vi.advanceTimersByTime(5000);
      });

      expect(result.current.lastUpdated).toBe(1705312805000);
    });
  });

  describe('runtime-truth compliance', () => {
    it('every metric has a defined source', () => {
      const healthReport: SovereignHealthReport = {
        status: 'warning',
        criticalRisks: 1,
        totalIssues: 5,
        repairsLogged: 1,
        branchDelta: 0.5,
        summary: 'Health warning',
        recommendations: [],
      };

      const { result } = renderHook(() => useHomePageMetrics(healthReport));

      result.current.metrics.forEach((metric) => {
        expect(metric.source).toBeDefined();
        expect(metric.source.length).toBeGreaterThan(0);
        expect(['demo', 'runtime', 'system']).toContain(metric.source);
      });
    });

    it('demo metrics are clearly marked as demo', () => {
      const { result } = renderHook(() => useHomePageMetrics(null));

      const demoMetrics = result.current.metrics.filter((m) => m.isDemo);
      demoMetrics.forEach((metric) => {
        expect(metric.isDemo).toBe(true);
        expect(metric.source).toBe('demo');
      });
    });

    it('runtime metrics are not marked as demo', () => {
      const healthReport: SovereignHealthReport = {
        status: 'green',
        criticalRisks: 0,
        totalIssues: 2,
        repairsLogged: 1,
        branchDelta: 0,
        summary: 'Health green',
        recommendations: [],
      };

      const { result } = renderHook(() => useHomePageMetrics(healthReport));

      const runtimeMetrics = result.current.metrics.filter((m) => m.source === 'runtime');
      runtimeMetrics.forEach((metric) => {
        expect(metric.isDemo).toBe(false);
      });
    });
  });
});
