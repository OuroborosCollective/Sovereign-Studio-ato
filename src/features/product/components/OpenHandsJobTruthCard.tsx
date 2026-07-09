/**
 * OpenHands Job Truth Card - Shows real OpenHands job status from runtime state
 * 
 * This is NOT a progress indicator. It shows the CURRENT runtime state as a
 * status chain. The stages are not sequential steps but possible states.
 * Only shows when a code/Draft PR task is detected.
 */

import React from 'react';
import type { OpenHandsJobSnapshot, OpenHandsJobStatus } from '../runtime/openhandsEnterpriseRuntime';

// Design tokens from BuilderContainer
const C = {
  bg: '#0e1116',
  surface: '#161c24',
  border: '#232d3a',
  accent: '#00d9b1',
  text: '#cdd9e5',
  textSub: '#768390',
  textMuted: '#3d4f61',
  green: '#34d399',
  sky: '#22d3ee',
  amber: '#fbbf24',
  rose: '#fb7185',
  violet: '#a78bfa',
};

export type TruthCardStage = 'erkannt' | 'startet' | 'läuft' | 'blockiert' | 'draft-pr-bereit';

export interface OpenHandsJobTruthCardProps {
  job: OpenHandsJobSnapshot | null | undefined;
  onStart?: () => void;
  onPreview?: () => void;
  onCancel?: () => void;
  onOpenDraftPr?: () => void;
}

// Map OpenHands status to TruthCard stage.
// Runtime truth: completed alone is not Draft-PR-ready. The URL is the evidence.
function mapJobToStage(job: OpenHandsJobSnapshot): TruthCardStage {
  switch (job.status) {
    case 'idle': return 'erkannt';
    case 'queued': return 'startet';
    case 'provisioning': return 'startet';
    case 'running': return 'läuft';
    case 'waiting-for-user': return 'läuft';
    case 'validating': return 'läuft';
    case 'blocked': return 'blockiert';
    case 'failed': return 'blockiert';
    case 'completed': return job.draftPrUrl ? 'draft-pr-bereit' : 'blockiert';
    case 'cleaned': return 'blockiert';
  }
}

// Stage configuration
const STAGE_CONFIG: Record<TruthCardStage, {
  label: string;
  color: string;
  bgColor: string;
  icon: string;
}> = {
  'erkannt': { label: 'Erkannt', color: C.amber, bgColor: C.amber + '20', icon: '👁' },
  'startet': { label: 'Startet', color: C.sky, bgColor: C.sky + '20', icon: '🚀' },
  'läuft': { label: 'Läuft', color: C.violet, bgColor: C.violet + '20', icon: '⚡' },
  'blockiert': { label: 'Blockiert', color: C.rose, bgColor: C.rose + '20', icon: '⚠' },
  'draft-pr-bereit': { label: 'Draft PR bereit', color: C.green, bgColor: C.green + '20', icon: '✓' },
};

/**
 * StatusChain - Displays runtime state as discrete states, NOT as progress.
 * This is a status visualization, not a progress bar.
 */
