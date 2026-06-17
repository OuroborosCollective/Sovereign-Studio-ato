import React from 'react';

interface LoginViewProps {
  onLogin: () => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLogin }) => {
  return (
    <main className="min-h-screen p-4 text-slate-100">
      <section className="mx-auto flex min-h-[calc(100vh-2rem)] max-w-4xl flex-col justify-center rounded-3xl border border-slate-700 bg-slate-950/80 p-6 shadow-2xl">
        <div className="max-w-2xl">
          <p className="mb-3 inline-flex rounded-full border border-emerald-400/30 bg-emerald-500/10 px-3 py-1 text-xs font-bold uppercase tracking-wide text-emerald-200">
            Sovereign Tool · Local Operator Shell
          </p>
          <h1 className="text-3xl font-black tracking-tight text-white md:text-5xl">Sovereign Canvas Tool</h1>
          <p className="mt-4 text-sm leading-6 text-slate-300 md:text-base">
            Starte die geschützte Arbeitsfläche für Repo-Snapshot, NoCode-Live-Monitor, Pattern Memory,
            Telemetry Log, Remote Memory Gateway und Draft-PR-Automation.
          </p>
        </div>

        <div className="mt-8 grid gap-3 text-sm md:grid-cols-3">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="font-bold text-slate-100">1 · Repo laden</div>
            <p className="mt-1 text-xs text-slate-400">GitHub-URL eintragen und echten Repository-Snapshot prüfen.</p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="font-bold text-slate-100">2 · Monitor prüfen</div>
            <p className="mt-1 text-xs text-slate-400">Runtime, Telemetry, Pattern-Kategorien und Gateway sichtbar halten.</p>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="font-bold text-slate-100">3 · Draft PR bauen</div>
            <p className="mt-1 text-xs text-slate-400">Erst nach Guards, Reviews und Runtime-Checks veröffentlichen.</p>
          </div>
        </div>

        <button
          className="mt-8 w-full rounded-2xl border border-cyan-300/40 bg-cyan-400/15 px-5 py-4 text-left text-lg font-black uppercase tracking-wide text-cyan-100 shadow-lg shadow-cyan-950/30 transition hover:bg-cyan-400/25 md:w-fit"
          onClick={onLogin}
          type="button"
        >
          Sovereign Arbeitsfläche öffnen
        </button>

        <p className="mt-4 text-xs text-slate-500">
          Hinweis: Ohne geladenes Repository bleibt Full Auto bewusst blockiert. Das ist kein Freeze, sondern ein Guard.
        </p>
      </section>
    </main>
  );
};
