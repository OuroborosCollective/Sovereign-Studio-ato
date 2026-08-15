import React from 'react';
import { C } from './builderConstants';

export interface CompactRepoSetupSheetProps {
  readonly value: string;
  readonly busy: boolean;
  readonly error: string | null;
  readonly onChange: (value: string) => void;
  readonly onLoad: () => void;
  readonly onClose: () => void;
}

export function CompactRepoSetupSheet({ value, busy, error, onChange, onLoad, onClose }: CompactRepoSetupSheetProps) {
  const canLoad = !busy && value.trim().length > 0;

  const submitTitle = busy
    ? 'Repository-Snapshot wird geladen…'
    : !canLoad
    ? 'Bitte geben Sie eine gültige GitHub-Repository-URL ein'
    : 'Repository-Snapshot von der angegebenen URL laden';

  return (
    <div role="presentation" onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 84, background: 'rgba(14,17,22,0.84)', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Repo Setup"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key !== 'Escape') return;
          event.stopPropagation();
          onClose();
        }}
        style={{ width: '100%', maxWidth: 520, margin: '0 auto', borderRadius: '20px 20px 0 0', border: `1px solid ${C.border}`, background: C.surface, padding: '16px 16px calc(22px + env(safe-area-inset-bottom, 0px))' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'start' }}>
          <div>
            <strong style={{ color: C.text }}>Repository laden</strong>
            <p style={{ color: C.textMuted, fontSize: 11, margin: '5px 0 0' }}>
              Erst ein bestätigter Runtime-Snapshot schaltet Repo-, Files- und Executor-Pfade frei.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Repo Setup schließen"
            title="Repo Setup schließen"
            className="p-1 px-2.5 text-stone-400 hover:text-stone-100 hover:bg-slate-800/50 focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none rounded transition-all cursor-pointer text-lg font-bold"
          >
            ×
          </button>
        </div>
        <label
          htmlFor="repo-setup-url-input"
          style={{ display: 'grid', gap: 6, marginTop: 14, color: C.textSub, fontSize: 11 }}
        >
          GitHub Repository URL
          <input
            id="repo-setup-url-input"
            aria-label="GitHub Repository URL"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && canLoad) {
                onLoad();
              }
            }}
            placeholder="https://github.com/owner/repository"
            autoComplete="url"
            inputMode="url"
            className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none transition-all"
            style={{ width: '100%', padding: '12px', borderRadius: 10, border: `1px solid ${C.border}`, background: C.bg, color: C.text, fontSize: 16 }}
          />
        </label>
        {error ? <p role="alert" style={{ color: C.rose, fontSize: 11 }}>{error}</p> : null}
        <button
          type="button"
          onClick={onLoad}
          disabled={!canLoad}
          title={submitTitle}
          className="focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:outline-none transition-all cursor-pointer"
          style={{
            marginTop: 12,
            width: '100%',
            padding: '12px',
            borderRadius: 10,
            border: `1px solid ${C.sky}`,
            background: `${C.sky}18`,
            color: C.sky,
            fontWeight: 700,
            opacity: canLoad ? 1 : 0.5,
          }}
        >
          {busy ? 'Repo-Snapshot wird geladen…' : 'Repo-Snapshot laden'}
        </button>
      </section>
    </div>
  );
}
