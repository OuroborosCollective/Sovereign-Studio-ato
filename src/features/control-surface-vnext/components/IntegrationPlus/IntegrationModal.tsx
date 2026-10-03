import React from 'react';
import { Blocks, Link2Off, ShieldCheck } from 'lucide-react';
import { Modal } from '../Modal';
import { RegistryReadbackStatus, type RegistryReadbackStatusProps } from '../RegistryReadbackStatus';
import type { IntegrationAttachment } from '../../types/domain';

interface Props extends RegistryReadbackStatusProps { isOpen: boolean; onClose: () => void; integrations: IntegrationAttachment[]; }

export function IntegrationModal({ isOpen, onClose, integrations, ...readback }: Props) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="INTEGRATION ARCHITECTURE // READBACK REGISTRY">
      <div className="space-y-3 font-mono">
        <RegistryReadbackStatus {...readback} />
        <div className="p-3 rounded border border-white/5 bg-[var(--carbon-surface)] text-[10.5px] text-[var(--text-muted)] flex items-start gap-2"><ShieldCheck size={14} className="text-[var(--emerald-seal)] shrink-0" /><span>Observed backend integrations and their actual verification boundaries. A configured or isolated service is not a verified attachment or permission to execute tools.</span></div>
        {integrations.map((item) => <div key={item.id} className="p-3 rounded-lg border border-white/5 bg-[var(--carbon-deep)] flex gap-3"><Blocks size={17} className="text-[var(--red-laser)] shrink-0" /><div className="min-w-0 flex-1"><div className="text-white font-bold">{item.name}</div><div className="text-[10px] text-[var(--text-main)] mt-1">{item.status}</div>{item.blocker && <div className="mt-1 text-[10px] text-[var(--red-alert)] break-words">{item.blocker}</div>}<p className="text-[10px] text-[var(--text-muted)] mt-1">{item.boundary}</p><details className="mt-2 text-[9px] text-[var(--text-dim)]" open><summary className="cursor-pointer text-[var(--text-main)]">READBACK PROVENANCE</summary><div className="mt-1 break-all">Source: {item.source}<br />Observed: {item.observedAt}<br /><span>{item.readbackSha256}</span></div></details></div></div>)}
        {integrations.length === 0 && <div className="py-8 text-center text-[var(--text-dim)]"><Link2Off size={20} className="mx-auto mb-2 opacity-50" /><div className="text-xs">{readback.isLoading ? 'READING INTEGRATIONS…' : readback.readbackError ? 'INTEGRATION READBACK UNAVAILABLE' : 'NO INTEGRATIONS RETURNED IN SERVER READBACK'}</div></div>}
      </div>
    </Modal>
  );
}
