import React, { useEffect, useMemo, useState } from 'react';
import { Activity, Brain, Gauge, Settings } from 'lucide-react';
import type { LauncherEntry, LauncherToolProps } from '../../launcherRegistry';
import {
  createCoverageCheckingEvidence,
  deriveCoverageInspectionEvidence,
  deriveHealthInspectionEvidence,
  deriveMemoryInspectionEvidence,
  deriveSettingsInspectionEvidence,
  useSovereignToolInspectionStore,
  type SovereignToolInspectionEvidence,
} from '../../../product/runtime/sovereignToolInspectionRuntime';

const C = {
  bg: '#0e1116',
  surface: '#161c24',
  border: '#232d3a',
  text: '#cdd9e5',
  textSub: '#768390',
  green: '#34d399',
  amber: '#fbbf24',
  rose: '#fb7185',
} as const;

function Shell({
  title,
  subtitle,
  children,
}: {
  readonly title: string;
  readonly subtitle: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: 14, background: C.bg }}>
      <div style={{ display: 'grid', gap: 4, marginBottom: 12 }}>
        <span style={{ color: C.text, fontFamily: 'monospace', fontSize: 13, fontWeight: 800 }}>
          {title}
        </span>
        <span style={{ color: C.textSub, fontSize: 11, lineHeight: 1.45 }}>
          {subtitle}
        </span>
      </div>
      <div style={{ display: 'grid', gap: 8 }}>{children}</div>
    </div>
  );
}

function Row({
  label,
  value,
  tone = 'neutral',
}: {
  readonly label: string;
  readonly value: string;
  readonly tone?: 'neutral' | 'ok' | 'warn' | 'bad';
}) {
  const color = tone === 'ok' ? C.green : tone === 'warn' ? C.amber : tone === 'bad' ? C.rose : C.textSub;
  return (
    <div
      style={{
        display: 'grid',
        gap: 4,
        padding: '9px 10px',
        borderRadius: 10,
        background: C.surface,
        border: `1px solid ${C.border}`,
      }}
    >
      <span style={{ color: C.textSub, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.7 }}>
        {label}
      </span>
      <span style={{ color, fontFamily: 'monospace', fontSize: 11, lineHeight: 1.45 }}>
        {value}
      </span>
    </div>
  );
}

function toneForEvidence(evidence: SovereignToolInspectionEvidence): 'ok' | 'warn' | 'bad' {
  if (evidence.outcome === 'ready') return 'ok';
  if (evidence.outcome === 'failed') return 'bad';
  return 'warn';
}

