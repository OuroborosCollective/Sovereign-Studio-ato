/**
 * Integration Intent Draft Card
 *
 * Compact assistant card showing recognized integration intent with action buttons.
 * Part of Issue #520: UI confirmation for detected integration tasks.
 *
 * Product rules:
 * - Shows only runtime-derived state
 * - No fake progress, no hardcoded success
 * - Exactly three action buttons: Einbauen, Neu formulieren, Ablehnen
 * - Gate status reflects real runtime state
 */

import React from 'react';
import type { IntegrationIntentDraft, IntegrationIntentDraftGateSnapshot } from '../runtime/integrationIntentDraftRuntime';

export interface IntegrationIntentDraftCardProps {
  /** The recognized integration draft */
  draft: IntegrationIntentDraft;
  /** Current gate snapshot from runtime */
  gateSnapshot: IntegrationIntentDraftGateSnapshot;
  /** Called when user confirms the draft */
  onConfirm: () => void;
  /** Called when user wants to rephrase the draft */
  onRephrase: () => void;
  /** Called when user rejects the draft */
  onReject: () => void;
  /** Optional: can confirm check result for button state */
  canConfirm?: boolean;
  /** Optional: blocker message if cannot confirm */
  confirmBlocker?: string;
}

/**
 * Single gate indicator component
 */
function GateIndicator({
  label,
  ready,
}: {
  label: string;
  ready: boolean;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        className={`w-2 h-2 rounded-full ${
          ready ? 'bg-emerald-400' : 'bg-slate-600'
        }`}
      />
      <span
        className={`text-[10px] ${
          ready ? 'text-emerald-400' : 'text-slate-500'
        }`}
      >
        {label}
      </span>
    </div>
  );
}

/**
 * Integration Intent Draft Card Component
 *
 * Displays:
 * - Header: "Ich habe daraus diesen Integrationsauftrag erkannt:"
 * - Title (extracted/improved)
 * - Goal
 * - Scope keywords
 * - Affected files (if derivable)
 * - Gate status indicators
 * - Three action buttons
 */
export const IntegrationIntentDraftCard: React.FC<IntegrationIntentDraftCardProps> = ({
  draft,
  gateSnapshot,
  onConfirm,
  onRephrase,
  onReject,
  canConfirm = true,
  confirmBlocker,
}) => {
  return (
    <div
      className="mx-3 my-2 rounded-xl border border-cyan-500/30 bg-slate-900/80 backdrop-blur-sm overflow-hidden"
      data-testid="integration-intent-draft-card"
      data-draft-id={draft.id}
      data-draft-title={draft.title}
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-cyan-500/20 bg-gradient-to-r from-cyan-500/10 to-transparent">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-lg bg-cyan-500/20 flex items-center justify-center">
            <span className="text-cyan-400 text-xs">⬡</span>
          </div>
          <p className="text-xs text-cyan-300 font-medium">
            Ich habe daraus diesen Integrationsauftrag erkannt:
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="px-4 py-3 space-y-3">
        {/* Title */}
        <div>
          <h4
            className="text-sm font-semibold text-slate-100 leading-snug"
            data-testid="draft-title"
          >
            {draft.title}
          </h4>
        </div>

        {/* Goal */}
        <div>
          <span className="text-[10px] text-cyan-500 uppercase tracking-wider font-bold">
            Ziel
          </span>
          <p className="text-xs text-slate-300 mt-0.5" data-testid="draft-goal">
            {draft.goal}
          </p>
        </div>

        {/* Scope */}
        {draft.scope.length > 0 && (
          <div>
            <span className="text-[10px] text-cyan-500 uppercase tracking-wider font-bold">
              Scope
            </span>
            <div className="flex flex-wrap gap-1.5 mt-1" data-testid="draft-scope">
              {draft.scope.map((s) => (
                <span
                  key={s}
                  className="px-2 py-0.5 rounded-full text-[10px] bg-slate-800 border border-slate-700 text-slate-400"
                >
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Affected Files */}
        {draft.affectedFiles.length > 0 && (
          <div>
            <span className="text-[10px] text-cyan-500 uppercase tracking-wider font-bold">
              Mögliche Dateien
            </span>
            <div className="mt-1 space-y-0.5" data-testid="draft-affected-files">
              {draft.affectedFiles.slice(0, 3).map((f) => (
                <div
                  key={f}
                  className="text-[10px] text-slate-500 font-mono truncate"
                  title={f}
                >
                  {f}
                </div>
              ))}
              {draft.affectedFiles.length > 3 && (
                <div className="text-[10px] text-slate-600">
                  +{draft.affectedFiles.length - 3} weitere
                </div>
              )}
            </div>
          </div>
        )}

        {/* Gates */}
        <div className="pt-2 border-t border-slate-800">
          <span className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">
            Gates
          </span>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-1.5" data-testid="draft-gates">
            <GateIndicator label="Repo ready" ready={gateSnapshot.repoReady} />
            <GateIndicator label="GitHub Write" ready={gateSnapshot.githubWriteReady} />
            <GateIndicator label="Direct Patch" ready={gateSnapshot.directPatchReady} />
            <GateIndicator label="OpenHands" ready={gateSnapshot.openhandsReady} />
          </div>
          {confirmBlocker && (
            <p className="text-[10px] text-amber-400 mt-1.5" data-testid="confirm-blocker">
              ⚠ {confirmBlocker}
            </p>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="px-4 py-3 border-t border-cyan-500/20 bg-slate-900/50">
        <div className="flex gap-2">
          {/* Einbauen */}
          <button
            type="button"
            onClick={onConfirm}
            disabled={!canConfirm}
            className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
              canConfirm
                ? 'bg-cyan-500/20 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/30 active:scale-[0.98]'
                : 'bg-slate-800 border border-slate-700 text-slate-500 cursor-not-allowed'
            }`}
            data-testid="btn-confirm"
            aria-label="Integrationsauftrag einbauen"
          >
            Einbauen
          </button>

          {/* Neu formulieren */}
          <button
            type="button"
            onClick={onRephrase}
            className="flex-1 px-3 py-2 rounded-lg text-xs font-medium bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 active:scale-[0.98] transition-all"
            data-testid="btn-rephrase"
            aria-label="Integrationsauftrag neu formulieren"
          >
            Neu formulieren
          </button>

          {/* Ablehnen */}
          <button
            type="button"
            onClick={onReject}
            className="flex-1 px-3 py-2 rounded-lg text-xs font-medium bg-slate-800/50 border border-slate-700/50 text-slate-500 hover:bg-slate-700/50 hover:text-slate-400 active:scale-[0.98] transition-all"
            data-testid="btn-reject"
            aria-label="Integrationsauftrag ablehnen"
          >
            Ablehnen
          </button>
        </div>
      </div>
    </div>
  );
};
