import React from 'react';
import type { ModelHealthStatus } from '../hooks/useModelHealth';

/**
 * Props for ModelHealthPanel
 * If no models are provided, shows placeholder UI explaining the feature
 */
export interface ModelHealthPanelProps {
  /** List of model health statuses */
  models?: ModelHealthStatus[];
  /** Whether health checks are currently running */
  isChecking?: boolean;
  /** Timestamp of last health check */
  lastCheck?: number | null;
  /** Callback to refresh health status */
  onRefresh?: () => void;
  /** Whether to show refresh button */
  showRefresh?: boolean;
}

/**
 * Fallback mock data for when no adapters are configured
 */
const MOCK_MODEL_STATUS: ModelHealthStatus[] = [
  {
    id: 'mock-bridge',
    name: 'Primary Bridge',
    status: 'unknown',
    latencyMs: null,
    lastCheck: null,
    errorCount: 0,
    successCount: 0,
    isEnabled: true,
  },
  {
    id: 'mock-mlvoca',
    name: 'MLVoca (No-Key)',
    status: 'unknown',
    latencyMs: null,
    lastCheck: null,
    errorCount: 0,
    successCount: 0,
    isEnabled: true,
  },
];

function statusIcon(status: ModelHealthStatus['status']): string {
  if (status === 'healthy') return '🟢';
  if (status === 'degraded') return '🟡';
  return '⚪';
}

function statusColor(status: ModelHealthStatus['status']): string {
  if (status === 'healthy') return 'text-emerald-300';
  if (status === 'degraded') return 'text-amber-300';
  return 'text-slate-400';
}

function formatLatency(ms: number | null): string {
  if (ms === null) return 'N/A';
  return `${ms}ms`;
}

function formatTime(timestamp: number | null): string {
  if (!timestamp) return 'Never';
  const diff = Date.now() - timestamp;
  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  return `${Math.floor(diff / 3600000)}h ago`;
}

export function ModelHealthPanel({
  models = MOCK_MODEL_STATUS,
  isChecking = false,
  lastCheck = null,
  onRefresh,
  showRefresh = true,
}: ModelHealthPanelProps) {
  const healthyCount = models.filter((m) => m.status === 'healthy').length;
  const degradedCount = models.filter((m) => m.status === 'degraded').length;
  const unknownCount = models.filter((m) => m.status === 'unknown').length;
  const hasMockData = models === MOCK_MODEL_STATUS;

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold">Model Health Monitor</h2>
          <p className="mt-1 text-xs text-slate-400">
            {models.length} model(s) · {healthyCount} healthy · {degradedCount} degraded · {unknownCount} unknown
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-500">
            Last check: {formatTime(lastCheck)}
          </span>
          {showRefresh && onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isChecking}
              className="rounded border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-300 hover:bg-cyan-500/20 disabled:opacity-50"
            >
              {isChecking ? 'Checking...' : 'Refresh'}
            </button>
          )}
        </div>
      </div>

      {hasMockData && (
        <div className="mt-3 rounded border border-amber-500/20 bg-amber-500/10 p-3">
          <p className="text-xs text-amber-300">
            💡 Connect a repository to enable real-time LLM health monitoring. The model health panel automatically tracks latency, success rates, and availability for all configured LLM adapters.
          </p>
        </div>
      )}

      {models.length === 0 ? (
        <p className="mt-4 text-xs text-slate-500">No models configured.</p>
      ) : (
        <div className="mt-4 space-y-2">
          {models.map((model) => (
            <div
              key={model.id}
              className="flex items-center justify-between rounded border border-slate-800 bg-slate-900/70 p-3"
            >
              <div className="flex items-center gap-3">
                <span className="text-lg" role="img" aria-label={model.status}>
                  {statusIcon(model.status)}
                </span>
                <div>
                  <p className={`font-bold ${statusColor(model.status)}`}>
                    {model.name}
                  </p>
                  <p className="text-xs text-slate-500">
                    {model.isEnabled ? 'Enabled' : 'Disabled'} · {model.status}
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className={`font-mono text-sm ${statusColor(model.status)}`}>
                  {formatLatency(model.latencyMs)}
                </p>
                <p className="text-xs text-slate-500">
                  {model.successCount}/{model.successCount + model.errorCount} success
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 rounded border border-slate-800 bg-slate-900/70 p-3">
        <h3 className="font-bold text-xs text-slate-400">Health Legend</h3>
        <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-500">
          <span>🟢 Healthy: Latency &lt; 2s</span>
          <span>🟡 Degraded: Latency &gt; 2s</span>
          <span>⚪ Unknown: Not checked or failed</span>
        </div>
      </div>
    </section>
  );
}
