import React, { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, ShieldCheck } from 'lucide-react';
import { Modal } from '../Modal';
import type { OwnerInteraction, OwnerInteractionResponse } from '../../types/domain';

interface Props {
  interaction: OwnerInteraction | undefined;
  onSubmit: ((res: OwnerInteractionResponse) => void) | ((interactionId: string, response: string) => void);
  isSubmitting?: boolean;
}

export function OwnerInteractionModal({ interaction, onSubmit, isSubmitting = false }: Props) {
  const [text, setText] = useState('');
  const [dismissedId, setDismissedId] = useState<string | null>(null);
  useEffect(() => { if (interaction?.id && interaction.id !== dismissedId) setText(''); }, [interaction?.id, dismissedId]);
  if (!interaction || dismissedId === interaction.id) return null;

  const dispatchResponse = (response: string) => {
    if (!response.trim()) return;
    if (onSubmit.length === 1) {
      (onSubmit as (res: OwnerInteractionResponse) => void)({ interactionId: interaction.id, response: response.trim() });
    } else {
      (onSubmit as (id: string, res: string) => void)(interaction.id, response.trim());
    }
    setText('');
  };

  return (
    <Modal isOpen onClose={() => setDismissedId(interaction.id)} title="HUMAN-IN-THE-LOOP // OWNER DIRECTIVE REQUIRED">
      <div className="space-y-4 font-mono">
        <div className="p-3.5 rounded-lg bg-[rgba(255,140,0,0.12)] border border-[var(--red-alert)] flex items-start gap-3">
          <AlertTriangle size={20} className="text-[var(--red-alert)] shrink-0 mt-0.5 animate-pulse" />
          <div><div className="text-[11px] font-bold text-white uppercase tracking-wider mb-1">PERSISTED RUN IS WAITING FOR OWNER INPUT</div><div className="text-xs text-[var(--text-main)] leading-relaxed whitespace-pre-wrap">{interaction.prompt}</div>{interaction.context && <div className="mt-2 text-[9px] text-[var(--text-dim)]">NEXT ACTION: {interaction.context}</div>}</div>
        </div>
        {interaction.options && interaction.options.length > 0 && <div><div className="text-[9.5px] uppercase tracking-wider text-[var(--text-muted)] mb-2">SERVER-SUPPLIED OPTION</div><div className="flex flex-wrap gap-2">{interaction.options.map((option) => <button key={option} type="button" onClick={() => dispatchResponse(option)} disabled={isSubmitting} className="px-3 py-1.5 text-xs font-bold bg-[var(--carbon-deep)] border border-white/10 hover:border-[var(--red-laser)] text-white rounded-md disabled:opacity-50">&gt; {option}</button>)}</div></div>}
        {interaction.requiresText && <div className="flex flex-col gap-2 pt-2 border-t border-white/5"><label htmlFor="vnext-owner-evidence" className="text-[9.5px] uppercase tracking-wider text-[var(--text-muted)]">OWNER EVIDENCE / DIRECTIVE</label><textarea id="vnext-owner-evidence" value={text} onChange={(event) => setText(event.target.value)} disabled={isSubmitting} placeholder="Provide the exact owner response. This is sent to the persisted run resume endpoint." className="w-full bg-[var(--carbon-deep)] border border-white/10 text-white p-3 rounded-lg outline-none resize-none text-xs focus:border-[var(--red-laser)] min-h-[72px]" rows={3}/><div className="grid grid-cols-2 gap-2"><button type="button" onClick={() => setDismissedId(interaction.id)} className="min-h-10 rounded border border-white/10 text-[var(--text-muted)] hover:text-white">NOT NOW</button><button type="button" onClick={() => dispatchResponse(text)} disabled={isSubmitting || !text.trim()} className="min-h-10 bg-[var(--red-pulse)] text-white font-bold flex items-center justify-center gap-2 rounded-md disabled:opacity-40">{isSubmitting ? <><Loader2 size={13} className="animate-spin" /> RESUMING…</> : <>SUBMIT TO RUN <ShieldCheck size={13} /></>}</button></div></div>}
      </div>
    </Modal>
  );
}
