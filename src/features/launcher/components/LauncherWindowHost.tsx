/**
 * LauncherWindowHost — rendert alle offenen, nicht-minimierten Tool-Fenster.
 *
 * Sortiert nach z-index damit zuletzt fokussiertes Fenster ganz oben liegt.
 * Issue #453
 */

import React from 'react';
import { useLauncherStore } from '../useLauncherStore';
import { LauncherWindow } from './LauncherWindow';

export function LauncherWindowHost() {
  const windows = useLauncherStore((s) => s.windows);

  return (
    <>
      {windows
        .filter((w) => !w.minimized)
        .sort((a, b) => a.zIndex - b.zIndex)
        .map((w) => (
          <LauncherWindow key={w.id} id={w.id} zIndex={w.zIndex} />
        ))}
    </>
  );
}
