import React, { useMemo, useState } from 'react';
import { createSovereignAgentClient } from '../product/runtime/sovereignAgentClient';
import {
  resolveSovereignAgentConfig,
  type SovereignAgentJobSnapshot,
} from '../product/runtime/sovereignAgentRuntime';
import { RescuePanel } from './RescuePanel';

/**
 * Current-session Rescue bridge.
 *
 * Rescue never adopts the backend's "latest" persisted job. The only job it
 * can publish is one returned through this overlay's own onJobReady callback,
 * followed by a fresh job readback and the canonical Draft-PR preparation gate.
 */
export function SovereignRescueOverlay() {
  const [open, setOpen] = useState(false);
  const [job, setJob] = useState<SovereignAgentJobSnapshot | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const config = useMemo(() => resolveSovereignAgentConfig(), []);
  const client = useMemo(() => createSovereignAgentClient({ config }), [config]);

  const adoptRescueJob = async (jobId: string): Promise<void> => {
    const snapshot = await client.getJob(jobId);
    if (snapshot.jobId !== jobId) throw new Error('Rescue job readback identity mismatch.');
    setJob(snapshot);
    setMessage(`Rescue-Job ${jobId.slice(0, 12)} revisionsgebunden zurückgelesen.`);
  };

  const publishRescueDraftPr = async (): Promise<void> => {
    if (!job?.jobId) throw new Error('Kein aktueller Rescue-Job für Draft-PR-Publikation gebunden.');
    const current = await client.getJob(job.jobId);
    if (current.jobId !== job.jobId) throw new Error('Rescue job changed during publication readback.');
    setJob(current);

    const preparation = await client.prepareDraftPr(current.jobId);
    if (!preparation.ok || !preparation.draftPrPreparation.allowed || preparation.draftPrPreparation.canCreateDraftPr === false) {
      const blocker = preparation.draftPrPreparation.blockers.join('; ')
        || preparation.draftPrPreparation.summary
        || preparation.draftPrPreparation.nextAction
        || 'Draft-PR-Gate hat die Rescue-Veröffentlichung nicht freigegeben.';
      throw new Error(blocker);
    }

    const created = await client.createDraftPr(current.jobId);
    const next = { ...current, draftPrUrl: created.draftPrCreate.prUrl };
    setJob(next);
    setMessage(
      `Rescue Draft PR von GitHub zurückgelesen: ${created.draftPrCreate.prUrl} · Head ${created.draftPrCreate.readbackHeadSha.slice(0, 12)}`,
    );
  };

  return (
    <>
      <button
        type="button"
        aria-label="Sovereign Rescue öffnen"
        onClick={() => setOpen(true)}
        style={{
          position: 'fixed',
          right: 12,
          bottom: 82,
          zIndex: 70,
          minHeight: 42,
          padding: '0 12px',
          borderRadius: 10,
          border: '1px solid #38bdf866',
          background: '#0c4a6ecc',
          color: '#f0f9ff',
          fontWeight: 750,
          cursor: 'pointer',
        }}
      >
        Rescue
      </button>
      {message && (
        <div
          role="status"
          data-testid="sovereign-rescue-readback"
          style={{ position: 'fixed', right: 12, bottom: 132, zIndex: 69, maxWidth: 360, padding: '7px 9px', borderRadius: 8, background: '#0f172a', color: '#bae6fd', fontSize: 10 }}
        >
          {message}
        </div>
      )}
      <RescuePanel
        open={open}
        apiBaseUrl={config.agentApiUrl}
        currentJobId={job?.jobId}
        draftPrUrl={job?.draftPrUrl}
        onClose={() => setOpen(false)}
        onJobReady={adoptRescueJob}
        onPublishDraftPr={publishRescueDraftPr}
      />
    </>
  );
}

export default SovereignRescueOverlay;
