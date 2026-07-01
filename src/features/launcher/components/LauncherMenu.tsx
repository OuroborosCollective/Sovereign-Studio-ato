/**
 * LauncherMenu — App-Grid-Overlay für den Sovereign Launcher.
 *
 * Öffnet sich als Bottom-Sheet über dem Chat wenn isMenuOpen === true.
 * Folgt dem bestehenden RepoTreeExplorer-Muster (BuilderContainer L4400):
 * fixed, bottom-0, backdrop-blur, rounded-t-2xl.
 *
 * Issue #452
 */

import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { useLauncherStore } from '../useLauncherStore';
import { LAUNCHER_REGISTRY, type LauncherEntry } from '../launcherRegistry';

// ── LauncherMenu ─────────────────────────────────────────────────────────────

export function LauncherMenu() {
  const { isMenuOpen, closeMenu, launchTool } = useLauncherStore();

  // Document-level ESC-Handler — zuverlässig unabhängig vom Fokus
  useEffect(() => {
    if (!isMenuOpen) return;
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') closeMenu(); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [isMenuOpen, closeMenu]);

  if (!isMenuOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[200] bg-black/40 backdrop-blur-sm"
        onClick={closeMenu}
        aria-hidden="true"
        data-testid="launcher-menu-backdrop"
      />

      {/* Drawer — slide up von unten, max 70vh */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Sovereign Launcher"
        data-testid="launcher-menu"
        className="fixed bottom-0 left-0 right-0 z-[201] flex flex-col bg-[#0e1116]/95 backdrop-blur-2xl border-t border-white/10 rounded-t-2xl shadow-2xl"
        style={{ maxHeight: '70vh', maxWidth: 480, margin: '0 auto' }}
        onKeyDown={(e) => { if (e.key === 'Escape') closeMenu(); }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-white/10 shrink-0">
          <div>
            <h2 className="text-xs font-black text-white uppercase tracking-widest">
              Sovereign Launcher
            </h2>
            <p className="text-[10px] text-white/40 mt-0.5">Tool auswählen</p>
          </div>
          <button
            onClick={closeMenu}
            className="p-1.5 rounded-lg text-white/40 hover:text-white hover:bg-white/10 transition-colors"
            aria-label="Launcher schließen"
          >
            <X size={16} />
          </button>
        </div>

        {/* Icon Grid */}
        <div className="overflow-y-auto flex-1 p-4">
          {LAUNCHER_REGISTRY.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 gap-3">
              <span className="text-3xl opacity-20">⬡</span>
              <p className="text-white/30 text-xs text-center">
                Noch keine Tools registriert.
              </p>
              <p className="text-white/20 text-[10px] text-center">
                Tools werden in LAUNCHER_REGISTRY eingetragen.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-3">
              {LAUNCHER_REGISTRY.map((entry) => (
                <LauncherTile
                  key={entry.id}
                  entry={entry}
                  onLaunch={() => launchTool(entry.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ── LauncherTile ─────────────────────────────────────────────────────────────

interface LauncherTileProps {
  entry: LauncherEntry;
  onLaunch: () => void;
}

function LauncherTile({ entry, onLaunch }: LauncherTileProps) {
  const Icon = entry.icon;

  return (
    <button
      onClick={onLaunch}
      disabled={entry.disabled}
      data-testid={`launcher-tile-${entry.id}`}
      className="relative flex flex-col items-center gap-2 p-3 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 hover:border-white/20 active:scale-95 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-white/20"
    >
      {/* Badge */}
      {entry.badge && (
        <span className="absolute top-1.5 right-1.5 text-[8px] font-black bg-indigo-500 text-white px-1.5 py-0.5 rounded-full leading-none">
          {entry.badge}
        </span>
      )}

      {/* Icon */}
      <div
        className={`w-10 h-10 rounded-xl ${entry.color} flex items-center justify-center shadow-lg`}
      >
        <Icon size={20} className="text-white" />
      </div>

      {/* Label */}
      <span className="text-[10px] font-bold text-white/80 text-center leading-tight line-clamp-2">
        {entry.label}
      </span>
    </button>
  );
}
