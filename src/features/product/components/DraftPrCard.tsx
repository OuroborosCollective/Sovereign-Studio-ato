/**
 * DraftPrCard - Compact inline card for Draft PR and build status
 *
 * Shows only real Draft PR state supplied by the OpenHands/GitHub runtime path.
 * The build badge defaults to unknown so the UI never invents a green run.
 */

import React from 'react';
import type { DraftPrBuildStatusResult } from '../runtime/draftPrBuildStatusRuntime';

const C = {
  bg:        '#0e1116',
  surface:   '#161c24',
  border:    '#232d3a',
  accent:    '#00d9b1',
  text:      '#cdd9e5',
  textSub:   '#768390',
  green:     '#34d399',
  sky:       '#22d3ee',
  amber:     '#fbbf24',
  rose:      '#fb7185',
};

const DEFAULT_BUILD_STATUS: DraftPrBuildStatusResult = {
  state: 'unknown',
  label: 'Build unbekannt',
  detail: 'Keine GitHub Workflow-Runs sichtbar; kein grüner Status wird erfunden.',
};

const BUILD_COLOR: Record<DraftPrBuildStatusResult['state'], string> = {
  success: C.green,
  failure: C.rose,
  running: C.sky,
  pending: C.amber,
  unknown: C.textSub,
};

export interface DraftPrCardProps {
  url: string;
  changedFiles: number | string[];
  onOpenBrowser: () => void;
  onDiscussInChat: () => void;
  buildStatus?: DraftPrBuildStatusResult;
}

function extractPrLabel(url: string): string {
  const urlParts = url.split('/');
  const lastPart = urlParts[urlParts.length - 1];
  return lastPart && /^\d+$/.test(lastPart)
    ? `PR #${lastPart}`
    : (lastPart || 'unbekannt');
}

export const DraftPrCard: React.FC<DraftPrCardProps> = ({
  url,
  changedFiles,
  onOpenBrowser,
  onDiscussInChat,
  buildStatus = DEFAULT_BUILD_STATUS,
}) => {
  const branch = extractPrLabel(url);
  const fileCount = Array.isArray(changedFiles)
    ? changedFiles.length
    : (typeof changedFiles === 'number' ? changedFiles : 0);
  const buildColor = BUILD_COLOR[buildStatus.state];

  return (
    <div
      role="region"
      aria-label="Draft PR Karte"
      data-testid="draft-pr-card"
      style={{
        margin: '8px 0',
        padding: '12px 16px',
        borderRadius: 12,
        background: C.surface,
        border: `1px solid ${C.accent}40`,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 16 }}>📝</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, color: C.accent, fontSize: 14 }}>
            Draft PR ready
          </div>
          <div style={{ fontSize: 12, color: C.textSub, marginTop: 2 }}>
            Branch: <code style={{ color: C.text }}>{branch}</code>
          </div>
        </div>
      </div>

      <div
        data-testid="draft-pr-build-badge"
        aria-label={`Buildstatus: ${buildStatus.label}`}
        style={{
          borderRadius: 8,
          border: `1px solid ${buildColor}40`,
          background: `${buildColor}12`,
          padding: '8px 10px',
          fontSize: 12,
          color: C.textSub,
        }}
      >
        <div style={{ color: buildColor, fontWeight: 600 }}>
          {buildStatus.label}
        </div>
        <div style={{ marginTop: 2 }}>{buildStatus.detail}</div>
        {buildStatus.runUrl ? (
          <a href={buildStatus.runUrl} target="_blank" rel="noreferrer" style={{ color: C.sky, marginTop: 4, display: 'inline-block' }}>
            Run öffnen
          </a>
        ) : null}
      </div>

      <div style={{ fontSize: 12, color: C.textSub }}>
        {fileCount > 0 ? (
          <span>{fileCount} geänderte Datei{fileCount !== 1 ? 'en' : ''}</span>
        ) : (
          <span style={{ fontStyle: 'italic' }}>Keine Dateien geändert</span>
        )}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <button
          type="button"
          onClick={onOpenBrowser}
          style={{
            padding: '6px 12px',
            borderRadius: 8,
            background: C.accent + '20',
            border: `1px solid ${C.accent}40`,
            color: C.accent,
            fontSize: 12,
            fontWeight: 500,
            cursor: 'pointer',
          }}
          aria-label="Öffne PR im Browser"
        >
          Im Browser öffnen
        </button>

        <button
          type="button"
          onClick={onDiscussInChat}
          style={{
            padding: '6px 12px',
            borderRadius: 8,
            background: C.sky + '15',
            border: `1px solid ${C.sky}30`,
            color: C.sky,
            fontSize: 12,
            fontWeight: 500,
            cursor: 'pointer',
          }}
          aria-label="Im Chat besprechen"
        >
          Im Chat besprechen
        </button>
      </div>
    </div>
  );
};

export default DraftPrCard;
