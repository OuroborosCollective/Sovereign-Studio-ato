import React, { useState } from 'react';
import {
  parseIdleAwarenessPullRequestUrl,
  readIdleLiveAwarenessMode,
  readIdleLiveAwarenessPrUrl,
  writeIdleLiveAwarenessMode,
  writeIdleLiveAwarenessPrUrl,
  type IdleLiveAwarenessMode,
} from '../runtime/idleLiveAwareness';

const OPTIONS: Array<{
  mode: IdleLiveAwarenessMode;
  title: string;
  description: string;
}> = [
  {
    mode: 'off',
    title: 'Aus',
    description: 'Keine Idle-Beobachtung. Das ist die Standard- und Minimalberechtigung.',
  },
  {
    mode: 'observe',
    title: 'Beobachten',
    description: 'Nur lesende Live-Evidence prüfen und Zustandsänderungen im Sovereign-Monitor sichtbar machen.',
  },
  {
    mode: 'observe-notify',
    title: 'Beobachten + melden',
    description: 'Wie Beobachten; zusätzlich darf bei relevanten Übergängen eine bereits erlaubte Browser-Benachrichtigung erscheinen.',
  },
];

export const IdleLiveAwarenessSettingsCard: React.FC = () => {
  const [mode, setMode] = useState<IdleLiveAwarenessMode>(() => readIdleLiveAwarenessMode());
  const [prUrl, setPrUrl] = useState(() => readIdleLiveAwarenessPrUrl());
  const [targetValid, setTargetValid] = useState(() => !readIdleLiveAwarenessPrUrl() || Boolean(parseIdleAwarenessPullRequestUrl(readIdleLiveAwarenessPrUrl())));

  const selectMode = (nextMode: IdleLiveAwarenessMode): void => {
    setMode(nextMode);
    writeIdleLiveAwarenessMode(nextMode);
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('sovereign:idle-awareness-mode', { detail: { mode: nextMode } }));
    }
  };

  const updateTarget = (value: string): void => {
    setPrUrl(value);
    const parsed = parseIdleAwarenessPullRequestUrl(value);
    const valid = Boolean(parsed);
    setTargetValid(valid || value.trim().length === 0);
    if (!valid) return;
    if (writeIdleLiveAwarenessPrUrl(value) && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('sovereign:idle-awareness-target', { detail: { prUrl: value.trim() } }));
    }
  };

  return (
    <fieldset className="space-y-3 rounded-xl border border-sky-200 bg-sky-50 p-4" aria-describedby="idle-awareness-help">
      <legend className="px-1 text-[11px] font-black uppercase tracking-wide text-sky-900">
        Idle Live Awareness
      </legend>
      <p id="idle-awareness-help" className="text-[10px] leading-relaxed text-sky-900">
        Im Idle-Modus werden keine Änderungen ausgeführt. Kein Merge, Deploy, Patch, Workflow-Start oder Datenbank-Write.
        Die Freigabe kann hier jederzeit sofort entzogen werden.
      </p>

      <label className="block text-[10px] font-bold text-stone-700">
        Beobachteter Pull Request
        <input
          type="url"
          inputMode="url"
          value={prUrl}
          onChange={(event) => updateTarget(event.target.value)}
          placeholder="https://github.com/owner/repo/pull/123"
          aria-invalid={!targetValid}
          aria-describedby="idle-awareness-target-help"
          className="mt-1 w-full rounded-lg border border-sky-200 bg-white p-2 font-mono text-[10px] text-stone-900 outline-none focus:ring-2 focus:ring-sky-500"
        />
      </label>
      <p id="idle-awareness-target-help" className={`text-[9px] ${targetValid ? 'text-stone-500' : 'text-rose-700'}`}>
        {targetValid
          ? 'Scope: genau dieser PR und jeweils nur sein aktueller Head-SHA. Keine Repository-Schreibberechtigung.'
          : 'Bitte eine vollständige GitHub-PR-URL eintragen.'}
      </p>

      <div className="space-y-2" role="radiogroup" aria-label="Idle Live Awareness Berechtigung">
        {OPTIONS.map((option) => (
          <label key={option.mode} className="flex cursor-pointer items-start gap-3 rounded-lg border border-sky-100 bg-white p-3">
            <input
              type="radio"
              name="idle-live-awareness-mode"
              value={option.mode}
              checked={mode === option.mode}
              onChange={() => selectMode(option.mode)}
              className="mt-0.5"
            />
            <span className="min-w-0">
              <strong className="block text-[11px] text-stone-900">{option.title}</strong>
              <span className="block text-[10px] leading-relaxed text-stone-600">{option.description}</span>
            </span>
          </label>
        ))}
      </div>

      <p className="text-[9px] text-stone-500">
        Gerätebenachrichtigungen werden nie automatisch angefordert. Sie werden nur genutzt, wenn der Browser sie bereits erlaubt hat.
      </p>
    </fieldset>
  );
};