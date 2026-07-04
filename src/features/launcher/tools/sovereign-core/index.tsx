import React, { useEffect, useMemo, useState } from 'react';
import { Activity, Brain, Gauge, Settings } from 'lucide-react';
import type { LauncherEntry, LauncherToolProps } from '../../launcherRegistry';

const C = {
  bg: '#0e1116',
  surface: '#161c24',
  border: '#232d3a',
  text: '#cdd9e5',
  textSub: '#768390',
  green: '#34d399',
  amber: '#fbbf24',
  rose: '#fb7185',
  sky: '#22d3ee',
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

function canUseLocalStorage(): boolean {
  try {
    const key = '__sovereign_storage_check__';
    window.localStorage.setItem(key, '1');
    window.localStorage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

export function SovereignSettingsTool(_props: LauncherToolProps) {
  const storageReady = canUseLocalStorage();
  const language = typeof navigator === 'undefined' ? 'unknown' : navigator.language || 'unknown';
  const online = typeof navigator === 'undefined' ? false : navigator.onLine;

  return (
    <Shell
      title="Settings"
      subtitle="Sichtbare App-Regeln und sichere Session-Fähigkeiten. Keine Secrets werden angezeigt."
    >
      <Row label="Surface" value="Chat-first · Inspector nur Nebenfläche" tone="ok" />
      <Row label="Merge Policy" value="Draft PR erlaubt · Auto-Merge nicht erlaubt" tone="ok" />
      <Row label="Storage" value={storageReady ? 'localStorage verfügbar' : 'localStorage blockiert'} tone={storageReady ? 'ok' : 'warn'} />
      <Row label="Client" value={`Sprache: ${language} · Netzwerk: ${online ? 'online' : 'offline'}`} tone={online ? 'ok' : 'warn'} />
      <Row label="Nächste Aktion" value="Für Account, Credits oder Zugang das Profil bzw. GitHub-Access-Tool öffnen." />
    </Shell>
  );
}

export function SovereignMemoryTool(_props: LauncherToolProps) {
  const memoryKeys = useMemo(() => {
    try {
      return Object.keys(window.localStorage).filter((key) => /memory|pattern|sovereign/i.test(key));
    } catch {
      return [];
    }
  }, []);

  return (
    <Shell
      title="Memory"
      subtitle="Zeigt nur echte lokale Speicher-Hinweise. Inhalte und Secrets werden nicht ausgegeben."
    >
      <Row label="Lokale Memory Keys" value={`${memoryKeys.length} relevante Schlüssel gefunden`} tone={memoryKeys.length ? 'ok' : 'warn'} />
      <Row
        label="Sichtbarkeit"
        value={memoryKeys.length ? memoryKeys.slice(0, 6).join(' · ') : 'Keine lokalen Memory-/Pattern-Schlüssel im Browser gefunden'}
      />
      <Row label="Regel" value="Memory ist Diagnose-/Kontextfläche. Die Produktwahrheit bleibt Runtime-State." tone="ok" />
      <Row label="Nächste Aktion" value="Für Pattern-Details den Inspector öffnen oder eine konkrete Memory-Frage in den Chat stellen." />
    </Shell>
  );
}

export function SovereignHealthTool(_props: LauncherToolProps) {
  const storageReady = canUseLocalStorage();
  const online = typeof navigator === 'undefined' ? false : navigator.onLine;
  const serviceWorkerState = typeof navigator !== 'undefined' && 'serviceWorker' in navigator ? 'verfügbar' : 'nicht verfügbar';

  return (
    <Shell
      title="Health"
      subtitle="Kleine echte Client-Checks statt grüner Behauptungen. Server-/CI-Status muss separat geprüft werden."
    >
      <Row label="Netzwerk" value={online ? 'Browser meldet online' : 'Browser meldet offline'} tone={online ? 'ok' : 'warn'} />
      <Row label="Storage" value={storageReady ? 'Browser-Speicher schreibbar' : 'Browser-Speicher blockiert'} tone={storageReady ? 'ok' : 'bad'} />
      <Row label="Service Worker" value={serviceWorkerState} tone={serviceWorkerState === 'verfügbar' ? 'ok' : 'warn'} />
      <Row label="Wahrheitsgrenze" value="Dieser Check ersetzt keine CI-, Worker- oder VPS-Prüfung." />
    </Shell>
  );
}

export function SovereignCoverageTool(_props: LauncherToolProps) {
  const [state, setState] = useState<'loading' | 'ready' | 'missing'>('loading');
  const [detail, setDetail] = useState('Coverage Map wird geprüft…');

  useEffect(() => {
    let alive = true;
    async function loadCoverage() {
      try {
        const response = await fetch('/generated/test-coverage-map.json', { cache: 'no-store' });
        if (!alive) return;
        if (!response.ok) {
          setState('missing');
          setDetail(`Coverage Map nicht erreichbar · HTTP ${response.status}`);
          return;
        }
        const payload = await response.json();
        const fileCount = Array.isArray(payload?.files)
          ? payload.files.length
          : Object.keys(payload ?? {}).length;
        setState('ready');
        setDetail(`Coverage Map geladen · ${fileCount} Einträge erkannt`);
      } catch (error) {
        if (!alive) return;
        setState('missing');
        setDetail(error instanceof Error ? error.message : 'Coverage Map konnte nicht gelesen werden.');
      }
    }
    void loadCoverage();
    return () => { alive = false; };
  }, []);

  return (
    <Shell
      title="Coverage"
      subtitle="Prüft die echte generierte Coverage-Map aus dem Deployment-Pfad. Keine Prozent-Fakes."
    >
      <Row
        label="Coverage Map"
        value={detail}
        tone={state === 'ready' ? 'ok' : state === 'loading' ? 'warn' : 'bad'}
      />
      <Row label="Regel" value="Keine harten Prozentwerte anzeigen, solange sie nicht aus echter Coverage berechnet sind." tone="ok" />
      <Row label="Nächste Aktion" value="Wenn die Map fehlt: Release-/Coverage-Job prüfen und nicht grün behaupten." />
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
