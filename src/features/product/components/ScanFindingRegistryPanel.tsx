import React, { memo, useMemo } from 'react';
import {
  SCAN_FINDING_CATEGORIES,
  buildScanFindingPublishGate,
  groupScanFindingsByCategory,
  summarizeScanFindingRegistry,
  type ScanFinding,
  type ScanFindingRegistry,
  type ScanFindingSeverity,
} from '../runtime/scanFindingRegistry';

export interface ScanFindingRegistryPanelProps {
  registry: ScanFindingRegistry;
}

function severityClass(severity: ScanFindingSeverity): string {
  if (severity === 'critical') return 'text-red-400';
  if (severity === 'high') return 'text-red-300';
  if (severity === 'medium') return 'text-amber-300';
  return 'text-slate-300';
}

const FindingCard = memo(({ finding }: { finding: ScanFinding }) => {
  return (
    <details className="rounded border border-slate-800 bg-slate-900/70 p-3">
      <summary className="cursor-pointer">
        <span className={`mr-2 font-bold uppercase ${severityClass(finding.severity)}`}>{finding.severity}</span>
        <span className="mr-2 rounded bg-slate-950 px-2 py-0.5 text-[11px] uppercase text-slate-400">{finding.category}</span>
        <span className="font-bold text-slate-100">{finding.title}</span>
      </summary>
      <div className="mt-3 grid gap-2 text-xs text-slate-400">
        <p><span className="font-bold text-slate-300">Path:</span> <code>{finding.filePath}</code>{finding.lineNumber ? `:${finding.lineNumber}` : ''}</p>
        <p><span className="font-bold text-slate-300">Description:</span> {finding.description}</p>
        <p><span className="font-bold text-slate-300">Fix:</span> {finding.fixTips}</p>
        <p><span className="font-bold text-slate-300">Confidence:</span> {finding.confidence} • <span className="font-bold text-slate-300">Hits:</span> {finding.hits} • <span className="font-bold text-slate-300">Status:</span> {finding.status}</p>
      </div>
    </details>
  );
});

FindingCard.displayName = 'FindingCard';

export const ScanFindingRegistryPanel = memo(({ registry }: ScanFindingRegistryPanelProps) => {
  const activeFindings = useMemo(() =>
    registry.findings.filter((finding) => finding.status === 'active'),
    [registry.findings]
  );
  const resolvedFindings = useMemo(() =>
    registry.findings.filter((finding) => finding.status === 'resolved'),
    [registry.findings]
  );
  const grouped = useMemo(() =>
    groupScanFindingsByCategory(activeFindings),
    [activeFindings]
  );
  const latestRun = registry.runs[0];
  const gate = useMemo(() =>
    buildScanFindingPublishGate(registry),
    [registry]
  );
  const summary = useMemo(() =>
    summarizeScanFindingRegistry(registry),
    [registry]
  );

  return (
    <section className="mt-4 rounded border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-bold">Scan Findings Registry</h2>
          <p className="mt-1 text-xs text-slate-400">{summary}</p>
        </div>
        <span className={`rounded bg-slate-900 px-2 py-1 text-xs font-bold uppercase ${gate.allowed ? 'text-emerald-300' : 'text-red-300'}`}>
          {gate.allowed ? 'clear' : 'needs attention'}
        </span>
      </div>

      <p className="mt-2 text-xs text-slate-500">{gate.summary}</p>

      {latestRun ? (
        <div className="mt-4 rounded border border-slate-800 bg-slate-900/70 p-3">
          <p className="font-bold text-slate-100">Latest scan</p>
          <p className="mt-1 text-xs text-slate-400">{latestRun.summary}</p>
        </div>
      ) : (
        <p className="mt-4 rounded border border-slate-800 bg-slate-900/70 p-3 text-xs text-slate-500">No scan findings collected yet. Load a repository first.</p>
      )}

      <div className="mt-4 grid gap-3">
        {SCAN_FINDING_CATEGORIES.map((category) => {
          const items = grouped[category];
          if (!items.length) return null;
          return (
            <div key={category} className="rounded border border-slate-800 bg-slate-950/70 p-3">
              <h3 className="font-bold uppercase text-slate-300">{category} · {items.length}</h3>
              <div className="mt-3 grid gap-2">
                {items.map((finding) => <FindingCard key={finding.id} finding={finding} />)}
              </div>
            </div>
          );
        })}
      </div>

      {resolvedFindings.length ? (
        <details className="mt-4 rounded border border-slate-800 bg-slate-900/70 p-3">
          <summary className="cursor-pointer font-bold text-slate-300">Resolved history · {resolvedFindings.length}</summary>
          <div className="mt-3 grid gap-2">
            {resolvedFindings.map((finding) => <FindingCard key={finding.id} finding={finding} />)}
          </div>
        </details>
      ) : null}
    </section>
  );
});

ScanFindingRegistryPanel.displayName = 'ScanFindingRegistryPanel';
