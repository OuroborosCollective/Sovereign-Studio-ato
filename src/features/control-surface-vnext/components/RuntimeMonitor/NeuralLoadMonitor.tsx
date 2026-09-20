import React from 'react';
import { Activity, Cpu, Radio } from 'lucide-react';
import type { JobPhase, SovereignJob } from '../../types/domain';

interface Props { job?: SovereignJob | null; phase?: JobPhase; }

export function NeuralLoadMonitor({ job, phase = 'IDLE' }: Props) {
  const currentPhase = job?.phase || phase;
  const active = ['DISPATCHING', 'PROVISIONING', 'EXECUTING', 'FINALIZING'].includes(currentPhase);
  const evidenceCount = job?.logs.length ?? 0;
  const files = job?.workspaceState.modifiedFiles.length ?? 0;
  return (
    <div className="bg-[var(--carbon-deep)] border-b border-[rgba(255,30,56,0.22)] p-2.5 font-mono select-none" data-testid="vnext-phase-activity">
      <div className="flex items-center justify-between mb-1.5 text-[10px]">
        <div className="flex items-center gap-1.5 text-white font-bold tracking-wider"><Cpu size={12} className={active ? 'text-[var(--red-laser)]' : 'text-[var(--text-muted)]'} /><span className="uppercase text-[9.5px]">MISSION PHASE ACTIVITY</span></div>
        <div className="flex items-center gap-2 text-[9px]"><span className="text-[var(--text-dim)]">EVENTS</span><span className="text-white font-bold">{evidenceCount}</span><span className="text-[var(--text-dim)]">FILES</span><span className="text-white font-bold">{files}</span></div>
      </div>
      <p className="text-[9px] text-[var(--text-muted)]">{active ? 'Awaiting task observations below; completion percentage is unavailable.' : 'Phase and counts come from the last received job state.'}</p>
      <div className="flex items-center justify-between mt-1 text-[8.5px] text-[var(--text-dim)]"><span className="flex items-center gap-1"><Activity size={10} className="text-[var(--red-laser)]" />PHASE // {currentPhase}</span><span className="flex items-center gap-1"><Radio size={9} /> UI PROJECTION · NOT CPU TELEMETRY</span></div>
    </div>
  );
}
