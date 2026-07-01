/**
 * CreditDisplay — TopBar badge showing current credit balance and EUR value.
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
  const isLow = credits < 50;

  return (
    <div
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border ${
        isLow
          ? 'bg-rose-500/10 border-rose-400/25'
          : 'bg-amber-500/10 border-amber-400/20'
      } ${className}`}
      title={`${credits.toLocaleString('de-DE')} Credits ≈ €${eurValue}`}
    >
      <span
        className={`text-[10px] font-black tabular-nums ${
          isLow ? 'text-rose-400' : 'text-amber-400'
        }`}
      >
        {credits.toLocaleString('de-DE')}
      </span>
      <span
        className={`text-[9px] font-bold ${
          isLow ? 'text-rose-400/70' : 'text-amber-400/60'
        }`}
      >
        CR
      </span>
      <span
        className={`text-[9px] ${
          isLow ? 'text-rose-400/40' : 'text-amber-400/40'
        }`}
      >
        ≈€{eurValue}
      </span>
    </div>
  );
}
