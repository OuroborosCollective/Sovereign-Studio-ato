/**
 * SkillScanPanel — Scan any GitHub repo for skills, adapt & install.
 *
 * Opens as an overlay from /scan-skills slash command.
 * Shows detected skills with framework badge, lets user install each.
 */

import React, { useState } from 'react';
import { useSkillsStore } from '../useSkillsStore';
import type { FoundSkill } from '../skillsApi';

const C = {
  bg: '#0e1116',
  card: '#161c24',
  border: '#232d3a',
  accent: '#00d9b1',
  text: '#cdd9e5',
  muted: '#768390',
  danger: '#f85149',
  warn: '#d29922',
};

const FRAMEWORK_COLORS: Record<string, string> = {
  replit:  '#7b6fff',
  cursor:  '#00b4d8',
  claude:  '#c77dff',
  openai:  '#10a37f',
  fastmcp: '#ff9f1c',
  generic: '#768390',
  unknown: '#444',
};

interface Props {
  onClose: () => void;
  onInstalled?: (slug: string) => void;
}

export function SkillScanPanel({ onClose, onInstalled }: Props) {
  const { scanRepo, adaptAndInstall, scanning, scanResult, scanError } = useSkillsStore();

  const [repoInput, setRepoInput] = useState('');
  const [installing, setInstalling] = useState<string | null>(null);
  const [installMsg, setInstallMsg] = useState<Record<string, string>>({});
  const [installed, setInstalled] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);

  const handleScan = async () => {
    setErr(null);
    const clean = repoInput.trim().replace(/^https?:\/\/github\.com\//, '').replace(/\.git$/, '');
    const [owner, repo] = clean.split('/');
    if (!owner || !repo) { setErr('Format: owner/repo oder GitHub-URL'); return; }
    try { await scanRepo(owner, repo); }
    catch (e) { setErr((e as Error).message); }
  };

  const handleInstall = async (found: FoundSkill) => {
    const clean = repoInput.trim().replace(/^https?:\/\/github\.com\//, '').replace(/\.git$/, '');
    const [owner, repo] = clean.split('/');
    setInstalling(found.path);
    setErr(null);
    try {
      const sk = await adaptAndInstall(owner, repo, found, (msg) =>
        setInstallMsg((m) => ({ ...m, [found.path]: msg })),
      );
      setInstalled((s) => new Set(s).add(found.path));
      onInstalled?.(sk.slug);
    } catch (e) {
      setErr(`${found.path}: ${(e as Error).message}`);
    } finally {
      setInstalling(null);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(14,17,22,0.9)', backdropFilter: 'blur(8px)',
        display: 'flex', alignItems: 'flex-end', justifyContent: 'center', padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 480, maxHeight: '82vh', overflowY: 'auto',
          background: C.card, borderRadius: 20, border: `1px solid ${C.border}`,
          padding: 20, display: 'flex', flexDirection: 'column', gap: 16,
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ color: C.accent, fontWeight: 700, fontSize: 15 }}>🔍 Skill-Scanner</div>
            <div style={{ color: C.muted, fontSize: 12, marginTop: 2 }}>
              Erkennt Skills aus jedem Repo — Replit, Cursor, Claude, MCP, Custom
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: C.muted, fontSize: 20, cursor: 'pointer' }}>✕</button>
        </div>

        {/* Repo Input */}
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            value={repoInput}
            onChange={(e) => setRepoInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleScan()}
            placeholder="owner/repo oder GitHub-URL"
            style={{
              flex: 1, background: C.bg, border: `1px solid ${C.border}`,
              borderRadius: 10, padding: '8px 12px', color: C.text, fontSize: 13, outline: 'none',
            }}
          />
          <button
            onClick={handleScan}
            disabled={scanning || !repoInput.trim()}
            style={{
              background: C.accent, border: 'none', borderRadius: 10,
              padding: '8px 16px', color: '#000', fontWeight: 700, fontSize: 13, cursor: 'pointer',
              opacity: scanning ? 0.6 : 1,
            }}
          >
            {scanning ? '…' : 'Scannen'}
          </button>
        </div>

        {/* Error */}
        {(err || scanError) && (
          <div style={{ background: `${C.danger}22`, border: `1px solid ${C.danger}44`, borderRadius: 10, padding: '8px 12px', color: C.danger, fontSize: 12 }}>
            {err || scanError}
          </div>
        )}

        {/* Results */}
        {scanResult && (
          <>
            <div style={{ color: C.muted, fontSize: 12 }}>
              {scanResult.total} Skills gefunden — Frameworks: {scanResult.frameworks_detected.join(', ')}
            </div>

            {scanResult.found.length === 0 && (
              <div style={{ color: C.muted, fontSize: 13, textAlign: 'center', padding: 20 }}>
                Keine Skills erkannt. Unterstützte Formate: SKILL.md, .cursorrules, AGENTS.md, prompts/, server.py MCP Tools.
              </div>
            )}

            {scanResult.found.map((found) => (
              <div
                key={found.path}
                style={{
                  background: C.bg, borderRadius: 12, border: `1px solid ${C.border}`,
                  padding: 12, display: 'flex', flexDirection: 'column', gap: 6,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    background: FRAMEWORK_COLORS[found.framework] || FRAMEWORK_COLORS.unknown,
                    color: '#fff', fontSize: 10, fontWeight: 700, padding: '2px 7px',
                    borderRadius: 6, textTransform: 'uppercase', letterSpacing: 0.5,
                  }}>
                    {found.framework}
                  </span>
                  <span style={{ color: C.text, fontSize: 13, fontWeight: 600 }}>{found.name}</span>
                </div>
                <div style={{ color: C.muted, fontSize: 11, fontFamily: 'monospace' }}>{found.path}</div>
                {found.preview && (
                  <div style={{ color: C.muted, fontSize: 11, lineHeight: 1.4 }}>
                    {found.preview.slice(0, 120)}{found.preview.length > 120 ? '…' : ''}
                  </div>
                )}
                {installMsg[found.path] && (
                  <div style={{ color: C.accent, fontSize: 11 }}>{installMsg[found.path]}</div>
                )}
                <button
                  onClick={() => handleInstall(found)}
                  disabled={installing === found.path || installed.has(found.path)}
                  style={{
                    background: installed.has(found.path) ? `${C.accent}33` : C.accent,
                    border: 'none', borderRadius: 8, padding: '6px 14px',
                    color: installed.has(found.path) ? C.accent : '#000',
                    fontWeight: 700, fontSize: 12, cursor: 'pointer',
                    alignSelf: 'flex-start',
                    opacity: installing === found.path ? 0.7 : 1,
                  }}
                >
                  {installed.has(found.path) ? '✓ Installiert' : installing === found.path ? '…' : '+ Installieren'}
                </button>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
