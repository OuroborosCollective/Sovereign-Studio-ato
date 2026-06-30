import React, { useState, useCallback } from 'react';

// Design tokens from BuilderContainer
const C = {
  bg: '#0e1116',
  surface: '#161c24',
  border: '#232d3a',
  borderHov: '#2e3d50',
  accent: '#00d9b1',
  accentDim: '#00d9b122',
  orange: '#f97316',
  text: '#cdd9e5',
  textSub: '#768390',
  textMuted: '#3d4f61',
  green: '#34d399',
  sky: '#22d3ee',
  amber: '#fbbf24',
  rose: '#fb7185',
};

export interface ExternalRouteConsentGateProps {
  onApprove: () => void;
  onDeny: () => void;
  attempts?: number;
}

/**
 * Consent gate shown when no-key routes are blocked and all other routes failed.
 * Allows users to explicitly opt-in to free external routes for this request only.
 */
export function ExternalRouteConsentGate({ onApprove, onDeny, attempts = 0 }: ExternalRouteConsentGateProps) {
  return (
    <div
      style={{
        background: C.surface,
        border: `1px solid ${C.orange}`,
        borderRadius: 12,
        padding: '16px',
        marginBottom: 12,
      }}
    >
      {/* Warning header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 12,
          marginBottom: 12,
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: '50%',
            background: `${C.orange}20`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 18,
            flexShrink: 0,
          }}
        >
          ⚠️
        </div>
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: C.orange,
              marginBottom: 4,
            }}
          >
            Limits erreicht – Notfall Free-Routen aktivieren?
          </div>
          <div
            style={{
              fontSize: 12,
              color: C.textSub,
              lineHeight: 1.5,
            }}
          >
            Alle verfügbaren LLM-Anbieter (mit API-Key) sind fehlgeschlagen oder nicht verfügbar.
            {attempts > 0 && ` (${attempts} Versuche)`}
          </div>
        </div>
      </div>

      {/* Warning body */}
      <div
        style={{
          background: `${C.orange}10`,
          borderRadius: 8,
          padding: '12px',
          marginBottom: 16,
        }}
      >
        <div
          style={{
            fontSize: 12,
            color: C.text,
            lineHeight: 1.5,
          }}
        >
          <strong style={{ color: C.orange }}>⚡ Kostenlose externe Notfall-Routen</strong> können
          deinen Auftrag und Repo-Kontext außerhalb der lokalen Runtime verarbeiten.
        </div>
        <ul
          style={{
            margin: '8px 0 0 0',
            padding: '0 0 0 20px',
            fontSize: 11,
            color: C.textSub,
            lineHeight: 1.6,
          }}
        >
          <li>Daten werden an externe Dienste (z.B. Pollinations, HuggingFace) gesendet</li>
          <li>Der Repo-Kontext wird für diese Anfrage verarbeitet</li>
          <li>Dies gilt nur für diesen einmaligen Vorgang</li>
        </ul>
      </div>

      {/* Action buttons */}
      <div
        style={{
          display: 'flex',
          gap: 12,
          justifyContent: 'flex-end',
        }}
      >
        <button
          type="button"
          onClick={onDeny}
          style={{
            padding: '8px 16px',
            borderRadius: 8,
            background: 'transparent',
            color: C.textSub,
            fontSize: 13,
            border: `1px solid ${C.border}`,
            cursor: 'pointer',
          }}
        >
          NEIN, lokal weiter
        </button>
        <button
          type="button"
          onClick={onApprove}
          style={{
            padding: '8px 16px',
            borderRadius: 8,
            background: C.orange,
            color: C.bg,
            fontSize: 13,
            fontWeight: 500,
            border: 'none',
            cursor: 'pointer',
          }}
        >
          JA, einmalig aktivieren
        </button>
      </div>
    </div>
  );
}

export default ExternalRouteConsentGate;