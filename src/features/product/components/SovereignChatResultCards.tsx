import React from 'react';
import type { SovereignChatResultCard } from '../runtime/sovereignChatWorkbenchResults';

export interface SovereignChatResultCardsProps {
  readonly cards: readonly SovereignChatResultCard[];
}

function cardToneClass(kind: SovereignChatResultCard['kind']): string {
  if (kind === 'draft-pr') return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-50';
  if (kind === 'stopper') return 'border-rose-400/30 bg-rose-500/10 text-rose-50';
  if (kind === 'completed') return 'border-amber-300/30 bg-amber-500/10 text-amber-50';
  return 'border-cyan-400/25 bg-slate-950/70 text-slate-100';
}

function safeCardKey(card: SovereignChatResultCard, index: number): string {
  return `${card.kind}:${card.title}:${index}`;
}

export function SovereignChatResultCards({ cards }: SovereignChatResultCardsProps): React.ReactElement | null {
  if (!cards.length) return null;

  return (
    <div className="mt-3 grid gap-2" aria-label="OpenHands Ergebnis-Karten" data-testid="sovereign-chat-result-cards">
      {cards.map((card, index) => (
        <div
          key={safeCardKey(card, index)}
          className={`rounded-2xl border p-3 text-sm ${cardToneClass(card.kind)}`}
          data-result-card-kind={card.kind}
        >
          <p className="text-xs font-black uppercase tracking-wide opacity-80">{card.title}</p>
          <p className="mt-1 whitespace-pre-wrap">{card.message}</p>
          {card.items?.length ? (
            <ul className="mt-2 space-y-1 text-xs opacity-90">
              {card.items.map((item) => <li key={item} className="truncate">• {item}</li>)}
            </ul>
          ) : null}
          {card.actionUrl && card.actionLabel ? (
            <a
              className="mt-2 inline-flex rounded-full border border-current/30 px-3 py-1 text-xs font-black underline-offset-4 hover:underline"
              href={card.actionUrl}
              target="_blank"
              rel="noreferrer"
            >
              {card.actionLabel}
            </a>
          ) : null}
        </div>
      ))}
    </div>
  );
}