function canUseLocalStorage(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const key = '__sovereign_storage_check__';
    window.localStorage.setItem(key, '1');
    window.localStorage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

function countRelevantMemoryKeys(): number {
  if (typeof window === 'undefined') return 0;
  try {
    return Object.keys(window.localStorage)
      .filter((key) => /memory|pattern|sovereign/i.test(key))
      .length;
  } catch {
    return 0;
  }
}

export function SovereignSettingsTool(_props: LauncherToolProps) {
  const storageReady = canUseLocalStorage();
  const language = typeof navigator === 'undefined' ? 'unknown' : navigator.language || 'unknown';
  const online = typeof navigator === 'undefined' ? false : navigator.onLine;
  const recordEvidence = useSovereignToolInspectionStore((store) => store.recordEvidence);
  const evidence = useMemo(
    () => deriveSettingsInspectionEvidence({ storageReady, online, language }),
    [language, online, storageReady],
  );

  useEffect(() => {
    recordEvidence('settings', evidence);
  }, [evidence, recordEvidence]);

  return (
    <Shell
      title="Settings"
      subtitle="Sichtbare App-Regeln und sichere Session-Fähigkeiten. Keine Secrets werden angezeigt."
    >
      <Row label="Prüfergebnis" value={`${evidence.statusLabel} · ${evidence.reason}`} tone={toneForEvidence(evidence)} />
      <Row label="Surface" value="Chat-first · Inspector nur Nebenfläche" tone="ok" />
      <Row label="Merge Policy" value="Draft PR erlaubt · Auto-Merge nicht erlaubt" tone="ok" />
      <Row label="Storage" value={storageReady ? 'localStorage verfügbar' : 'localStorage blockiert'} tone={storageReady ? 'ok' : 'warn'} />
      <Row label="Client" value={`Sprache: ${language} · Netzwerk: ${online ? 'online' : 'offline'}`} tone={online ? 'ok' : 'warn'} />
      <Row label="Nächste Aktion" value={evidence.nextAction} />
    </Shell>
  );
}

export function SovereignMemoryTool(_props: LauncherToolProps) {
  const storageReady = canUseLocalStorage();
  const relevantKeyCount = useMemo(() => countRelevantMemoryKeys(), []);
  const recordEvidence = useSovereignToolInspectionStore((store) => store.recordEvidence);
  const evidence = useMemo(
    () => deriveMemoryInspectionEvidence({ storageReady, relevantKeyCount }),
    [relevantKeyCount, storageReady],
  );

  useEffect(() => {
    recordEvidence('memory', evidence);
  }, [evidence, recordEvidence]);

  return (
    <Shell
      title="Memory"
      subtitle="Zeigt nur echte lokale Speicher-Hinweise. Schlüsselnamen, Inhalte und Secrets werden nicht ausgegeben."
    >
      <Row label="Prüfergebnis" value={`${evidence.statusLabel} · ${evidence.reason}`} tone={toneForEvidence(evidence)} />
      <Row label="Lokale Memory Hinweise" value={`${relevantKeyCount} relevante Schlüssel gezählt`} tone={relevantKeyCount ? 'ok' : 'warn'} />
      <Row label="Sichtbarkeit" value="Schlüsselnamen und Inhalte bleiben verborgen." tone="ok" />
      <Row label="Regel" value="Memory ist Diagnose-/Kontextfläche. Die Produktwahrheit bleibt Runtime-State." tone="ok" />
      <Row label="Nächste Aktion" value={evidence.nextAction} />
    </Shell>
  );
}

export function SovereignHealthTool(_props: LauncherToolProps) {
  const storageReady = canUseLocalStorage();
  const online = typeof navigator === 'undefined' ? false : navigator.onLine;
  const serviceWorkerAvailable = typeof navigator !== 'undefined' && 'serviceWorker' in navigator;
  const recordEvidence = useSovereignToolInspectionStore((store) => store.recordEvidence);
  const evidence = useMemo(
    () => deriveHealthInspectionEvidence({ online, storageReady, serviceWorkerAvailable }),
    [online, serviceWorkerAvailable, storageReady],
  );

  useEffect(() => {
    recordEvidence('health', evidence);
  }, [evidence, recordEvidence]);

  return (
    <Shell
      title="Health"
      subtitle="Kleine echte Client-Checks statt grüner Behauptungen. Server-/CI-Status muss separat geprüft werden."
    >
      <Row label="Prüfergebnis" value={`${evidence.statusLabel} · ${evidence.reason}`} tone={toneForEvidence(evidence)} />
      <Row label="Netzwerk" value={online ? 'Browser meldet online' : 'Browser meldet offline'} tone={online ? 'ok' : 'warn'} />
      <Row label="Storage" value={storageReady ? 'Browser-Speicher schreibbar' : 'Browser-Speicher blockiert'} tone={storageReady ? 'ok' : 'bad'} />
      <Row label="Service Worker" value={serviceWorkerAvailable ? 'verfügbar' : 'nicht verfügbar'} tone={serviceWorkerAvailable ? 'ok' : 'warn'} />
      <Row label="Wahrheitsgrenze" value="Dieser Check ersetzt keine CI-, Worker- oder VPS-Prüfung." />
      <Row label="Nächste Aktion" value={evidence.nextAction} />
    </Shell>
  );
}

export function SovereignCoverageTool(_props: LauncherToolProps) {
  const [evidence, setEvidence] = useState<SovereignToolInspectionEvidence>(() => createCoverageCheckingEvidence());
  const recordEvidence = useSovereignToolInspectionStore((store) => store.recordEvidence);

  useEffect(() => {
    let alive = true;
    const checking = createCoverageCheckingEvidence();
    setEvidence(checking);
    recordEvidence('coverage', checking);

    async function loadCoverage() {
      try {
        const response = await fetch('/generated/test-coverage-map.json', { cache: 'no-store' });
        if (!alive) return;
        if (!response.ok) {
          const failed = deriveCoverageInspectionEvidence({
            ok: false,
            detail: `Coverage Map nicht erreichbar · HTTP ${response.status}`,
          });
          setEvidence(failed);
          recordEvidence('coverage', failed);
          return;
        }
        const payload: unknown = await response.json();
        if (!alive) return;
        const fileCount = typeof payload === 'object' && payload !== null && 'files' in payload && Array.isArray(payload.files)
          ? payload.files.length
          : typeof payload === 'object' && payload !== null
            ? Object.keys(payload).length
            : 0;
        const ready = deriveCoverageInspectionEvidence({ ok: true, fileCount });
        setEvidence(ready);
        recordEvidence('coverage', ready);
      } catch (error) {
        if (!alive) return;
        const failed = deriveCoverageInspectionEvidence({
          ok: false,
          detail: error instanceof Error ? error.message : 'Coverage Map konnte nicht gelesen werden.',
        });
        setEvidence(failed);
        recordEvidence('coverage', failed);
      }
    }

    void loadCoverage();
    return () => { alive = false; };
  }, [recordEvidence]);

  return (
    <Shell
      title="Coverage"
      subtitle="Prüft die echte generierte Coverage-Map aus dem Deployment-Pfad. Keine Prozent-Fakes."
    >
      <Row
        label="Coverage Map"
        value={`${evidence.statusLabel} · ${evidence.reason}`}
        tone={toneForEvidence(evidence)}
      />
      <Row label="Regel" value="Keine harten Prozentwerte anzeigen, solange sie nicht aus echter Coverage berechnet sind." tone="ok" />
      <Row label="Nächste Aktion" value={evidence.nextAction} />
    </Shell>
  );
}

export const settingsToolEntry: LauncherEntry = {
  id: 'settings',
  label: 'Settings',
  description: 'Chat-first Regeln und Session-Fähigkeiten',
  icon: Settings,
  color: 'bg-sky-600',
  component: SovereignSettingsTool,
  disabled: false,
};

export const memoryToolEntry: LauncherEntry = {
  id: 'memory',
  label: 'Memory',
  description: 'Lokale Memory-/Pattern-Hinweise',
  icon: Brain,
  color: 'bg-violet-600',
  component: SovereignMemoryTool,
  disabled: false,
};

export const healthToolEntry: LauncherEntry = {
  id: 'health',
  label: 'Health',
  description: 'Echte Client-Health-Checks',
  icon: Activity,
  color: 'bg-emerald-600',
  component: SovereignHealthTool,
  disabled: false,
};

export const coverageToolEntry: LauncherEntry = {
  id: 'coverage',
  label: 'Coverage',
  description: 'Coverage Map ohne Prozent-Fakes',
  icon: Gauge,
  color: 'bg-amber-600',
  component: SovereignCoverageTool,
  disabled: false,
};
