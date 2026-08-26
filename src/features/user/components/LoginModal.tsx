/**
 * LoginModal — release-rescue authentication surface.
 *
 * Google OAuth, GitHub OAuth, passkeys and account-key login remain backend
 * capabilities but are intentionally not exposed in the user-facing release
 * candidate.  The Play release surface offers only email/password login and
 * registration until the external identity-provider reviews are completed.
 */

import React, { useState } from 'react';
import { useUserStore } from '../useUserStore';

const C = {
  bg:      '#0e1116',
  surface: '#161c25',
  border:  '#263042',
  accent:  '#58a6ff',
  danger:  '#f85149',
  text:    '#e6edf3',
  sub:     '#8b949e',
};

const S: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed', inset: 0, zIndex: 9000,
    background: 'rgba(0,0,0,.72)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 16,
  },
  card: {
    background: C.surface, border: `1px solid ${C.border}`,
    borderRadius: 14, padding: 32, width: '100%', maxWidth: 400,
    boxShadow: '0 24px 60px rgba(0,0,0,.6)',
  },
  title: { fontSize: 20, fontWeight: 700, color: C.text, marginBottom: 4 },
  sub:   { fontSize: 13, color: C.sub, marginBottom: 24 },
  label: { display: 'block', fontSize: 11, color: C.sub, marginBottom: 5,
           textTransform: 'uppercase' as const, letterSpacing: '.5px' },
  input: {
    width: '100%', background: C.bg, border: `1px solid ${C.border}`,
    borderRadius: 7, color: C.text, fontSize: 14, padding: '11px 12px',
    minHeight: 44, outline: 'none', fontFamily: 'inherit', marginBottom: 14,
    boxSizing: 'border-box' as const,
  },
  btn: {
    width: '100%', border: 'none', borderRadius: 7, cursor: 'pointer',
    fontSize: 14, fontWeight: 600, padding: '11px 0', minHeight: 44,
    fontFamily: 'inherit', marginBottom: 10,
  },
  err: {
    background: '#2d1117', border: `1px solid ${C.danger}`,
    borderRadius: 7, color: C.danger, fontSize: 13,
    padding: '9px 12px', marginBottom: 14,
  },
  link: {
    background: 'none', border: 'none', color: C.accent, cursor: 'pointer',
    fontSize: 13, minHeight: 44, padding: '8px 4px', fontFamily: 'inherit',
  },
};

interface Props {
  onClose: () => void;
}

export function LoginModal({ onClose }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const { login, register, isLoading, error, clearError } = useUserStore();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    clearError();
    if (mode === 'login') {
      await login(email.trim(), password);
    } else {
      await register(email.trim(), password, displayName.trim());
    }
    if (!useUserStore.getState().error) onClose();
  }

  function switchMode() {
    clearError();
    setPassword('');
    setMode((current) => current === 'login' ? 'register' : 'login');
  }

  return (
    <div
      style={S.overlay}
      role="presentation"
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <div style={S.card} role="dialog" aria-modal="true" aria-label={mode === 'login' ? 'Anmelden' : 'Registrieren'}>
        <div style={S.title}>{mode === 'login' ? 'Anmelden' : 'Registrieren'}</div>
        <div style={S.sub}>
          {mode === 'login'
            ? 'Mit E-Mail und Passwort anmelden.'
            : 'Konto mit E-Mail und Passwort erstellen.'}
        </div>

        {error && <div style={S.err} role="alert">{error}</div>}

        <form onSubmit={handleSubmit}>
          {mode === 'register' && (
            <>
              <label style={S.label} htmlFor="sovereign-register-name">Name</label>
              <input
                id="sovereign-register-name"
                style={S.input}
                type="text"
                autoComplete="name"
                placeholder="Dein Name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                required
                autoFocus
              />
            </>
          )}

          <label style={S.label} htmlFor="sovereign-login-email">E-Mail</label>
          <input
            id="sovereign-login-email"
            style={S.input}
            type="email"
            autoComplete="email"
            inputMode="email"
            placeholder="du@beispiel.de"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoFocus={mode === 'login'}
          />

          <label style={S.label} htmlFor="sovereign-login-password">Passwort</label>
          <input
            id="sovereign-login-password"
            style={S.input}
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            placeholder={mode === 'register' ? 'Mindestens 8 Zeichen' : '••••••••'}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={mode === 'register' ? 8 : undefined}
          />

          <button
            type="submit"
            disabled={isLoading}
            style={{
              ...S.btn,
              background: C.accent,
              color: '#0d1117',
              opacity: isLoading ? .6 : 1,
              cursor: isLoading ? 'wait' : 'pointer',
            }}
          >
            {isLoading ? 'Bitte warten…' : mode === 'login' ? 'Anmelden' : 'Konto erstellen'}
          </button>
        </form>

        <div style={{ textAlign: 'center', fontSize: 13, color: C.sub, marginTop: 6 }}>
          {mode === 'login' ? 'Noch kein Konto?' : 'Schon registriert?'}{' '}
          <button type="button" style={S.link} onClick={switchMode}>
            {mode === 'login' ? 'Registrieren' : 'Anmelden'}
          </button>
        </div>
      </div>
    </div>
  );
}
