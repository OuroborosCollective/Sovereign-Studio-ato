/**
 * OpenHands Job Truth Card - Shows real OpenHands job status from runtime state
 * 
 * Displays: erkannt | startet | läuft | blockiert | Draft PR bereit
 * Only shows when a code/Draft PR task is detected in the chat.
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

// Map OpenHands status to TruthCard stage
function mapJobStatusToStage(status: OpenHandsJobStatus): TruthCardStage {
  switch (status) {
    case 'idle': return 'erkannt';
    case 'queued': return 'startet';
    case 'running': return 'läuft';
    case 'waiting-for-user': return 'läuft';
    case 'blocked': return 'blockiert';
    case 'failed': return 'blockiert';
    case 'completed': return 'draft-pr-bereit';
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

function StageIndicator({ stage, isActive }: { stage: TruthCardStage; isActive: boolean }) {
  const config = STAGE_CONFIG[stage];
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 4,
        opacity: isActive ? 1 : 0.4,
        transition: 'opacity 0.3s',
      }}
    >
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: '50%',
          background: isActive ? config.bgColor : C.textMuted + '20',
          border: `2px solid ${isActive ? config.color : C.textMuted + '40'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 14,
          transition: 'all 0.3s',
        }}
      >
        {isActive ? config.icon : ''}
      </div>
      <span
        style={{
          fontSize: 10,
          color: isActive ? config.color : C.textMuted,
          fontWeight: isActive ? 600 : 400,
        }}
      >
        {config.label}
      </span>
    </div>
  );
}

function StageConnector({ isActive }: { isActive: boolean }) {
  return (
    <div
      style={{
        flex: 1,
        height: 2,
        background: isActive ? C.green : C.textMuted + '30',
        margin: '0 4px',
        marginBottom: 22,
        transition: 'background 0.3s',
      }}
    />
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

  const stage: TruthCardStage = mapJobStatusToStage(job.status);
  const config = STAGE_CONFIG[stage];
  
  // Get stage order for progress indicator
  const stages: TruthCardStage[] = ['erkannt', 'startet', 'läuft', 'blockiert', 'draft-pr-bereit'];
  const currentIndex = stages.indexOf(stage);

  // Check if this is a terminal state that should show action buttons
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
          marginBottom: 12,
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

      {/* Stage Progress */}
      <div style={{ display: 'flex', alignItems: 'flex-start', marginBottom: 14 }}>
        {stages.slice(0, -1).map((s, idx) => (
          <React.Fragment key={s}>
            <StageIndicator stage={s} isActive={idx <= currentIndex} />
            {idx < stages.length - 2 && <StageConnector isActive={idx < currentIndex} />}
          </React.Fragment>
        ))}
      </div>

      {/* Status Details */}
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
      </div>

      {/* Action Buttons - only show based on state */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {/* Show Start button when erkannt */}
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

        {/* Show Preview button when erkannt or startet */}
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

        {/* Show Cancel button when running */}
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

        {/* Show Open Draft PR button when draft is ready */}
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

        {/* Show Retry for blocked */}
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
