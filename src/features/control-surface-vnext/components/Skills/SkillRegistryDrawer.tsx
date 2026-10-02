import React from 'react';
import { BrainCircuit, Cpu } from 'lucide-react';
import { Modal } from '../Modal';
import { RegistryReadbackStatus } from '../RegistryReadbackStatus';
import type { RuntimeAgentNode, SovereignJob } from '../../types/domain';

interface Props {
  isOpen: boolean; onClose: () => void; agents: RuntimeAgentNode[];
  observedAt?: string; receivedMonotonicMs?: number; isLoading?: boolean;
  readbackError?: string; onRefresh?: () => void; job?: SovereignJob | null;
}

export function SkillRegistryDrawer({ isOpen, onClose, agents, observedAt, receivedMonotonicMs, isLoading, readbackError, onRefresh, job }: Props) {
  return <Modal isOpen={isOpen} onClose={onClose} title="AGENT REGISTRY // RUNTIME PROJECTION">
    <div className="space-y-3 font-mono">
      <RegistryReadbackStatus observedAt={observedAt} receivedMonotonicMs={receivedMonotonicMs} isLoading={isLoading} readbackError={readbackError} onRefresh={onRefresh} />
      <p className="text-[11px] text-[var(--text-muted)]">Server-registered executor and actual persisted agent tasks. Task state, executor heartbeat and measured progress are separate observations.</p>
      {job && <div className="text-[10px] text-[var(--text-dim)] break-all">Job: {job.id}<br />Last persisted executor heartbeat: {job.lastHeartbeatAt || 'UNOBSERVED'}<br />Last progress event: {job.lastEventAt || 'UNOBSERVED'}</div>}
      {agents.map(agent => <div key={`${agent.kind}-${agent.id}`} className="p-3 border border-white/10 rounded-lg bg-[var(--carbon-deep)] flex gap-3">
        {agent.kind === 'executor' ? <Cpu size={18} className="text-[var(--red-laser)] shrink-0" /> : <BrainCircuit size={18} className="text-[var(--red-laser)] shrink-0" />}
        <div className="min-w-0 flex-1 break-words">
          <div className="text-sm font-bold text-white">{agent.name}</div>
          <div className="text-[10px] text-[var(--text-main)]">{agent.kind.toUpperCase()} · {agent.status}</div>
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">{agent.description}</p>
          {agent.persistedStatus && agent.persistedStatus !== agent.status && <p className="mt-1 text-[10px] text-[var(--text-muted)]">Persisted task state: {agent.persistedStatus}; current job state takes precedence.</p>}
          <details className="mt-2 text-[10px] text-[var(--text-dim)]" open>
            <summary className="cursor-pointer text-[var(--text-main)]">READBACK PROVENANCE</summary>
            <div className="mt-1 break-all">Source: {agent.source}<br />{agent.jobId && <>Job: {agent.jobId}<br /></>}{agent.runId && <>Run: {agent.runId}<br /></>}{agent.taskId && <>Task: {agent.taskId}<br /></>}{agent.updatedAt && <>Persisted task timestamp: {agent.updatedAt}</>}</div>
          </details>
        </div>
      </div>)}
      {!agents.length && <p className="text-[11px] text-[var(--text-dim)]">{isLoading ? 'Reading the authenticated agent registry…' : readbackError ? 'Agent readback unavailable.' : 'No persisted agent tasks were returned for the selected scope.'}</p>}
    </div>
  </Modal>;
}
