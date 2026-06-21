import React, { useEffect, useState } from 'react';
import { RepoFileList } from '../../github/components/RepoFileList';
import type { RepoFile } from '../../github/types';
import { buildRepoSnapshotSummary, getRepoSnapshotStatus } from '../runtime/sovereignFunctionalGuards';

export interface RepoSnapshotContainerProps {
  repoUrl: string;
  repoBranch: string;
  accessValue: string;
  repoStatus: string;
  isRepoBusy: boolean;
  runtimeBusy: boolean;
  repoFiles: RepoFile[];
  memoryHints: string;
  onRepoUrlChange: (value: string) => void;
  onRepoBranchChange: (value: string) => void;
  onAccessValueChange: (value: string) => void;
  onLoadRepo: () => void;
  onSaveView: () => void;
  onRestoreView: () => void;
  onClearView: () => void;
}

function redactAccessValue(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return '<no-token>';
  if (trimmed.length <= 8) return '<set>';
  return `${trimmed.slice(0, 4)}…${trimmed.slice(-4)}`;
}

function setupPhase(input: { ready: boolean; busy: boolean; repoUrl: string; repoStatus: string }): 'no-repo' | 'repo-loading' | 'repo-loaded' | 'repo-error' {
  if (input.busy) return 'repo-loading';
  if (input.ready) return 'repo-loaded';
  if (!input.repoUrl.trim() || input.repoStatus.includes('Noch kein') || input.repoStatus.includes('fehlt')) return 'no-repo';
  return 'repo-error';
}

function publishRepoSetupState(input: {
  repoUrl: string;
  accessValue: string;
  repoStatus: string;
  busy: boolean;
  ready: boolean;
}): void {
  if (typeof window === 'undefined') return;

  const detail = {
    hasToken: input.accessValue.trim().length > 0,
    tokenStatus: input.accessValue.trim().length > 0 ? 'valid' as const : 'none' as const,
    repoReady: input.ready,
    setupPhase: setupPhase({ ready: input.ready, busy: input.busy, repoUrl: input.repoUrl, repoStatus: input.repoStatus }),
    isBusy: input.busy,
    status: input.repoStatus,
    redactedToken: redactAccessValue(input.accessValue),
    dependencyHealthy: true,
    updatedAt: Date.now(),
  };

  window.__sovereignSetupState = detail;
  window.dispatchEvent(new CustomEvent('sovereign:setup-state', { detail }));
}

const inputClassName = 'mt-2 block w-full min-w-0 rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-3 text-base leading-6 text-slate-50 placeholder:text-slate-500 focus:border-cyan-300 focus:outline-none focus:ring-2 focus:ring-cyan-400/20';
const actionButtonClassName = 'rounded-xl border border-cyan-400/25 bg-cyan-950/50 px-3 py-3 text-sm font-black text-cyan-50 disabled:cursor-not-allowed disabled:opacity-45';

