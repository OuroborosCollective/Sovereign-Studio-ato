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
  draft: IntegrationIntentDraft;
  gateSnapshot: IntegrationIntentDraftGateSnapshot;
  onConfirm: () => void;
  onConfirmWithGitHubAccess?: () => void;
  onRephrase: () => void;
  onReject: () => void;
  canConfirm?: boolean;
  confirmBlocker?: string;
}

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

export const IntegrationIntentDraftCard: React.FC<IntegrationIntentDraftCardProps> = ({
  draft,
  gateSnapshot,
  onConfirm,
  onConfirmWithGitHubAccess,
  onRephrase,
  onReject,
  canConfirm = true,
  confirmBlocker,
}) => {
  const needsGitHubAccess = gateSnapshot.repoReady && !gateSnapshot.githubWriteReady;
  const einbauenEnabled = gateSnapshot.repoReady && (canConfirm || needsGitHubAccess);
  const effectiveConfirmBlocker = confirmBlocker
    ?? (
      gateSnapshot.repoReady && !needsGitHubAccess && !canConfirm
        ? 'Einbauen wartet: Der Sovereign Agent ist noch nicht startbereit oder ein bestätigter Executor-Lauf ist bereits aktiv.'
        : undefined
    );

  const handleEinbauen = () => {
    if (needsGitHubAccess && onConfirmWithGitHubAccess) {
      onConfirmWithGitHubAccess();
    } else if (canConfirm) {
      onConfirm();
    }
  };

  return (
    <div
      className="mx-3 my-2 rounded-xl border border-cyan-500/30 bg-slate-900/80 backdrop-blur-sm overflow-hidden"
      data-testid="integration-intent-draft-card"
      data-draft-id={draft.id}
      data-draft-title={draft.title}
    >
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

      <div className="px-4 py-3 space-y-3">
        <div>
          <h4
            className="text-sm font-semibold text-slate-100 leading-snug"
            data-testid="draft-title"
          >
            {draft.title}
          </h4>
        </div>

        <div>
          <span className="text-[10px] text-cyan-500 uppercase tracking-wider font-bold">
            Ziel
          </span>
          <p className="text-xs text-slate-300 mt-0.5" data-testid="draft-goal">
            {draft.goal}
          </p>
        </div>

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

        <div className="pt-2 border-t border-slate-800">
          <span className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">
            Gates
          </span>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-1.5" data-testid="draft-gates">
            <GateIndicator label="Repo ready" ready={gateSnapshot.repoReady} />
            <GateIndicator label="GitHub Write" ready={gateSnapshot.githubWriteReady} />
            <GateIndicator label="Direct Patch" ready={gateSnapshot.directPatchReady} />
            <GateIndicator label="Sovereign Agent" ready={gateSnapshot.agentReady} />
          </div>
          {effectiveConfirmBlocker && (
            <p className="text-[10px] text-amber-400 mt-1.5" data-testid="confirm-blocker">
              ⚠ {effectiveConfirmBlocker}
            </p>
          )}
        </div>
      </div>

      <div className="px-4 py-3 border-t border-cyan-500/20 bg-slate-900/50">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleEinbauen}
            disabled={!einbauenEnabled}
            className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
              einbauenEnabled
                ? needsGitHubAccess
                  ? 'bg-amber-500/20 border border-amber-500/40 text-amber-300 hover:bg-amber-500/30 active:scale-[0.98]'
                  : 'bg-cyan-500/20 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/30 active:scale-[0.98]'
                : 'bg-slate-800 border border-slate-700 text-slate-500 cursor-not-allowed'
            }`}
            data-testid="btn-confirm"
            aria-label="Integrationsauftrag einbauen"
          >
            {needsGitHubAccess ? 'GitHub-Zugang benötigt' : 'Einbauen'}
          </button>

          <button
            type="button"
            onClick={onRephrase}
            className="flex-1 px-3 py-2 rounded-lg text-xs font-medium bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 active:scale-[0.98] transition-all"
            data-testid="btn-rephrase"
            aria-label="Integrationsauftrag neu formulieren"
          >
            Neu formulieren
          </button>

          <button
            type="button"
            onClick={onReject}
            className="flex-1 px-3 py-2 rounded-lg text-xs font-medium bg-rose-500/10 border border-rose-500/35 text-rose-300 hover:bg-rose-500/20 active:scale-[0.98] transition-all"
            data-testid="btn-reject"
            data-enabled="true"
            aria-label="Integrationsauftrag ablehnen"
          >
            Ablehnen
          </button>
        </div>
      </div>
    </div>
  );
};
