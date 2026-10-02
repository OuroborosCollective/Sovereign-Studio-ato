import React, { useEffect, useState } from 'react';

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
      {onRefresh && <button type="button" onClick={onRefresh} disabled={isLoading} className="min-h-11 px-2 rounded border border-white/10 text-white disabled:opacity-40">REFRESH READBACK</button>}</div>
    {observedAt && <div className="break-all">Observed: {observedAt}{age != null && <> · received {age}s ago</>}</div>}
    {readbackError && <div role="alert" className="text-[var(--red-alert)] break-words">Readback unavailable: {readbackError}</div>}
  </div>;
}
