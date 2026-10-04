import React, { useEffect, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';

export interface RegistryReadbackStatusProps {
  observedAt?: string; receivedMonotonicMs?: number; isLoading?: boolean;
  readbackError?: string; onRefresh?: () => void;
}

export function RegistryReadbackStatus({ observedAt, receivedMonotonicMs, isLoading, readbackError, onRefresh }: RegistryReadbackStatusProps) {
  const [, tick] = useState(0);
  useEffect(() => {
    if (receivedMonotonicMs == null) return;
    const timer = setInterval(() => tick(value => value + 1), 1000);
    return () => clearInterval(timer);
  }, [receivedMonotonicMs]);
  const age = receivedMonotonicMs == null ? undefined : Math.max(0, Math.floor((performance.now() - receivedMonotonicMs) / 1000));
  const stale = Boolean(readbackError) || (age != null && age >= 30);
  return <div className="text-[10px] text-[var(--text-muted)] space-y-1">
    <div className="flex items-center justify-between gap-2"><span>{stale ? 'LAST OBSERVED · STALE READBACK' : isLoading ? 'READING SERVER STATE' : observedAt ? 'SERVER READBACK' : 'READBACK UNAVAILABLE'}</span>
      {onRefresh && <button type="button" onClick={onRefresh} disabled={isLoading} title={isLoading ? "Refreshing server state..." : "Refresh server state readback"} className="min-h-11 px-2 flex items-center gap-1.5 rounded border border-white/10 text-white disabled:opacity-40 hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20 transition-colors">{isLoading ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />} REFRESH READBACK</button>}</div>
    {observedAt && <div className="break-all">Observed: {observedAt}{age != null && <> · received {age}s ago</>}</div>}
    {readbackError && <div role="alert" className="text-[var(--red-alert)] break-words">Readback unavailable: {readbackError}</div>}
  </div>;
}
