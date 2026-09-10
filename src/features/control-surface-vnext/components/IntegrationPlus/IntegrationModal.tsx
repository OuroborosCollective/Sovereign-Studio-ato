import React from 'react';
import { Blocks, Link2Off, ShieldCheck } from 'lucide-react';
import { Modal } from '../Modal';
import type { IntegrationAttachment } from '../../types/domain';

interface Props { isOpen: boolean; onClose: () => void; integrations: IntegrationAttachment[]; }

export function IntegrationModal({ isOpen, onClose, integrations }: Props) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="INTEGRATION ARCHITECTURE // READBACK REGISTRY">
      <div className="space-y-3 font-mono">
        <div className="p-3 rounded border border-white/5 bg-[var(--carbon-surface)] text-[10.5px] text-[var(--text-muted)] flex items-start gap-2"><ShieldCheck size={14} className="text-[var(--emerald-seal)] shrink-0" /><span>This surface is read-only. It does not invent attachment state and exposes no local connect switch. New integrations appear only after a real backend projection contract exists.</span></div>
        {integrations.map((item) => <div key={item.id} className="p-3 rounded-lg border border-white/5 bg-[var(--carbon-deep)] flex gap-3"><Blocks size={17} className="text-[var(--red-laser)] shrink-0" /><div><div className="text-white font-bold">{item.name}</div><div className="text-[9px] text-[var(--text-dim)] mt-1">{item.type} · {item.status}</div></div></div>)}
        {integrations.length === 0 && <div className="py-8 text-center text-[var(--text-dim)]"><Link2Off size={20} className="mx-auto mb-2 opacity-50" /><div className="text-xs">NO SERVER-BACKED INTEGRATION PROJECTION</div><div className="mt-1 text-[9px]">Nothing is fabricated to fill this panel.</div></div>}
      </div>
    </Modal>
  );
}
