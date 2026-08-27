import React, { useState, useMemo } from 'react';
import { buildOpenHandsOperatorBriefing, type BriefingSection, type BriefingItem } from '../runtime/openHandsOperatorBriefing';

const STATUS_COLORS: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  ok: { bg: 'bg-emerald-500/20', border: 'border-emerald-500/40', text: 'text-emerald-300', icon: '🟢' },
  warning: { bg: 'bg-amber-500/20', border: 'border-amber-500/40', text: 'text-amber-300', icon: '🟡' },
  blocked: { bg: 'bg-rose-500/20', border: 'border-rose-500/40', text: 'text-rose-300', icon: '🔴' },
  info: { bg: 'bg-cyan-500/20', border: 'border-cyan-500/40', text: 'text-cyan-300', icon: '🔵' },
};

function BriefingItemRow({ item }: { item: BriefingItem }) {
  const colors = STATUS_COLORS[item.status || 'info'];
  return (
    <div className="flex items-start justify-between gap-2 rounded-lg border border-slate-700/50 bg-slate-900/50 p-2">
      <span className="text-xs font-medium text-slate-300">{item.label}</span>
      <span className={`text-xs font-bold ${colors.text}`}>{item.value}</span>
    </div>
  );
}

function BriefingSectionCard({ section, isExpanded, onToggle }: { section: BriefingSection; isExpanded: boolean; onToggle: () => void }) {
  const colors = STATUS_COLORS[section.status];
  return (
    <div className={`rounded-xl border ${colors.border} ${colors.bg} p-3`}>
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between text-left"
        aria-expanded={isExpanded}
      >
        <span className="text-sm font-bold text-white">
          {colors.icon} {section.title}
        </span>
        <span className="text-xs text-slate-400">{isExpanded ? '▼' : '▶'}</span>
      </button>
      {isExpanded && (
        <div className="mt-2 space-y-1">
          {section.items.map((item, idx) => (
            <BriefingItemRow key={idx} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

export function OpenHandsOperatorBriefingPanel() {
  const briefing = useMemo(() => buildOpenHandsOperatorBriefing(), []);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['triggers', 'workflows']));

  const toggleSection = (id: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <div className="rounded-2xl border border-slate-600 bg-slate-800/95 p-4 shadow-xl">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold text-white">🤖 OpenHands Operator-Briefing</h2>
        {briefing.isBlocked && (
          <span className="rounded-full bg-rose-500/30 px-3 py-1 text-xs font-bold text-rose-300">
            🔴 Blockiert
          </span>
        )}
        {!briefing.isBlocked && briefing.warningCount > 0 && (
          <span className="rounded-full bg-amber-500/30 px-3 py-1 text-xs font-bold text-amber-300">
            🟡 {briefing.warningCount} Warnung{briefing.warningCount > 1 ? 'en' : ''}
          </span>
        )}
        {!briefing.isBlocked && briefing.warningCount === 0 && (
          <span className="rounded-full bg-emerald-500/30 px-3 py-1 text-xs font-bold text-emerald-300">
            🟢 Bereit
          </span>
        )}
      </div>

      {/* Blocked Warning */}
      {briefing.isBlocked && (
        <div className="mb-4 rounded-lg border border-rose-500/50 bg-rose-500/10 p-3">
          <p className="text-sm font-bold text-rose-300">
            ⚠️ OpenHands kann nicht starten, solange blockierende Probleme vorhanden sind.
          </p>
        </div>
      )}

      {/* Warning Notice */}
      {!briefing.isBlocked && briefing.warningCount > 0 && (
        <div className="mb-4 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3">
          <p className="text-sm font-bold text-amber-300">
            ⚡ OpenHands kann starten, aber einige Einstellungen fehlen.
          </p>
        </div>
      )}

      {/* Sections */}
      <div className="space-y-2">
        {briefing.sections.map((section) => (
          <BriefingSectionCard
            key={section.id}
            section={section}
            isExpanded={expandedSections.has(section.id)}
            onToggle={() => toggleSection(section.id)}
          />
        ))}
      </div>

      {/* Footer */}
      <div className="mt-4 border-t border-slate-600 pt-3">
        <p className="text-xs text-slate-400">
          Weitere Informationen finden Sie in der{' '}
          <a href="/docs/OPENHANDS_OPERATOR_BRIEFING.md" className="text-cyan-400 underline hover:text-cyan-300">
            Dokumentation
          </a>
          .
        </p>
      </div>
    </div>
  );
}