function StatusChain({ currentStage }: { currentStage: TruthCardStage }) {
  const stages: TruthCardStage[] = ['erkannt', 'startet', 'läuft', 'blockiert', 'draft-pr-bereit'];
  const currentIndex = stages.indexOf(currentStage);
  
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        flexWrap: 'wrap',
        marginBottom: 12,
      }}
      role="list"
      aria-label="OpenHands Job Statuskette"
    >
      {stages.map((stage, idx) => {
        const config = STAGE_CONFIG[stage];
        const isCurrent = stage === currentStage;
        const isPast = idx < currentIndex;
        
        return (
          <React.Fragment key={stage}>
            {idx > 0 && (
              <span
                style={{
                  color: isPast ? C.green : C.textMuted,
                  fontSize: 10,
                  marginBottom: 8,
                }}
              >
                →
              </span>
            )}
            <div
              role="listitem"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '4px 8px',
                borderRadius: 6,
                background: isCurrent ? config.bgColor : 'transparent',
                border: isCurrent ? `1px solid ${config.color}40` : '1px solid transparent',
                opacity: isCurrent || isPast ? 1 : 0.4,
              }}
            >
              <span style={{ fontSize: 12 }}>{config.icon}</span>
              <span
                style={{
                  fontSize: 10,
                  color: isCurrent ? config.color : isPast ? C.green : C.textMuted,
                  fontWeight: isCurrent ? 600 : 400,
                }}
              >
                {config.label}
              </span>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

export const OpenHandsJobTruthCard: React.FC<OpenHandsJobTruthCardProps> = ({
  job,
  onStart,
  onPreview,
  onCancel,
  onOpenDraftPr,
}) => {
  // Don't render if no job
  if (!job) return null;

  const stage: TruthCardStage = mapJobToStage(job);
  const config = STAGE_CONFIG[stage];
  const completedWithoutDraftPr = job.status === 'completed' && !job.draftPrUrl;

  // Determine action buttons based on current state
  const isTerminalBlocked = stage === 'blockiert';
  const isDraftReady = stage === 'draft-pr-bereit';
  const isRunning = stage === 'läuft' || stage === 'startet';

  return (
    <div
      role="region"
      aria-label="OpenHands Job Status"
      data-testid="openhands-truth-card"
      style={{
        margin: '8px 0',
        padding: '14px 16px',
        borderRadius: 12,
        background: C.surface,
        border: `1px solid ${config.color}40`,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 18 }}>🤖</span>
          <span style={{ fontWeight: 600, color: C.text, fontSize: 14 }}>
            OpenHands Job
          </span>
        </div>
        <div
          style={{
            padding: '3px 10px',
            borderRadius: 12,
            background: config.bgColor,
            color: config.color,
            fontSize: 11,
            fontWeight: 600,
          }}
        >
          {config.label}
        </div>
      </div>

      {/* Status Chain - NOT progress, but current state indicator */}
      <StatusChain currentStage={stage} />

      {/* Status Details from real runtime */}
      <div
        style={{
          fontSize: 11,
          color: C.textSub,
          marginBottom: 12,
          padding: '8px 10px',
          background: C.bg,
          borderRadius: 6,
        }}
      >
        {job.openHandsId && (
          <div style={{ marginBottom: 4 }}>
            <span style={{ color: C.textMuted }}>ID:</span>{' '}
            <code style={{ color: C.text }}>{job.openHandsId}</code>
          </div>
        )}
        {job.events.length > 0 && (
          <div>
            <span style={{ color: C.textMuted }}>Letzte:</span>{' '}
            {job.events[job.events.length - 1]?.message || 'Keine Events'}
          </div>
        )}
        {job.lastError && (
          <div style={{ color: C.rose, marginTop: 4 }}>
            {job.lastError}
          </div>
        )}
        {completedWithoutDraftPr && (
          <div style={{ color: C.amber, marginTop: 4 }}>
            Sovereign Agent meldet abgeschlossen, aber keine Draft-PR-URL liegt vor. Ergebnis noch nicht belegbar.
          </div>
        )}
      </div>

      {/* Action Buttons - based on current runtime state */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {/* Start button when erkannt */}
        {stage === 'erkannt' && onStart && (
          <button
            type="button"
            onClick={onStart}
            style={{
              padding: '7px 14px',
              borderRadius: 8,
              background: C.accent,
              color: C.bg,
              fontSize: 12,
              fontWeight: 500,
              border: 'none',
              cursor: 'pointer',
            }}
          >
            🤖 OpenHands starten
          </button>
        )}

        {/* Preview button when erkannt or startet */}
        {(stage === 'erkannt' || stage === 'startet') && onPreview && (
          <button
            type="button"
            onClick={onPreview}
            style={{
              padding: '7px 14px',
              borderRadius: 8,
              background: 'transparent',
              color: C.sky,
              fontSize: 12,
              border: `1px solid ${C.sky}40`,
              cursor: 'pointer',
            }}
          >
            👁 Vorher ansehen
          </button>
        )}

        {/* Cancel button when running */}
        {isRunning && onCancel && (
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: '7px 14px',
              borderRadius: 8,
              background: 'transparent',
              color: C.rose,
              fontSize: 12,
              border: `1px solid ${C.rose}40`,
              cursor: 'pointer',
            }}
          >
            ✕ Abbrechen
          </button>
        )}

        {/* Open Draft PR button when draft is ready */}
        {isDraftReady && job.draftPrUrl && onOpenDraftPr && (
          <button
            type="button"
            onClick={onOpenDraftPr}
            style={{
              padding: '7px 14px',
              borderRadius: 8,
              background: C.green,
              color: C.bg,
              fontSize: 12,
              fontWeight: 500,
              border: 'none',
              cursor: 'pointer',
            }}
          >
            📝 Draft PR öffnen
          </button>
        )}

        {/* Retry for blocked */}
        {isTerminalBlocked && onStart && (
          <button
            type="button"
            onClick={onStart}
            style={{
              padding: '7px 14px',
              borderRadius: 8,
              background: C.amber + '20',
              color: C.amber,
              fontSize: 12,
              border: `1px solid ${C.amber}40`,
              cursor: 'pointer',
            }}
          >
            ↻ Erneut versuchen
          </button>
        )}
      </div>
    </div>
  );
};

export default OpenHandsJobTruthCard;
