import React, { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Check, Copy, ExternalLink, GitPullRequestDraft, Lock, ShieldAlert, ShieldCheck, Sparkles, X } from 'lucide-react';
import type { DraftPR, DraftPrPreparation, JobPhase, PublicationState } from '../../types/domain';
import { playVerificationChime } from '../../utils/audio';

interface Props {
  publication?: PublicationState;
  draftPR?: DraftPR;
  jobPhase?: JobPhase;
  preparation?: DraftPrPreparation;
  onPrepare?: () => void | Promise<void>;
  onPublish?: () => void | Promise<void>;
  isPreparing?: boolean;
  isPublishing?: boolean;
  publishError?: string;
}

export function PublicationInspector({ publication, draftPR: directDraftPR, jobPhase = 'IDLE', preparation, onPrepare, onPublish, isPreparing = false, isPublishing = false, publishError }: Props) {
  const [copiedHash, setCopiedHash] = useState(false);
  const [consentVisible, setConsentVisible] = useState(false);
  const draftPR = directDraftPR || publication?.draftPR;
  const isVerified = Boolean(draftPR?.draftVerified && draftPR.readbackVerified && draftPR.checksReadbackVerified);

  useEffect(() => { if (isVerified) playVerificationChime(); }, [isVerified, draftPR?.readbackHeadSha]);
  const copyHash = () => {
    if (!draftPR?.readbackHeadSha) return;
    void navigator.clipboard.writeText(draftPR.readbackHeadSha);
    setCopiedHash(true);
    window.setTimeout(() => setCopiedHash(false), 1600);
  };
  const prepare = async () => { setConsentVisible(false); await onPrepare?.(); };
  useEffect(() => { if (preparation?.allowed) setConsentVisible(true); }, [preparation?.allowed, preparation?.decision, preparation?.headBranch]);

  return (
    <div className="flex flex-col h-full bg-[var(--carbon-deep)] p-3 overflow-hidden" data-testid="vnext-publication-inspector">
      <div className="flex items-center justify-between border-b border-white/5 pb-2 mb-2">
        <div className="flex items-center gap-1.5 font-mono text-[11px] font-bold text-white uppercase tracking-wider"><GitPullRequestDraft size={13} className="text-[var(--red-laser)]" /> PUBLICATION INSPECTOR</div>
        {isVerified && <span className="flex items-center gap-1 font-mono text-[9px] px-1.5 py-0.5 rounded bg-[rgba(16,185,129,0.15)] text-[var(--emerald-seal)] border border-[rgba(16,185,129,0.3)] font-bold"><ShieldCheck size={10} /> GITHUB READBACK VERIFIED</span>}
      </div>

      <div className="flex-1 overflow-y-auto font-mono text-[10.5px] space-y-2.5">
        {draftPR && isVerified ? (
          <>
            <AnimatePresence>
              <motion.div key="verified" initial={{ opacity: 0, scale: 0.4, rotate: -160 }} animate={{ opacity: 1, scale: [0.4, 1.15, 1], rotate: [-160, 8, 0] }} transition={{ duration: 0.78 }} className="theme-diamond-cut p-2.5 rounded-lg bg-[rgba(16,185,129,0.14)] border border-[var(--emerald-seal)] shadow-[0_0_22px_rgba(16,185,129,0.28)] flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-full bg-[var(--emerald-seal)] text-black flex items-center justify-center shadow-[0_0_12px_#10b981]"><Lock size={14} strokeWidth={2.6} /></div>
                <div><div className="flex items-center gap-1.5 text-[10px] font-bold text-[var(--emerald-seal)] tracking-wider">DRAFT PR VERIFIED <Sparkles size={11} /></div><div className="text-[8.5px] text-[var(--text-muted)]">Open + draft + exact head readback + check-state readback.</div></div>
              </motion.div>
            </AnimatePresence>
            <div className="theme-diamond-cut p-3 rounded-lg border border-[rgba(16,185,129,0.35)] bg-[rgba(16,185,129,0.04)] space-y-2">
              <div className="flex justify-between gap-3"><span className="text-[var(--text-dim)]">PR</span><span className="text-white font-bold">#{draftPR.pullRequestNumber}</span></div>
              <div className="flex justify-between gap-3"><span className="text-[var(--text-dim)]">BRANCH</span><span className="text-white truncate">{draftPR.branch} → {draftPR.baseBranch}</span></div>
              <div className="flex justify-between gap-3"><span className="text-[var(--text-dim)]">CI</span><span className={draftPR.ciState === 'failure' ? 'text-[var(--red-alert)]' : draftPR.ciState === 'success' ? 'text-[var(--emerald-seal)]' : 'text-[var(--text-main)]'}>{draftPR.ciState.toUpperCase()} · {draftPR.checksSuccessCount}/{draftPR.checkRunCount} success</span></div>
              <div className="pt-2 border-t border-white/5"><div className="text-[9px] text-[var(--text-dim)]">READBACK HEAD SHA</div><button type="button" onClick={copyHash} className="mt-1 w-full flex items-center justify-between gap-2 p-2 rounded bg-[var(--carbon-base)] border border-white/5 text-[var(--emerald-seal)] text-left"><span className="truncate">{draftPR.readbackHeadSha}</span>{copiedHash ? <Check size={11} /> : <Copy size={11} />}</button></div>
              <a href={draftPR.url} target="_blank" rel="noreferrer" className="min-h-10 flex items-center justify-center gap-2 rounded bg-[rgba(16,185,129,0.1)] border border-[rgba(16,185,129,0.25)] text-[var(--emerald-seal)] font-bold">OPEN VERIFIED DRAFT PR <ExternalLink size={12} /></a>
            </div>
          </>
        ) : (
          <>
            <div className="p-3 rounded-lg bg-[var(--carbon-surface)] border border-white/5 text-[var(--text-muted)] leading-relaxed">Publication stays empty until Sovereign returns complete GitHub Draft-PR/head-SHA/check readback evidence. A completed repository job alone is not publication proof.</div>
            {jobPhase === 'READY_TO_PUBLISH' && !preparation && <button type="button" data-testid="vnext-prepare-draft-pr" onClick={() => void prepare()} disabled={isPreparing} className="w-full min-h-11 rounded-lg bg-[rgba(255,30,56,0.12)] border border-[var(--red-laser)] text-[var(--red-laser)] hover:bg-[var(--red-laser)] hover:text-white font-black tracking-wider disabled:opacity-40">{isPreparing ? 'READING DRAFT-PR GATE…' : 'READ DRAFT-PR GATE'}</button>}
            {preparation && !preparation.allowed && <div className="p-3 rounded-lg border border-[var(--red-alert)] bg-[rgba(255,140,0,0.08)] text-[var(--red-alert)] space-y-1"><div className="font-bold flex items-center gap-1.5"><ShieldAlert size={13} /> PUBLICATION BLOCKED</div><div>{preparation.blockers.join('; ') || preparation.summary || preparation.nextAction || preparation.decision}</div></div>}
            {preparation?.allowed && consentVisible && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-3.5 rounded-lg border border-[var(--red-laser)] bg-[rgba(255,30,56,0.08)] shadow-[0_0_18px_rgba(255,30,56,0.12)]"
                data-testid="vnext-draft-pr-consent"
                role="group"
                aria-labelledby="vnext-draft-pr-consent-title"
              >
                <div id="vnext-draft-pr-consent-title" className="text-white font-black tracking-wider mb-2">EXTERNAL WRITE CONSENT</div>
                <div className="text-[var(--text-muted)] leading-relaxed space-y-1"><div>Action: create exactly one GitHub <strong className="text-white">Draft PR</strong>.</div><div>Branch: <span className="text-white">{preparation.headBranch || 'backend-selected'}</span> → <span className="text-white">{preparation.baseBranch || 'main'}</span>.</div><div>No merge. No push to main. Success is shown only after independent GitHub readback.</div></div>
                <div className="grid grid-cols-2 gap-2 mt-3"><button type="button" onClick={() => setConsentVisible(false)} className="min-h-10 rounded border border-white/10 text-[var(--text-muted)] hover:text-white flex items-center justify-center gap-1"><X size={12} /> DECLINE</button><button type="button" data-testid="vnext-create-draft-pr" onClick={() => void onPublish?.()} disabled={isPublishing} className="min-h-10 rounded bg-[var(--red-pulse)] text-white font-black disabled:opacity-40">{isPublishing ? 'CREATING + VERIFYING…' : 'CREATE DRAFT PR'}</button></div>
              </motion.div>
            )}
            {publishError && <div className="p-2.5 rounded border border-[var(--red-alert)] bg-[rgba(255,30,56,0.08)] text-[var(--red-alert)]">{publishError}</div>}
          </>
        )}
      </div>
    </div>
  );
}
