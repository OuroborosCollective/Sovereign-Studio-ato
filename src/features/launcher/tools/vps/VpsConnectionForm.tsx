/**
 * VpsConnectionForm — SSH-Verbindungsformular.
 *
 * Felder: Host, Port, Benutzername, Auth-Methode (Passwort | SSH-Key).
 * Credentials werden NICHT in einem Store oder localStorage gespeichert.
 *
 * Issue #454
 */

import React, { useState } from 'react';
import { Terminal, Loader2, AlertCircle } from 'lucide-react';
import type { VpsCredentials } from './useVpsConnection';

const C = {
  bg:      '#0e1116',
  surface: '#161c24',
  border:  '#232d3a',
  accent:  '#00d9b1',
  text:    '#cdd9e5',
  textSub: '#768390',
  violet:  '#8b5cf6',
  error:   '#f87171',
} as const;

const input: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  background: C.bg,
  border: `1px solid ${C.border}`,
  borderRadius: 8,
  color: C.text,
  fontSize: 12,
  outline: 'none',
  boxSizing: 'border-box',
};

interface Props {
  connecting: boolean;
  error: string | null;
  onConnect: (creds: VpsCredentials) => void;
}

export function VpsConnectionForm({ connecting, error, onConnect }: Props) {
  const [host, setHost] = useState('');
  const [port, setPort] = useState('22');
  const [username, setUsername] = useState('');
  const [authMethod, setAuthMethod] = useState<'password' | 'key'>('password');
  const [password, setPassword] = useState('');
  const [privateKey, setPrivateKey] = useState('');

  const isValid = host.trim() && username.trim() &&
    (authMethod === 'password' ? password : privateKey.trim());

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid || connecting) return;
    onConnect({
      host: host.trim(),
      port: parseInt(port, 10) || 22,
      username: username.trim(),
      authMethod,
      password: authMethod === 'password' ? password : undefined,
      privateKey: authMethod === 'key' ? privateKey.trim() : undefined,
    });
  }

  return (
    <div style={{
      height: '100%', overflowY: 'auto', padding: 20,
      display: 'flex', flexDirection: 'column', gap: 20,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: C.violet, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Terminal size={18} color="#fff" />
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>VPS Verbinden</div>
          <div style={{ fontSize: 10, color: C.textSub }}>SSH-Zugangsdaten eingeben</div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 12px', borderRadius: 8,
          background: 'rgba(248,113,113,0.08)', border: `1px solid rgba(248,113,113,0.2)`,
        }}>
          <AlertCircle size={14} color={C.error} />
          <span style={{ fontSize: 11, color: C.error }}>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Host + Port */}
        <div style={{ display: 'flex', gap: 8 }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 10, color: C.textSub, fontWeight: 600, letterSpacing: '0.06em', display: 'block', marginBottom: 5 }}>
              HOST / IP
            </label>
            <input
              style={input}
              type="text"
              placeholder="192.168.1.1 oder server.example.com"
              value={host}
              onChange={(e) => setHost(e.target.value)}
              autoComplete="off"
              disabled={connecting}
            />
          </div>
          <div style={{ width: 70 }}>
            <label style={{ fontSize: 10, color: C.textSub, fontWeight: 600, letterSpacing: '0.06em', display: 'block', marginBottom: 5 }}>
              PORT
            </label>
            <input
              style={input}
              type="number"
              min={1}
              max={65535}
              value={port}
              onChange={(e) => setPort(e.target.value)}
              disabled={connecting}
            />
          </div>
        </div>

        {/* Username */}
        <div>
          <label style={{ fontSize: 10, color: C.textSub, fontWeight: 600, letterSpacing: '0.06em', display: 'block', marginBottom: 5 }}>
            BENUTZERNAME
          </label>
          <input
            style={input}
            type="text"
            placeholder="root oder ubuntu"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            disabled={connecting}
          />
        </div>

        {/* Auth Method */}
        <div>
          <label style={{ fontSize: 10, color: C.textSub, fontWeight: 600, letterSpacing: '0.06em', display: 'block', marginBottom: 8 }}>
            AUTHENTIFIZIERUNG
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            {(['password', 'key'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setAuthMethod(m)}
                style={{
                  flex: 1, padding: '7px 0', borderRadius: 8, fontSize: 11, fontWeight: 600,
                  border: `1px solid ${authMethod === m ? C.accent : C.border}`,
                  background: authMethod === m ? `${C.accent}15` : 'transparent',
                  color: authMethod === m ? C.accent : C.textSub,
                  cursor: 'pointer', transition: 'all 0.15s',
                }}
                disabled={connecting}
              >
                {m === 'password' ? 'Passwort' : 'SSH-Key'}
              </button>
            ))}
          </div>
        </div>

        {/* Auth Input */}
        {authMethod === 'password' ? (
          <div>
            <label style={{ fontSize: 10, color: C.textSub, fontWeight: 600, letterSpacing: '0.06em', display: 'block', marginBottom: 5 }}>
              PASSWORT
            </label>
            <input
              style={input}
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              disabled={connecting}
            />
          </div>
        ) : (
          <div>
            <label style={{ fontSize: 10, color: C.textSub, fontWeight: 600, letterSpacing: '0.06em', display: 'block', marginBottom: 5 }}>
              PRIVATE KEY (PEM)
            </label>
            <textarea
              style={{ ...input, minHeight: 100, resize: 'vertical', fontFamily: 'monospace', fontSize: 10 }}
              placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;..."
              value={privateKey}
              onChange={(e) => setPrivateKey(e.target.value)}
              disabled={connecting}
            />
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={!isValid || connecting}
          style={{
            padding: '10px 0', borderRadius: 10, fontSize: 12, fontWeight: 700,
            border: 'none', cursor: isValid && !connecting ? 'pointer' : 'not-allowed',
            background: isValid && !connecting ? C.violet : C.surface,
            color: isValid && !connecting ? '#fff' : C.textSub,
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            transition: 'all 0.15s',
          }}
        >
          {connecting ? (
            <><Loader2 size={14} className="animate-spin" /> Verbinde…</>
          ) : (
            'SSH Verbinden'
          )}
        </button>
      </form>

      <p style={{ fontSize: 10, color: C.textSub, textAlign: 'center' }}>
        Zugangsdaten werden nicht gespeichert — nur für diese Session.
      </p>
    </div>
  );
}
