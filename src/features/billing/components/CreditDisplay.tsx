/**
 * CreditDisplay — TopBar badge showing current credit balance and EUR value.
 *
 * Only renders when the user is logged in (credits prop provided and ≥ 0).
 * "Low" threshold is < 50 credits AND credits > 0 to avoid false alarm on
 * anonymous / unloaded state where credits = 0.
 *
 * Issue #458
 */

import React from 'react';
import { EUR_PER_CREDIT } from '../costConfig';

interface CreditDisplayProps {
  credits: number;
  className?: string;
}

export function CreditDisplay({ credits, className = '' }: CreditDisplayProps) {
  const eurValue = (credits * EUR_PER_CREDIT).toFixed(2);
  // isLow only triggers when user has *some* credits but is running out.
  // credits === 0 at startup (anonymous) should not show a red warning.
  const isLow = credits > 0 && credits < 50;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        padding: '3px 8px',
        borderRadius: 8,
        border: `1px solid ${isLow ? 'rgba(248,113,113,0.25)' : 'rgba(251,191,36,0.2)'}`,
        background: isLow ? 'rgba(239,68,68,0.08)' : 'rgba(245,158,11,0.08)',
        flexShrink: 0,
      }}
      title={`${credits.toLocaleString('de-DE')} Credits ≈ €${eurValue}`}
      className={className}
    >
      <span
        style={{
          fontFamily: 'monospace',
          fontSize: 10,
          fontWeight: 700,
          color: isLow ? '#f87171' : '#fbbf24',
          letterSpacing: 0,
        }}
      >
        {credits.toLocaleString('de-DE')}
      </span>
      <span
        style={{
          fontSize: 9,
          fontWeight: 600,
          color: isLow ? 'rgba(248,113,113,0.7)' : 'rgba(251,191,36,0.6)',
        }}
      >
        CR
      </span>
    </div>
  );
}
