import React from 'react';
import type { OpenHandsEnterpriseConfig } from '../runtime/openhandsEnterpriseRuntime';
import {
  buildOpenHandsOperatorBriefing,
  BRIEFING_STATUS_COLORS,
  BRIEFING_STATUS_LABELS,
  summarizeOpenHandsBriefing,
  type BriefingItem,
  type BriefingSection,
  type BriefingStatus,
  type OpenHandsOperatorBriefing,
} from '../runtime/openHandsOperatorBriefing';

export interface OpenHandsOperatorBriefingPanelProps {
  config: OpenHandsEnterpriseConfig;
  onClose?: () => void;
  initiallyExpanded?: boolean;
}

/** Status indicator dot */
function StatusDot({ status }: { status: BriefingStatus }) {
  return (
    <span
      className="inline-block h-2 w-2 rounded-full"
      style={{ backgroundColor: BRIEFING_STATUS_COLORS[status] }}
      aria-hidden="true"
    />
  );
}

/** Single briefing item row */
function BriefingItemRow({ item }: { item: BriefingItem }) {
  return (
    <div
      className="flex items-start gap-2 rounded px-2 py-1.5 transition-colors hover:bg-slate-800/50"
      data-briefing-item={item.id}
    >
      <div className="mt-1 flex-shrink-0">
        <StatusDot status={item.status} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-slate-400">{item.label}</span>
          <span
            className="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide"
            style={{
              color: BRIEFING_STATUS_COLORS[item.status],
              backgroundColor: `${BRIEFING_STATUS_COLORS[item.status]}20`,
            }}
          >
            {BRIEFING_STATUS_LABELS[item.status]}
          </span>
        </div>
        <div className="mt-0.5 text-sm text-slate-200">{item.value}</div>
        {item.hint && (
          <div className="mt-1 text-xs text-slate-500">{item.hint}</div>
        )}
      </div>
    </div>
  );
}

/** Section with collapsible content */
function BriefingSectionComponent({
  section,
  defaultExpanded = true,
}: {
  section: BriefingSection;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = React.useState(defaultExpanded);

  const blockedItems = section.items.filter(i => i.status === 'blocked').length;
  const warningItems = section.items.filter(i => i.status === 'warning').length;
  const statusIcon = blockedItems > 0 ? '🔴' : warningItems > 0 ? '🟡' : '🟢';

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left transition-colors hover:bg-slate-800/50"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2">
          <span aria-hidden="true">{statusIcon}</span>
          <h4 className="text-sm font-semibold text-slate-200">{section.title}</h4>
        </div>
        <span className="text-slate-500 transition-transform" aria-hidden="true">
          {expanded ? '▼' : '▶'}
        </span>
      </button>
      {expanded && (
        <div className="border-t border-slate-800 px-2 py-2">
          {section.items.map(item => (
            <BriefingItemRow key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Header showing summary status */
function BriefingHeader({ briefing }: { briefing: OpenHandsOperatorBriefing }) {
  const headerColor = briefing.isBlocked
    ? BRIEFING_STATUS_COLORS.blocked
    : briefing.warningCount > 0
      ? BRIEFING_STATUS_COLORS.warning
      : BRIEFING_STATUS_COLORS.ok;

  return (
    <div className="mb-3 flex items-center gap-2">
      <span
        className="flex h-8 w-8 items-center justify-center rounded-lg text-lg"
        style={{ backgroundColor: `${headerColor}30`, color: headerColor }}
        aria-hidden="true"
      >
        🤖
      </span>
      <div>
        <h3 className="text-sm font-semibold text-slate-100">OpenHands Operator-Briefing</h3>
        <p className="text-xs text-slate-400">{summarizeOpenHandsBriefing(briefing)}</p>
      </div>
    </div>
  );
}

/** Badge for counts */
function CountBadge({
  count,
  type,
}: {
  count: number;
  type: 'blocked' | 'warning';
}) {
  if (count === 0) return null;
  const color = type === 'blocked' ? BRIEFING_STATUS_COLORS.blocked : BRIEFING_STATUS_COLORS.warning;
  return (
    <span
      className="ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-xs font-bold"
      style={{ backgroundColor: `${color}30`, color }}
    >
      {count}
    </span>
  );
}

/** Main panel component */
export function OpenHandsOperatorBriefingPanel({
  config,
  onClose,
  initiallyExpanded = true,
}: OpenHandsOperatorBriefingPanelProps) {
  const briefing = React.useMemo(
    () => buildOpenHandsOperatorBriefing(config),
    [config]
  );

  const [allExpanded, setAllExpanded] = React.useState(initiallyExpanded);

  return (
    <div
      className="rounded-xl border border-cyan-500/30 bg-slate-950/80 p-4"
      data-testid="openhands-operator-briefing"
      role="region"
      aria-label="OpenHands Operator-Briefing"
    >
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <BriefingHeader briefing={briefing} />
        <div className="flex items-center gap-2">
          {briefing.blockedCount > 0 && (
            <CountBadge count={briefing.blockedCount} type="blocked" />
          )}
          {briefing.warningCount > 0 && (
            <CountBadge count={briefing.warningCount} type="warning" />
          )}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200"
              aria-label="Briefing schließen"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Expand/Collapse all */}
      <div className="mb-3 flex items-center justify-between border-b border-slate-800 pb-2">
        <span className="text-xs text-slate-500">
          {briefing.sections.length} Bereiche
        </span>
        <button
          type="button"
          onClick={() => setAllExpanded(!allExpanded)}
          className="text-xs text-cyan-400 transition-colors hover:text-cyan-300"
        >
          {allExpanded ? 'Alle einklappen' : 'Alle ausklappen'}
        </button>
      </div>

      {/* Sections */}
      <div className="space-y-3" role="list">
        {briefing.sections.map((section, index) => (
          <BriefingSectionComponent
            key={section.id}
            section={section}
            defaultExpanded={allExpanded || index < 2}
          />
        ))}
      </div>

      {/* Footer hint for blocked state */}
      {briefing.isBlocked && (
        <div
          className="mt-4 rounded-lg border border-red-500/30 bg-red-950/30 p-3"
          role="alert"
        >
          <p className="text-xs font-medium text-red-300">
            ⚠️ OpenHands kann nicht starten, solange blockierende Probleme vorhanden sind.
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Bitte prüfe die rot markierten Einträge und konfiguriere die fehlenden Einstellungen.
          </p>
        </div>
      )}

      {/* Footer hint for warnings only */}
      {!briefing.isBlocked && briefing.warningCount > 0 && (
        <div
          className="mt-4 rounded-lg border border-amber-500/30 bg-amber-950/30 p-3"
          role="status"
        >
          <p className="text-xs font-medium text-amber-300">
            ⚡ OpenHands kann starten, aber einige Einstellungen fehlen.
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Optionale Einstellungen sind gelb markiert.
          </p>
        </div>
      )}
    </div>
  );
}