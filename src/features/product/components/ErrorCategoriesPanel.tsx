import React, { useMemo } from 'react';
import { AlertCircle, AlertTriangle, Bug, CheckCircle2, Code, Eye, FileWarning, Lock, Shield, Type, Wrench, XCircle, Zap } from 'lucide-react';
import type { ScanFinding, ScanFindingCategory, ScanFindingRegistry, ScanFindingSeverity } from '../runtime/scanFindingRegistry';
import { SCAN_FINDING_CATEGORIES, groupScanFindingsByCategory, summarizeScanFindingRegistry } from '../runtime/scanFindingRegistry';

interface ErrorCategoriesPanelProps {
  registry: ScanFindingRegistry;
  onFindingClick?: (finding: ScanFinding) => void;
  className?: string;
}

const CATEGORY_LABELS: Record<ScanFindingCategory, string> = {
  architecture: 'Architektur',
  'type-error': 'TypeScript',
  'build-logic': 'Build-Logik',
  warning: 'Warnungen',
  'security-leak': 'Security',
  'test-doubles': 'Test-Doubles',
  'build-artifact': 'Build-Artefakte',
  'runtime-guard': 'Runtime Guards',
  auth: 'Auth',
  workflow: 'Workflow',
  'ci-failure': 'CI Fehler',
  'learning-memory': 'Learning Memory',
  'diff-preview': 'Diff Preview',
  'generated-file': 'Generated Files',
  docs: 'Dokumentation',
};

const SEVERITY_LABELS: Record<ScanFindingSeverity, string> = {
  critical: 'kritisch',
  high: 'hoch',
  medium: 'mittel',
  low: 'niedrig',
};

function categoryIcon(category: ScanFindingCategory): React.ReactElement {
  if (category === 'security-leak' || category === 'runtime-guard') return <Shield size={16} className="text-red-300" />;
  if (category === 'auth') return <Lock size={16} className="text-orange-300" />;
  if (category === 'type-error') return <Type size={16} className="text-purple-300" />;
  if (category === 'ci-failure' || category === 'workflow') return <Zap size={16} className="text-yellow-300" />;
  if (category === 'build-logic') return <Wrench size={16} className="text-blue-300" />;
  if (category === 'test-doubles') return <Bug size={16} className="text-green-300" />;
  if (category === 'architecture') return <Eye size={16} className="text-cyan-300" />;
  if (category === 'docs') return <Code size={16} className="text-stone-300" />;
  return <FileWarning size={16} className="text-slate-300" />;
}

function severityClasses(severity: ScanFindingSeverity): string {
  if (severity === 'critical') return 'border-red-500/40 bg-red-500/10 text-red-100';
  if (severity === 'high') return 'border-orange-500/40 bg-orange-500/10 text-orange-100';
  if (severity === 'medium') return 'border-amber-500/40 bg-amber-500/10 text-amber-100';
  return 'border-slate-500/40 bg-slate-500/10 text-slate-200';
}

function categoryClasses(category: ScanFindingCategory): string {
  if (category === 'security-leak' || category === 'runtime-guard') return 'border-red-500/20 bg-red-500/5';
  if (category === 'auth') return 'border-orange-500/20 bg-orange-500/5';
  if (category === 'type-error') return 'border-purple-500/20 bg-purple-500/5';
  if (category === 'ci-failure' || category === 'workflow') return 'border-yellow-500/20 bg-yellow-500/5';
  if (category === 'build-logic') return 'border-blue-500/20 bg-blue-500/5';
  if (category === 'architecture') return 'border-cyan-500/20 bg-cyan-500/5';
  if (category === 'learning-memory') return 'border-emerald-500/20 bg-emerald-500/5';
  return 'border-slate-500/20 bg-slate-500/5';
}

export const ErrorCategoriesPanel: React.FC<ErrorCategoriesPanelProps> = ({ registry, onFindingClick, className = '' }) => {
  const grouped = useMemo(() => groupScanFindingsByCategory(registry.findings), [registry.findings]);
  const summary = useMemo(() => summarizeScanFindingRegistry(registry), [registry]);
  const activeFindings = useMemo(() => registry.findings.filter((finding) => finding.status === 'active'), [registry.findings]);
  const resolvedCount = registry.findings.length - activeFindings.length;

  const bySeverity = useMemo(() => ({
    critical: activeFindings.filter((finding) => finding.severity === 'critical').length,
    high: activeFindings.filter((finding) => finding.severity === 'high').length,
    medium: activeFindings.filter((finding) => finding.severity === 'medium').length,
    low: activeFindings.filter((finding) => finding.severity === 'low').length,
  }), [activeFindings]);

  return (
    <section className={`rounded-2xl border border-slate-700/60 bg-slate-900 ${className}`}>
      <header className="border-b border-slate-700/70 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <AlertCircle size={18} className="text-cyan-300" />
            <div>
              <h3 className="text-sm font-bold text-slate-100">Fehlerkategorien</h3>
              <p className="text-[11px] text-slate-500">{summary}</p>
            </div>
          </div>
          <span className="rounded-full border border-slate-600/60 px-2 py-1 text-[10px] text-slate-300">{activeFindings.length} aktiv · {resolvedCount} gelöst</span>
        </div>
      </header>

      <div className="grid gap-2 p-4 sm:grid-cols-4">
        {(Object.keys(bySeverity) as ScanFindingSeverity[]).map((severity) => (
          <div key={severity} className={`rounded-xl border p-3 ${severityClasses(severity)}`}>
            <div className="text-[10px] uppercase tracking-wider opacity-75">{SEVERITY_LABELS[severity]}</div>
            <div className="text-2xl font-bold">{bySeverity[severity]}</div>
          </div>
        ))}
      </div>

      <div className="space-y-3 p-4 pt-0">
        {activeFindings.length === 0 ? (
          <p className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-emerald-100">
            Keine aktiven Finding-Blocker im Registry-Snapshot.
          </p>
        ) : SCAN_FINDING_CATEGORIES.map((category) => {
          const findings = grouped[category].filter((finding) => finding.status === 'active');
          if (!findings.length) return null;
          return (
            <div key={category} className={`rounded-xl border p-3 ${categoryClasses(category)}`}>
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs font-bold text-slate-100">
                  {categoryIcon(category)}
                  {CATEGORY_LABELS[category]}
                </div>
                <span className="rounded-full border border-slate-600/60 px-2 py-0.5 text-[10px] text-slate-300">{findings.length}</span>
              </div>
              <div className="space-y-2">
                {findings.slice(0, 6).map((finding) => (
                  <button
                    key={finding.id}
                    type="button"
                    onClick={() => onFindingClick?.(finding)}
                    className="w-full rounded-lg border border-slate-700/50 bg-slate-950/40 p-2 text-left transition hover:border-cyan-400/40"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-slate-100">{finding.title}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] ${severityClasses(finding.severity)}`}>{SEVERITY_LABELS[finding.severity]}</span>
                    </div>
                    <p className="mt-1 text-[11px] text-slate-400">{finding.filePath}</p>
                    <p className="mt-1 line-clamp-2 text-[11px] text-slate-500">{finding.fixTips || finding.description}</p>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <footer className="flex items-center justify-center gap-2 border-t border-slate-700/70 bg-slate-950/40 px-4 py-2 text-[10px] text-slate-500">
        <CheckCircle2 size={12} />
        Registry-Snapshot aus echter Scan-Runtime
      </footer>
    </section>
  );
};

export default ErrorCategoriesPanel;
