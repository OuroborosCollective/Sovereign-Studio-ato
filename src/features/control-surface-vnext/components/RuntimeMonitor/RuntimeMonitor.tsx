import React, { useEffect, useRef, useState } from 'react';
import { Activity, Check, Copy, Radio, Terminal } from 'lucide-react';
import type { SovereignJob } from '../../types/domain';

interface Props { job: SovereignJob | null | undefined; isPolling?: boolean; }

export function RuntimeMonitor({ job, isPolling = false }: Props) {
  const [copied, setCopied] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [job?.logs?.length]);
  const copyLogs = () => {
    if (!job?.logs) return;
    void navigator.clipboard.writeText(job.logs.join('\n'));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };
  const logs = job?.logs || [];
  return (
    <div className="flex flex-col h-full bg-[var(--carbon-deep)] p-3 border-b border-white/5 overflow-hidden" data-testid="vnext-runtime-monitor">
      <div className="flex items-center justify-between border-b border-white/5 pb-2 mb-2">
        <div className="flex items-center gap-1.5 font-mono text-[11px] font-bold text-white uppercase tracking-wider"><Activity size={13} className="text-[var(--red-laser)]" /><span>RUNTIME MONITOR</span></div>
        <div className="flex items-center gap-2">{isPolling && <div className="flex items-center gap-1 font-mono text-[9px] text-[var(--red-laser)] animate-pulse"><Radio size={10} /><span>LIVE READBACK</span></div>}<button onClick={copyLogs} disabled={logs.length === 0} className="text-[var(--text-dim)] hover:text-white disabled:opacity-30 transition-colors p-1" title="Copy runtime readback">{copied ? <Check size={12} className="text-[var(--emerald-seal)]" /> : <Copy size={12} />}</button></div>
      </div>
      <div className="flex-1 overflow-y-auto font-mono text-[10.5px] leading-relaxed space-y-1 pr-1 select-text">
        {logs.map((log, idx) => {
          const isError = /ERR|ERROR|FAILED|BLOCKED/i.test(log);
          const isSuccess = /GITHUB READBACK|VERIFIED|SUCCESS/i.test(log);
          const isWarning = /WARN|NEXT:|DIRECTIVE/i.test(log);
          return <div key={`${idx}-${log}`} className={`break-all py-0.5 px-1 rounded flex items-start gap-1.5 ${isError ? 'bg-[rgba(255,30,56,0.15)] text-[var(--red-laser)] font-bold' : isSuccess ? 'bg-[rgba(16,185,129,0.1)] text-[var(--emerald-seal)] font-semibold' : isWarning ? 'bg-[rgba(255,140,0,0.1)] text-[var(--red-alert)]' : 'text-[var(--text-muted)] hover:bg-white/[0.02]'}`}><span className="text-[var(--red-pulse)] select-none shrink-0">&gt;</span><span className="flex-1">{log}</span></div>;
        })}
        {logs.length === 0 && <div className="flex flex-col items-center justify-center h-28 text-center text-[var(--text-dim)] font-mono text-[10px] italic"><Terminal size={18} className="mb-1.5 opacity-40 text-[var(--red-pulse)]" /><span>No runtime readback yet.</span><span className="text-[9px] opacity-60">Nothing is synthesized to fill this panel.</span></div>}
        <div ref={logsEndRef} />
      </div>
    </div>
  );
}