export function RepoSnapshotContainer({
  repoUrl,
  repoBranch,
  accessValue,
  repoStatus,
  isRepoBusy,
  runtimeBusy,
  repoFiles,
  memoryHints,
  onRepoUrlChange,
  onRepoBranchChange,
  onAccessValueChange,
  onLoadRepo,
  onSaveView,
  onRestoreView,
  onClearView,
}: RepoSnapshotContainerProps) {
  const [showAccessHelp, setShowAccessHelp] = useState(false);
  const status = getRepoSnapshotStatus(repoFiles);
  const busy = isRepoBusy || runtimeBusy;
  const canLoad = !busy && repoUrl.trim().length > 0;
  const canSave = !busy && status.ready;
  const summary = repoFiles.length ? buildRepoSnapshotSummary(repoFiles) : repoStatus;

  useEffect(() => {
    publishRepoSetupState({
      repoUrl,
      accessValue,
      repoStatus,
      busy,
      ready: status.ready,
    });
  }, [accessValue, busy, repoStatus, repoUrl, status.ready]);

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200" data-testid="repo-snapshot-container">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-bold">Repository Snapshot</h2>
          <p className="mt-1 text-xs text-slate-400">Schritt 1: Repository laden. Danach Auftrag planen und Package bauen.</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className={status.ready ? 'rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-emerald-200' : 'rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-amber-200'}>{status.ready ? 'Repo geladen' : 'Repo fehlt'}</span>
          <span className={accessValue.trim() ? 'rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-emerald-200' : 'rounded-full border border-slate-600 bg-slate-900/80 px-3 py-1 text-slate-300'}>{accessValue.trim() ? 'Privater Zugang gesetzt' : 'Privater Zugang optional'}</span>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <label className="block min-w-0 rounded-2xl border border-cyan-400/35 bg-cyan-500/10 p-3 md:col-span-2">
          <span className="block text-xs font-black uppercase tracking-wide text-cyan-100">GitHub Repository URL</span>
          <input
            id="github-repo-url-input"
            name="github-repo-url"
            data-testid="github-repo-url-input"
            data-mobile-role="github-repo-url-input"
            className={inputClassName}
            value={repoUrl}
            onChange={(event) => onRepoUrlChange(event.target.value)}
            placeholder="https://github.com/owner/repository"
            aria-label="GitHub Repository URL"
            autoComplete="url"
            type="url"
          />
          <span className="mt-2 block text-[11px] leading-4 text-cyan-100/80">Pflichtfeld. Ohne geladenes Repo bleibt Produktion blockiert.</span>
        </label>

        <label className="block min-w-0 rounded-2xl border border-slate-700 bg-slate-900/60 p-3">
          <span className="block text-xs font-black uppercase tracking-wide text-slate-300">Branch</span>
          <input
            className={inputClassName}
            value={repoBranch}
            onChange={(event) => onRepoBranchChange(event.target.value)}
            placeholder="leer = Default Branch"
            aria-label="Repository branch"
          />
          <span className="mt-2 block text-[11px] text-slate-500">Leer lassen fuer Default.</span>
        </label>

        <label className="block min-w-0 rounded-2xl border border-amber-400/35 bg-amber-500/10 p-3 md:col-span-3">
          <span className="block text-xs font-black uppercase tracking-wide text-amber-100">GitHub Private Access</span>
          <input
            id="github-token-input"
            name="github-token"
            data-testid="github-token-input"
            data-mobile-role="github-token-input"
            className={inputClassName}
            value={accessValue}
            onFocus={() => setShowAccessHelp(true)}
            onChange={(event) => onAccessValueChange(event.target.value)}
            placeholder="Privater GitHub Zugang fuer private Repos"
            aria-label="GitHub private access"
            type="password"
            autoComplete="off"
          />
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] leading-4 text-amber-100/85">
            <span>Nur noetig fuer private Repos oder Draft PRs.</span>
            <button type="button" onClick={() => setShowAccessHelp((value) => !value)} className="rounded-full border border-amber-300/30 px-3 py-1 text-amber-100">Hilfe anzeigen</button>
          </div>
          {showAccessHelp ? (
            <div className="mt-3 rounded-xl border border-amber-300/25 bg-slate-950/70 p-3 text-xs leading-5 text-amber-50">
              Oeffne GitHub Settings, erstelle einen Repository-bezogenen privaten Zugangswert, waehle das Ziel-Repo und erlaube Inhalte sowie Pull Requests. Danach hier einfuegen und zuerst Load Repo ausfuehren.
            </div>
          ) : null}
        </label>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 md:flex md:flex-wrap">
        <button className={actionButtonClassName} onClick={onLoadRepo} disabled={!canLoad} type="button">1 · Load Repo</button>
        <button className={actionButtonClassName} onClick={onSaveView} disabled={!canSave} type="button">Save Session</button>
        <button className={actionButtonClassName} onClick={onRestoreView} disabled={busy} type="button">Restore Session</button>
        <button className={actionButtonClassName} onClick={onClearView} disabled={busy} type="button">Clear View</button>
      </div>

      <p className="mt-3 text-xs text-slate-400">{summary}</p>
      <p className="mt-1 text-xs text-slate-400">{status.reason}</p>
      {memoryHints ? <pre className="mt-2 whitespace-pre-wrap rounded bg-slate-900/70 p-3 text-xs text-emerald-200">{memoryHints}</pre> : null}
      <RepoFileList files={repoFiles} />
    </section>
  );
}
