import { useState, useEffect, useCallback } from 'react';
import type { SovereignHealthReport } from '../features/product/runtime/sovereignHealth';

export interface HomePageMetric {
  label: string;
  value: string;
  unit: string;
  isDemo: boolean;
  source: string;
}

export interface HomePageMetricsState {
  currentTime: string;
  metrics: HomePageMetric[];
  lastUpdated: number | null;
  isDemo: boolean;
}

const DEMO_METRICS: HomePageMetric[] = [
  { label: 'Neural', value: '84.2', unit: 'GFLOPS', isDemo: true, source: 'demo' },
  { label: 'Latency', value: '12', unit: 'ms', isDemo: true, source: 'demo' },
  { label: 'Load', value: '14', unit: '%', isDemo: true, source: 'demo' },
];

function formatTime(date: Date): string {
  return date.toLocaleTimeString('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function deriveMetricsFromHealth(health: SovereignHealthReport | null): HomePageMetric[] {
  if (!health) return DEMO_METRICS;

  const metrics: HomePageMetric[] = [];

  metrics.push({
    label: 'Health',
    value: health.status.toUpperCase(),
    unit: '',
    isDemo: false,
    source: 'runtime',
  });

  if (health.totalIssues > 0) {
    metrics.push({
      label: 'Issues',
      value: String(health.totalIssues),
      unit: '',
      isDemo: false,
      source: 'runtime',
    });
  }

  if (health.criticalRisks > 0) {
    metrics.push({
      label: 'Critical',
      value: String(health.criticalRisks),
      unit: '',
      isDemo: false,
      source: 'runtime',
    });
  }

  if (health.repairsLogged > 0) {
    metrics.push({
      label: 'Repairs',
      value: String(health.repairsLogged),
      unit: '',
      isDemo: false,
      source: 'runtime',
    });
  }

  return metrics;
}

function isDemoMode(health: SovereignHealthReport | null): boolean {
  if (!health) return true;
  return health.status === 'idle' && health.totalIssues === 0 && health.criticalRisks === 0;
}

export function useHomePageMetrics(healthReport: SovereignHealthReport | null) {
  const [state, setState] = useState<HomePageMetricsState>(() => ({
    currentTime: formatTime(new Date()),
    metrics: deriveMetricsFromHealth(healthReport),
    lastUpdated: Date.now(),
    isDemo: isDemoMode(healthReport),
  }));

  const updateTime = useCallback(() => {
    setState((prev) => ({
      ...prev,
      currentTime: formatTime(new Date()),
      lastUpdated: Date.now(),
    }));
  }, []);

  useEffect(() => {
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, [updateTime]);

  useEffect(() => {
    const newMetrics = deriveMetricsFromHealth(healthReport);
    setState((prev) => ({
      ...prev,
      metrics: newMetrics,
      isDemo: isDemoMode(healthReport),
      lastUpdated: Date.now(),
    }));
  }, [healthReport]);

  return state;
}
