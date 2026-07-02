/**
 * VpsWorkspace — Haupt-Ansicht nach SSH-Connect.
 *
 * Layout:
 *   Mobile (≤ 480px): Tab-Switch zwischen FileTree und Chat
 *   Desktop (> 480px): Zwei Spalten — FileTree 35% | Chat 65%
 *
 * Issue #454
 */

import React, { useState, useCallback } from 'react';
import { LogOut, Folder, MessageSquare } from 'lucide-react';
import { VpsFileTree } from './VpsFileTree';
import { VpsChat } from './VpsChat';
import type { ExecResult } from './useVpsConnection';

const C = {
  surface: '#161c24',
  border:  '#232d3a',
  accent:  '#00d9b1',
  text:    '#cdd9e5',
  textSub: '#768390',
  violet:  '#8b5cf6',
  error:   '#f87171',
} as const;

type MobileTab = 'tree' | 'chat';

interface Props {
  host: string;
  username: string;
  getTree: (path: string) => Promise<import('./useVpsConnection').DirEntry[]>;
  execCommand: (cmd: string) => Promise<ExecResult>;
  onDisconnect: () => void;
}

export function VpsWorkspace({ host, username, getTree, execCommand, onDisconnect }: Props) {
  const [mobileTab, setMobileTab] = useState<MobileTab>('chat');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  const handleSelectFile = useCallback((path: string) => {
    setSelectedFile(path);
    setMobileTab('chat');
  }, []);

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Status-Bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 14px', borderBottom: `1px solid ${C.border}`, flexShrink: 0,
        background: C.surface,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 7, height: 7, borderRadius: '50%', background: C.accent }} />
          <span style={{ fontSize: 10, color: C.textSub }}>
            <span style={{ color: C.text, fontWeight: 600 }}>{username}</span>
            @{host}
          </span>
        </div>
        <button
          type="button"
          onClick={onDisconnect}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            padding: '4px 8px', borderRadius: 6,
            border: `1px solid rgba(248,113,113,0.2)`,
            background: 'rgba(248,113,113,0.06)',
            color: C.error, fontSize: 10, fontWeight: 600, cursor: 'pointer',
          }}
        >
          <LogOut size={10} />
          Trennen
        </button>
      </div>

      {/* Mobile Tab-Switch */}
      <div className="flex lg:hidden" style={{
        display: 'flex', flexShrink: 0, borderBottom: `1px solid ${C.border}`,
      }}>
        {([
          { id: 'tree' as MobileTab, icon: Folder, label: 'Dateien' },
          { id: 'chat' as MobileTab, icon: MessageSquare, label: 'Chat' },
        ] as const).map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setMobileTab(id)}
            style={{
              flex: 1, padding: '8px 0', border: 'none', cursor: 'pointer',
              background: mobileTab === id ? `${C.violet}18` : 'transparent',
              color: mobileTab === id ? C.violet : C.textSub,
              fontSize: 11, fontWeight: 600,
              borderBottom: mobileTab === id ? `2px solid ${C.violet}` : '2px solid transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
              transition: 'all 0.15s',
            }}
          >
            <Icon size={12} />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
        {/* Desktop: Zwei Spalten */}
        <div style={{
          width: '35%', borderRight: `1px solid ${C.border}`,
          display: mobileTab === 'tree' ? 'flex' : 'none',
          flexDirection: 'column',
        }}
          className="md:flex"
        >
          <div style={{
            padding: '8px 10px', fontSize: 9, fontWeight: 700,
            color: C.textSub, letterSpacing: '0.1em',
            borderBottom: `1px solid ${C.border}`,
          }}>
            DATEISYSTEM
          </div>
          <VpsFileTree getTree={getTree} onSelectFile={handleSelectFile} />
        </div>

        <div style={{
          flex: 1,
          display: mobileTab === 'chat' ? 'flex' : 'none',
          flexDirection: 'column',
        }}
          className="md:flex"
        >
          <VpsChat
            host={host}
            username={username}
            execCommand={execCommand}
            onSelectFile={handleSelectFile}
          />
        </div>
      </div>

      {selectedFile && (
        <div style={{
          padding: '5px 14px', fontSize: 10, color: C.textSub,
          borderTop: `1px solid ${C.border}`, flexShrink: 0,
        }}>
          Ausgewählt: <span style={{ color: C.accent, fontFamily: 'monospace' }}>{selectedFile}</span>
        </div>
      )}
    </div>
  );
}
