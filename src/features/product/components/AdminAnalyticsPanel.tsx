import React, { useMemo, useState } from 'react';
import { Activity, AlertTriangle, BarChart3, CheckCircle, Clock, DollarSign, Shield, TrendingUp, XCircle, Zap } from 'lucide-react';

export interface AdminModelHealth {
  id: string;
  name: string;
  status: 'healthy' | 'degraded' | 'down';
  latencyMs: number;
  lastCheck: number;
}

export interface AdminUsageStats {
  modelId: string;
  modelName: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  requestCount: number;
  estimatedCost: number;
}

interface AdminAnalyticsPanelProps {
  isAdmin?: boolean;
  className?: string;
  usageStats?: AdminUsageStats[];
  modelHealth?: AdminModelHealth[];
  isLoading?: boolean;
}

function statusIcon(status: AdminModelHealth['status']): React.ReactElement {
  if (status === 'healthy') return <CheckCircle size={16} className="text-emerald-400" />;
  if (status === 'degraded') return <AlertTriangle size={16} className="text-amber-400" />;
  return <XCircle size={16} className="text-red-400" />;
}

function statusLabel(status: AdminModelHealth['status']): string {
  if (status === 'healthy') return 'Gesund';
  if (status === 'degraded') return 'Langsam';
  return 'Unerreichbar';
}

function statusClasses(status: AdminModelHealth['status']): string {
  if (status === 'healthy') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  if (status === 'degraded') return 'border-amber-500/30 bg-amber-500/10 text-amber-200';
  return 'border-red-500/30 bg-red-500/10 text-red-200';
}

export const AdminAnalyticsPanel: React.FC<AdminAnalyticsPanelProps> = ({
  isAdmin = false,
  className = '',
  usageStats = [],
  modelHealth = [],
  isLoading = false,
}) => {
  const [timeRange, setTimeRange] = useState<'day' | 'week' | 'month'>('day');

  const totals = useMemo(() => ({
    cost: usageStats.reduce((sum, item) => sum + item.estimatedCost, 0),
    tokens: usageStats.reduce((sum, item) => sum + item.totalTokens, 0),
    requests: usageStats.reduce((sum, item) => sum + item.requestCount, 0),
    maxTokens: Math.max(1, ...usageStats.map((item) => item.totalTokens)),
  }), [usageStats]);

  if (!isAdmin) return null;

  if (isLoading) {
    return (
      <section className={`rounded-2xl border border-cyan-500/20 bg-slate-900 p-4 ${className}`}>
        <div className="flex h-32 items-center justify-center gap-3 text-xs text-cyan-200">
          <Activity size={22} className="animate-pulse" />
          Runtime-Analytics werden geladen.
        </div>
      </section>
    );
  }

  return (
    <section className={`overflow-hidden rounded-2xl border border-cyan-500/20 bg-slate-900 ${className}`}>
      <header className="flex items-center justify-between border-b border-cyan-500/15 bg-slate-950/40 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-500/10">
            <BarChart3 size={16} className="text-cyan-300" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100">Admin Analytics</h3>
            <p className="text-[10px] text-slate-500">Nur echte Runtime-Daten, keine Demo-Werte.</p>
          </div>
        </div>
        <div className="flex gap-1 rounded-lg bg-slate-800/60 p-1">
          {(['day', 'week', 'month'] as const).map((range) => (
            <button
              key={range}
              type="button"
              onClick={() => setTimeRange(range)}
              className={`rounded px-2 py-1 text-[10px] font-semibold ${timeRange === range ? 'bg-cyan-500/20 text-cyan-200' : 'text-slate-500 hover:text-slate-300'}`}
            >
              {range === 'day' ? 'Tag' : range === 'week' ? 'Woche' : 'Monat'}
            </button>
          ))}
        </div>
      </header>

      <div className="grid gap-3 p-4 sm:grid-cols-3">
        <div className="rounded-xl bg-slate-800/50 p-3">
          <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500"><DollarSign size={12} />Kosten</div>
          <div className="text-xl font-bold text-slate-100">€{totals.cost.toFixed(3)}</div>
        </div>
        <div className="rounded-xl bg-slate-800/50 p-3">
          <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500"><Zap size={12} />Tokens</div>
          <div className="text-xl font-bold text-slate-100">{(totals.tokens / 1000).toFixed(1)}K</div>
        </div>
        <div className="rounded-xl bg-slate-800/50 p-3">
          <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500"><Clock size={12} />Requests</div>
          <div className="text-xl font-bold text-slate-100">{totals.requests}</div>
        </div>
      </div>

      <div className="border-t border-cyan-500/15 px-4 py-3">
        <div className="mb-3 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-cyan-300"><Activity size={14} />Model Health</div>
        <div className="space-y-2">
          {modelHealth.length === 0 ? (
            <p className="rounded-lg border border-slate-700/60 bg-slate-950/40 p-3 text-xs text-slate-400">Noch keine echten Model-Health-Daten aus der Runtime vorhanden.</p>
          ) : modelHealth.map((model) => (
            <div key={model.id} className="flex items-center justify-between rounded-lg bg-slate-800/30 p-2">
              <div className="flex items-center gap-3">
                {statusIcon(model.status)}
                <div>
                  <div className="text-xs font-medium text-slate-200">{model.name}</div>
                  <div className="text-[10px] text-slate-500">{model.status === 'down' ? 'Offline' : `${model.latencyMs}ms`}</div>
                </div>
              </div>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${statusClasses(model.status)}`}>{statusLabel(model.status)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-cyan-500/15 px-4 py-3">
        <div className="mb-3 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-cyan-300"><TrendingUp size={14} />Usage by Model</div>
        <div className="space-y-3">
          {usageStats.length === 0 ? (
            <p className="rounded-lg border border-slate-700/60 bg-slate-950/40 p-3 text-xs text-slate-400">Noch keine echten Usage-Daten aus der Runtime vorhanden.</p>
          ) : usageStats.map((stat) => (
            <div key={stat.modelId}>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-xs text-slate-300">{stat.modelName}</span>
                <span className="font-mono text-xs text-slate-500">{stat.requestCount} req</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                <div className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-indigo-500" style={{ width: `${(stat.totalTokens / totals.maxTokens) * 100}%` }} />
              </div>
              <div className="mt-1 flex justify-between text-[10px] text-slate-500">
                <span>{(stat.totalTokens / 1000).toFixed(1)}K tokens</span>
                <span className={stat.estimatedCost > 0 ? 'text-amber-400' : 'text-emerald-400'}>{stat.estimatedCost > 0 ? `€${stat.estimatedCost.toFixed(3)}` : 'Free'}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <footer className="flex items-center justify-center gap-2 border-t border-cyan-500/15 bg-slate-950/50 px-4 py-2">
        <Shield size={12} className="text-cyan-300" />
        <span className="text-[10px] text-slate-500">Admin Panel · echte Datenquelle erforderlich</span>
      </footer>
    </section>
  );
};

export default AdminAnalyticsPanel;
