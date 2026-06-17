import {
  buildExternalMemoryConsentText,
  validateExternalMemorySyncConfig,
  type ExternalMemoryHealthResult,
  type ExternalMemoryPullUpdatesResult,
  type ExternalMemorySearchResult,
  type ExternalMemorySyncConfig,
  type ExternalMemorySyncResult,
} from '../runtime/externalMemorySync';
import type { ExternalMemoryMonitoringResult } from '../runtime/externalMemoryMonitoring';
import type { RemoteMemoryUpdateIntakeResult } from '../runtime/remoteMemoryUpdateIntake';

export interface RemoteMemoryPanelProps {
  config: ExternalMemorySyncConfig;
  syncResult: ExternalMemorySyncResult | null;
  healthResult: ExternalMemoryHealthResult | null;
  monitoringResult: ExternalMemoryMonitoringResult | null;
  searchResult: ExternalMemorySearchResult | null;
  updatesResult: ExternalMemoryPullUpdatesResult | null;
  intakeResult: RemoteMemoryUpdateIntakeResult | null;
  isBusy: boolean;
  onChange: (config: ExternalMemorySyncConfig) => void;
  onHealth: () => void;
  onMonitoring: () => void;
  onSync: () => void;
  onSearch: () => void;
  onPullUpdates: () => void;
}

export function RemoteMemoryPanel({
  config,
  syncResult,
  healthResult,
  monitoringResult,
  searchResult,
  updatesResult,
  intakeResult,
  isBusy,
  onChange,
  onHealth,
  onMonitoring,
  onSync,
  onSearch,
  onPullUpdates,
}: RemoteMemoryPanelProps) {
  const validation = validateExternalMemorySyncConfig(config);
  const update = (patch: Partial<ExternalMemorySyncConfig>) => onChange({ ...config, ...patch });

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold">Remote Memory</h2>
          <p className="mt-1 text-xs text-slate-400">Optionaler Abgleich validierter Pattern-Zusammenfassungen. Standard: aus.</p>
        </div>
        <label className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-300">
          <input type="checkbox" checked={config.enabled} onChange={(event) => update({ enabled: event.target.checked })} />
          An
        </label>
      </div>

      <pre className="mt-4 whitespace-pre-wrap rounded border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-400">{buildExternalMemoryConsentText()}</pre>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <label className="grid gap-1">
          <span className="text-xs font-bold uppercase text-slate-400">URL</span>
          <input className="rounded border border-slate-700 bg-slate-900 p-2" value={config.gatewayUrl} onChange={(event) => update({ gatewayUrl: event.target.value })} placeholder="http://46.202.154.25:8088" />
        </label>
        <label className="grid gap-1">
          <span className="text-xs font-bold uppercase text-slate-400">Workspace</span>
          <input className="rounded border border-slate-700 bg-slate-900 p-2" value={config.workspaceId} onChange={(event) => update({ workspaceId: event.target.value })} />
        </label>
        <label className="grid gap-1">
          <span className="text-xs font-bold uppercase text-slate-400">Collection</span>
          <input className="rounded border border-slate-700 bg-slate-900 p-2" value={config.collectionName} onChange={(event) => update({ collectionName: event.target.value })} />
        </label>
        <label className="grid gap-1">
          <span className="text-xs font-bold uppercase text-slate-400">Contributor</span>
          <input className="rounded border border-slate-700 bg-slate-900 p-2" value={config.contributorId} onChange={(event) => update({ contributorId: event.target.value })} />
        </label>
        <label className="grid gap-1">
          <span className="text-xs font-bold uppercase text-slate-400">Mode</span>
          <select className="rounded border border-slate-700 bg-slate-900 p-2" value={config.mode} onChange={(event) => update({ mode: event.target.value as ExternalMemorySyncConfig['mode'] })}>
            <option value="manual">Manual</option>
            <option value="pull-only">Pull only</option>
            <option value="push-pull">Push + Pull</option>
          </select>
        </label>
      </div>

      <div className="mt-4 grid gap-2 text-xs text-slate-300 md:grid-cols-2">
        <label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(config.allowSelfHostedHttp)} onChange={(event) => update({ allowSelfHostedHttp: event.target.checked })} />Self-hosted HTTP test erlauben</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={config.consentAccepted} onChange={(event) => update({ consentAccepted: event.target.checked })} />Consent akzeptiert</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={config.includeScanFindings} onChange={(event) => update({ includeScanFindings: event.target.checked })} />Scan Findings</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={config.includeLearningPatterns} onChange={(event) => update({ includeLearningPatterns: event.target.checked })} />Learning Patterns</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={config.includeSolutionPatterns} onChange={(event) => update({ includeSolutionPatterns: event.target.checked })} />Solution Patterns</label>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" onClick={onHealth} disabled={!config.enabled || !validation.valid || isBusy}>Health</button>
        <button type="button" onClick={onMonitoring} disabled={!config.enabled || !validation.valid || isBusy}>Monitoring</button>
        <button type="button" onClick={onSync} disabled={!config.enabled || !validation.valid || isBusy}>Sync</button>
        <button type="button" onClick={onSearch} disabled={!config.enabled || !validation.valid || isBusy}>Search</button>
        <button type="button" onClick={onPullUpdates} disabled={!config.enabled || !validation.valid || isBusy}>Pull Updates + Intake</button>
      </div>

      <p className={validation.valid ? 'mt-3 text-xs text-emerald-300' : 'mt-3 text-xs text-red-300'}>{validation.summary}</p>
      {validation.errors.length ? <ul className="mt-2 list-disc pl-5 text-xs text-red-300">{validation.errors.map((error) => <li key={error}>{error}</li>)}</ul> : null}
      {validation.warnings.length ? <ul className="mt-2 list-disc pl-5 text-xs text-amber-300">{validation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}

      <div className="mt-4 grid gap-3 text-xs text-slate-300">
        {healthResult ? <pre className="whitespace-pre-wrap rounded bg-slate-900/70 p-3">Health: {healthResult.summary}</pre> : null}
        {monitoringResult ? <pre className="whitespace-pre-wrap rounded bg-slate-900/70 p-3">Monitoring: {monitoringResult.summary}</pre> : null}
        {syncResult ? <pre className="whitespace-pre-wrap rounded bg-slate-900/70 p-3">Sync: {syncResult.summary}</pre> : null}
        {searchResult ? <pre className="whitespace-pre-wrap rounded bg-slate-900/70 p-3">Search: {searchResult.summary}</pre> : null}
        {updatesResult ? <pre className="whitespace-pre-wrap rounded bg-slate-900/70 p-3">Updates: {updatesResult.summary}</pre> : null}
        {intakeResult ? <pre className="whitespace-pre-wrap rounded bg-slate-900/70 p-3">Intake: {intakeResult.summary}</pre> : null}
      </div>
    </section>
  );
}
