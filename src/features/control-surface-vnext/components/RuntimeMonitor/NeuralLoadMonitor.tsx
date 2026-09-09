import React from 'react';
import { motion } from 'motion/react';
import { Activity, Cpu, Radio } from 'lucide-react';
import type { JobPhase, SovereignJob } from '../../types/domain';

interface Props { job?: SovereignJob | null; phase?: JobPhase; }

const PHASE_ACTIVITY: Record<JobPhase, number> = {
  IDLE: 0,
  AWAKENING: 1,
  DISPATCHING: 2,
  PROVISIONING: 3,
  EXECUTING: 4,
  AWAITING_OWNER_INPUT: 2,
  FINALIZING: 5,
  BLOCKED: 1,
  READY_TO_PUBLISH: 5,
  COMPLETED: 6,
  FAILED: 1,
  CANCELLED: 0,
};

export function NeuralLoadMonitor({ job, phase = 'IDLE' }: Props) {
  const currentPhase = job?.phase || phase;
  const activity = PHASE_ACTIVITY[currentPhase];
  const width = `${Math.round((activity / 6) * 100)}%`;
  const evidenceCount = job?.logs.length ?? 0;
  const files = job?.workspaceState.modifiedFiles.length ?? 0;
  return (
    <div className="bg-[var(--carbon-deep)] border-b border-[rgba(255,30,56,0.22)] p-2.5 font-mono select-none" data-testid="vnext-phase-activity">
      <div className="flex items-center justify-between mb-1.5 text-[10px]">
        <div className="flex items-center gap-1.5 text-white font-bold tracking-wider"><Cpu size={12} className={activity > 0 ? 'text-[var(--red-laser)]' : 'text-[var(--text-muted)]'} /><span className="uppercase text-[9.5px]">MISSION PHASE ACTIVITY</span></div>
        <div className="flex items-center gap-2 text-[9px]"><span className="text-[var(--text-dim)]">EVENTS</span><span className="text-white font-bold">{evidenceCount}</span><span className="text-[var(--text-dim)]">FILES</span><span className="text-white font-bold">{files}</span></div>
      </div>
      <div className="relative h-3 w-full bg-[var(--carbon-surface)] rounded overflow-hidden border border-white/5 shadow-inner">
        <motion.div className="h-full bg-[var(--red-pulse)] shadow-[0_0_14px_rgba(255,30,56,0.65)]" animate={{ width }} transition={{ type: 'spring', stiffness: 140, damping: 20 }}>
          {activity > 0 && <motion.div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent" animate={{ x: ['-100%', '200%'] }} transition={{ duration: 1.1, repeat: Infinity, ease: 'linear' }} />}
        </motion.div>
      </div>
      <div className="flex items-center justify-between mt-1 text-[8.5px] text-[var(--text-dim)]"><span className="flex items-center gap-1"><Activity size={10} className="text-[var(--red-laser)]" />PHASE // {currentPhase}</span><span className="flex items-center gap-1"><Radio size={9} /> UI PROJECTION · NOT CPU TELEMETRY</span></div>
    </div>
  );
}
