import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Check, Loader2, ShieldCheck, X } from 'lucide-react';
import { Modal } from '../Modal';
import type { OwnerInteraction, OwnerInteractionResponse } from '../../types/domain';

interface Props {
  interaction: OwnerInteraction | undefined;
  onSubmit: (res: OwnerInteractionResponse) => void;
  isSubmitting?: boolean;
}

export function OwnerInteractionModal({ interaction, onSubmit, isSubmitting = false }: Props) {
  const [text, setText] = useState('');
  const [dismissedId, setDismissedId] = useState<string | null>(null);
  const dismissRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (interaction?.id && interaction.id !== dismissedId) setText('');
  }, [interaction?.id, dismissedId]);

  if (!interaction || dismissedId === interaction.id) return null;

  const isApproval = interaction.kind === 'approval' || interaction.id.startsWith('approval-');
  const dispatchResponse = (response: string) => {
    const normalized = response.trim();
    if (!normalized) return;
    if (isApproval && normalized.toLowerCase() !== 'approve' && normalized.toLowerCase() !== 'reject') return;

    onSubmit({ interactionId: interaction.id, response: normalized });
    setText('');
  };

  const decisionOptions = interaction.options?.filter((option) => {
    const normalized = option.trim().toLowerCase();
    return normalized === 'approve' || normalized === 'reject';
  }) ?? [];
  const hasDecisionButtons = isApproval && decisionOptions.length > 0;
  const safeDecision = decisionOptions.find((option) => option.trim().toLowerCase() === 'reject') ?? 'reject';
  const affirmativeDecision = decisionOptions.find((option) => option.trim().toLowerCase() === 'approve') ?? 'approve';

  return (
    <Modal
      isOpen
      onClose={() => setDismissedId(interaction.id)}
      title={isApproval ? 'OWNER AUTHORITY // ACTION DECISION REQUIRED' : 'HUMAN-IN-THE-LOOP // OWNER DIRECTIVE REQUIRED'}
      initialFocusRef={dismissRef}
    >
      <div className="sovereign-action-surface space-y-4 font-mono" role="group" aria-label={isApproval ? 'Pending action approval' : 'Pending owner directive'}>
        <div className="sovereign-action-header">
          <div className="flex items-start gap-3">
            <span className="sovereign-action-mark" aria-hidden="true">
              {isApproval ? <ShieldCheck size={18} /> : <AlertTriangle size={18} />}
            </span>
            <div className="min-w-0">
              <div className="sovereign-instrument-label">{isApproval ? 'ACTION PREVIEW / AWAITING OWNER DECISION' : 'PERSISTED RUN / AWAITING OWNER INPUT'}</div>
              <p className="mt-1 text-xs leading-relaxed text-[var(--text-main)]">
                {isApproval ? 'The server has paused this persisted run. Review the exact server-supplied request before choosing a decision.' : 'The server has paused this persisted run and is waiting for an explicit owner response.'}
              </p>
            </div>
          </div>
        </div>

        <dl className="sovereign-action-facts">
          <div>
            <dt>REQUEST</dt>
            <dd>{interaction.kind || 'owner-directive'}</dd>
          </div>
          <div>
            <dt>REQUEST ID</dt>
            <dd className="break-all">{interaction.id}</dd>
          </div>
          {interaction.context && (
            <div className="sm:col-span-2">
              <dt>NEXT SERVER ACTION</dt>
              <dd>{interaction.context}</dd>
            </div>
          )}
        </dl>

        <section className="sovereign-action-verbatim" aria-labelledby="sovereign-action-reason-label">
          <div id="sovereign-action-reason-label" className="sovereign-instrument-label">SERVER REQUEST / VERBATIM REASON</div>
          <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-white">{interaction.prompt}</p>
        </section>

        {hasDecisionButtons && (
          <div className="sovereign-action-decision" aria-label="Owner decision">
            <p className="sovereign-consent-hint">
              Decline is the least-authority path. No action is executed until an explicit decision reaches the server.
            </p>
            <div className="grid grid-cols-2 gap-2">
              <button
                ref={dismissRef}
                type="button"
                onClick={() => dispatchResponse(safeDecision)}
                disabled={isSubmitting}
                className="sovereign-decision-reject"
              >
                <X size={14} aria-hidden="true" />
                {safeDecision.toUpperCase()}
              </button>
              <button
                type="button"
                onClick={() => dispatchResponse(affirmativeDecision)}
                disabled={isSubmitting}
                className="sovereign-decision-approve"
              >
                {isSubmitting ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Check size={14} aria-hidden="true" />}
                {isSubmitting ? 'SUBMITTING…' : affirmativeDecision.toUpperCase()}
              </button>
            </div>
          </div>
        )}

        {interaction.requiresText && (
          <div className="sovereign-action-decision space-y-2">
            <label htmlFor="vnext-owner-evidence" className="sovereign-instrument-label">OWNER EVIDENCE / DIRECTIVE</label>
            <p id="vnext-owner-evidence-help" className="text-[10px] leading-relaxed text-[var(--text-muted)]">
              {isApproval ? 'This protected approval endpoint accepts exactly: approve or reject.' : 'The response is sent verbatim to the persisted run resume endpoint.'}
            </p>
            <textarea
              id="vnext-owner-evidence"
              aria-describedby="vnext-owner-evidence-help"
              value={text}
              onChange={(event) => setText(event.target.value)}
              disabled={isSubmitting}
              placeholder={isApproval ? 'approve or reject' : 'Enter the exact owner response.'}
              className="w-full min-h-[88px] resize-y border border-white/10 bg-[var(--carbon-deep)] p-3 text-xs text-white outline-none focus:border-[var(--red-laser)]"
              rows={4}
            />
            <div className="grid grid-cols-2 gap-2">
              <button ref={hasDecisionButtons ? undefined : dismissRef} type="button" onClick={() => setDismissedId(interaction.id)} className="sovereign-decision-reject min-h-10">
                NOT NOW
              </button>
              <button type="button" onClick={() => dispatchResponse(text)} disabled={isSubmitting || !text.trim()} className="sovereign-decision-approve min-h-10">
                {isSubmitting ? <><Loader2 size={14} className="animate-spin" aria-hidden="true" /> RESUMING…</> : <>SEND DIRECTIVE <ShieldCheck size={14} aria-hidden="true" /></>}
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
