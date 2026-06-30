/**
 * DraftPrCard - Compact inline card for Draft PR and build status
 * 
 * Shows:
 * - title: Draft PR ready
 * - branch or PR URL if available
 * - changed file count from OpenHandsJobSnapshot.changedFiles
 * - buttons: open browser, discuss in chat
 */

import React from 'react';

const C = {
  bg:        '#0e1116',
  surface:   '#161c24',
  border:    '#232d3a',
  accent:    '#00d9b1',
  text:      '#cdd9e5',
  textSub:   '#768390',
  green:     '#34d399',
  sky:       '#22d3ee',
};

export interface DraftPrCardProps {
  url: string;
  changedFiles: number | string[];
  onOpenBrowser: () => void;
  onDiscussInChat: () => void;
}

export const DraftPrCard: React.FC<DraftPrCardProps> = ({
  url,
  changedFiles,
  onOpenBrowser,
  onDiscussInChat,
}) => {
  // Extract branch from URL - pull numbers are numeric
  const urlParts = url.split('/');
  const lastPart = urlParts[urlParts.length - 1];
  const branch = lastPart && /^\d+$/.test(lastPart) 
    ? `PR #${lastPart}` 
    : (lastPart || 'unbekannt');
  
  // Handle changedFiles being either a number or array of file paths
  const fileCount = Array.isArray(changedFiles) 
    ? changedFiles.length 
    : (typeof changedFiles === 'number' ? changedFiles : 0);

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
      {/* Header */}
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

      {/* Changed files */}
      <div style={{ fontSize: 12, color: C.textSub }}>
        {fileCount > 0 ? (
          <span>{fileCount} geänderte Datei{fileCount !== 1 ? 'en' : ''}</span>
        ) : (
          <span style={{ fontStyle: 'italic' }}>Keine Dateien geändert</span>
        )}
      </div>

      {/* Actions */}
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
