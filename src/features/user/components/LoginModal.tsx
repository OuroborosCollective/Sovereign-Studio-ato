/**
 * LoginModal — E-Mail/Passwort-Login + Google OAuth + Registrierung.
 * Issue #459
 */

import React, { useState } from 'react';
import { useUserStore } from '../useUserStore';

const C = {
  bg:      '#0e1116',
  surface: '#161c25',
  border:  '#263042',
  accent:  '#58a6ff',
  green:   '#3fb950',
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
    borderRadius: 7, color: C.text, fontSize: 14, padding: '9px 12px',
    outline: 'none', fontFamily: 'inherit', marginBottom: 14,
    boxSizing: 'border-box' as const,
  },
  btn: {
    width: '100%', border: 'none', borderRadius: 7, cursor: 'pointer',
    fontSize: 14, fontWeight: 600, padding: '10px 0',
    fontFamily: 'inherit', marginBottom: 10,
  },
  err: {
    background: '#2d1117', border: `1px solid ${C.danger}`,
    borderRadius: 7, color: C.danger, fontSize: 13,
    padding: '9px 12px', marginBottom: 14,
  },
  link: {
    background: 'none', border: 'none', color: C.accent, cursor: 'pointer',
    fontSize: 13, padding: 0, fontFamily: 'inherit',
  },
  divider: {
    display: 'flex', alignItems: 'center', gap: 10,
    marginBottom: 12, color: C.sub, fontSize: 12,
  },
  line: { flex: 1, height: 1, background: C.border },
};

interface Props {
  onClose: () => void;
}

export function LoginModal({ onClose }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [googleLoading, setGoogleLoading] = useState(false);

  const { login, register, loginWithGoogle, isLoading, error, clearError } = useUserStore();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    clearError();
    if (mode === 'login') {
      await login(email, password);
    } else {
      await register(email, password, displayName);
    }
    // Close on success (user will be set in store)
    if (!useUserStore.getState().error) onClose();
  }

  async function handleGoogle() {
    setGoogleLoading(true);
    clearError();
    try {
      const { GoogleAuth } = await import('@codetrix-studio/capacitor-google-auth');
      const googleUser = await GoogleAuth.signIn();
      const idToken = googleUser.authentication.idToken;
      await loginWithGoogle(idToken);
      if (!useUserStore.getState().error) onClose();
    } catch {
      useUserStore.setState({ error: 'Google-Login abgebrochen oder nicht verfügbar' });
    } finally {
      setGoogleLoading(false);
    }
  }

  function switchMode() {
    clearError();
    setMode(m => m === 'login' ? 'register' : 'login');
  }

  return (
    <div style={S.overlay} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={S.card}>
        <div style={S.title}>{mode === 'login' ? 'Anmelden' : 'Registrieren'}</div>
        <div style={S.sub}>
          {mode === 'login' ? 'Willkommen zurück.' : 'Kostenloses Konto erstellen — 500 Credits inklusive.'}
        </div>

        {error && <div style={S.err}>{error}</div>}

        <form onSubmit={handleSubmit}>
          {mode === 'register' && (
            <>
              <label style={S.label}>Name</label>
              <input
                style={S.input} type="text" placeholder="Dein Name"
                value={displayName} onChange={e => setDisplayName(e.target.value)}
                required autoFocus
              />
            </>
          )}
          <label style={S.label}>E-Mail</label>
          <input
            style={S.input} type="email" placeholder="du@beispiel.de"
            value={email} onChange={e => setEmail(e.target.value)}
            required autoFocus={mode === 'login'}
          />
          <label style={S.label}>Passwort</label>
          <input
            style={S.input} type="password"
            placeholder={mode === 'register' ? 'Mindestens 8 Zeichen' : '••••••••'}
            value={password} onChange={e => setPassword(e.target.value)}
            required minLength={mode === 'register' ? 8 : undefined}
          />
          <button
            type="submit"
            disabled={isLoading}
            style={{ ...S.btn, background: C.accent, color: '#0d1117', opacity: isLoading ? .6 : 1 }}
          >
            {isLoading ? 'Bitte warten…' : mode === 'login' ? 'Anmelden' : 'Konto erstellen'}
          </button>
        </form>

        <div style={S.divider}><span style={S.line}/><span>oder</span><span style={S.line}/></div>

        <button
          style={{ ...S.btn, background: '#21262d', color: C.text, border: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
          onClick={handleGoogle}
          disabled={googleLoading || isLoading}
        >
          <GoogleIcon />
          {googleLoading ? 'Verbinde…' : 'Mit Google anmelden'}
        </button>

        <div style={{ textAlign: 'center', fontSize: 13, color: C.sub, marginTop: 6 }}>
          {mode === 'login' ? 'Noch kein Konto?' : 'Schon registriert?'}{' '}
          <button style={S.link} onClick={switchMode}>
            {mode === 'login' ? 'Registrieren' : 'Anmelden'}
          </button>
        </div>
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48">
      <path fill="#EA4335" d="M24 9.5c3.14 0 5.95 1.08 8.17 2.85l6.09-6.09C34.46 3.19 29.52 1 24 1 14.82 1 7.07 6.48 3.64 14.18l7.08 5.5C12.42 13.38 17.74 9.5 24 9.5z"/>
      <path fill="#4285F4" d="M46.1 24.55c0-1.64-.15-3.22-.42-4.75H24v9h12.42c-.54 2.9-2.18 5.36-4.65 7.02l7.19 5.58C42.93 37.3 46.1 31.36 46.1 24.55z"/>
      <path fill="#FBBC05" d="M10.72 28.68A14.53 14.53 0 0 1 9.5 24c0-1.63.28-3.22.72-4.68L3.14 13.82A23.93 23.93 0 0 0 0 24c0 3.87.93 7.54 2.55 10.78l8.17-6.1z"/>
      <path fill="#34A853" d="M24 47c5.52 0 10.16-1.83 13.55-4.97l-7.19-5.58C28.62 37.9 26.42 38.5 24 38.5c-6.26 0-11.58-3.88-13.28-9.32l-7.08 5.5C7.07 41.52 14.82 47 24 47z"/>
    </svg>
  );
}
