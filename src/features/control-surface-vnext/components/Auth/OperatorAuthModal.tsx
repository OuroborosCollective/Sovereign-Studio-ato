import React, { useState } from 'react';
import { motion } from 'motion/react';
import { AlertTriangle, Fingerprint, KeyRound, LogOut, ShieldCheck, User, X } from 'lucide-react';
import { useUserStore } from '../../../user/useUserStore';
import { playKeystrokeChirp } from '../../utils/audio';

interface Props { isOpen: boolean; onClose: () => void; }

export function OperatorAuthModal({ isOpen, onClose }: Props) {
  const { user, isLoading, error, login, loginWithAccountKey, logout, clearError } = useUserStore();
  const [accountKey, setAccountKey] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  if (!isOpen) return null;

  const submitAccountKey = async (event: React.FormEvent) => {
    event.preventDefault();
    const key = accountKey.trim();
    if (!key || isLoading) return;
    clearError();
    try { await loginWithAccountKey(key); }
    finally { setAccountKey(''); }
  };
  const submitPassword = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim() || !password || isLoading) return;
    clearError();
    try { await login(email.trim(), password); }
    finally { setPassword(''); }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-3"
      role="dialog" aria-modal="true" aria-label="Sovereign account session"
      onKeyDown={(event) => { if (event.key === 'Escape') onClose(); }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 14 }} animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 14 }}
        className="relative w-full max-w-lg bg-[var(--carbon-deep)] border border-[rgba(255,30,56,0.35)] rounded-xl shadow-[0_14px_54px_rgba(0,0,0,0.9),0_0_28px_rgba(255,30,56,0.17)] theme-diamond-cut overflow-hidden"
      >
        <div className="h-[2px] bg-gradient-to-r from-transparent via-[var(--red-laser)] to-transparent" />
        <header className="px-5 py-4 border-b border-white/5 flex items-center justify-between bg-[var(--carbon-base)]">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg border border-[var(--red-laser)] bg-[var(--carbon-surface)] flex items-center justify-center text-[var(--red-laser)] shadow-[0_0_12px_rgba(255,30,56,0.3)]"><Fingerprint size={20} /></div>
            <div className="min-w-0"><div className="font-mono text-xs sm:text-sm font-black tracking-widest text-white">SERVER-BOUND OPERATOR SESSION</div><div className="font-mono text-[9px] text-[var(--text-dim)]">HTTP-ONLY COOKIE · NO FRONTEND TOKEN STORAGE</div></div>
          </div>
          <button type="button" aria-label="Close account session" onClick={onClose} className="p-2 text-[var(--text-muted)] hover:text-white"><X size={18} /></button>
        </header>

        <div className="p-5 space-y-4 font-mono">
          {error && <div className="p-3 rounded border border-[var(--red-alert)] bg-[rgba(255,30,56,0.1)] text-[var(--red-alert)] text-xs flex gap-2"><AlertTriangle size={14} className="shrink-0" /><span>{error}</span></div>}

          {user && !user.isGuest ? (
            <div className="space-y-4">
              <div className="p-4 rounded-lg border border-[rgba(16,185,129,0.35)] bg-[rgba(16,185,129,0.07)]">
                <div className="flex items-center gap-2 text-[var(--emerald-seal)] text-[10px] font-bold tracking-widest"><ShieldCheck size={14} /> BACKEND SESSION READBACK</div>
                <div className="mt-3 grid grid-cols-[90px_1fr] gap-x-3 gap-y-1 text-[10.5px]">
                  <span className="text-[var(--text-dim)]">IDENTITY</span><span className="text-white truncate">{user.displayName}</span>
                  <span className="text-[var(--text-dim)]">ACCOUNT</span><span className="text-[var(--text-muted)] truncate">{user.email}</span>
                  <span className="text-[var(--text-dim)]">ROLE</span><span className="text-white">{user.role}</span>
                  <span className="text-[var(--text-dim)]">SESSION</span><span className="text-[var(--emerald-seal)]">AUTHENTICATED</span>
                </div>
              </div>
              <button type="button" disabled={isLoading} onClick={() => { playKeystrokeChirp(); void logout(); }} className="w-full min-h-11 rounded-lg border border-[rgba(255,30,56,0.35)] bg-[rgba(255,30,56,0.1)] text-[var(--red-laser)] hover:bg-[var(--red-laser)] hover:text-white font-bold text-xs flex items-center justify-center gap-2 disabled:opacity-50"><LogOut size={14} /> END BACKEND SESSION</button>
            </div>
          ) : (
            <>
              {user?.isGuest && <div className="p-3 rounded border border-white/10 bg-[var(--carbon-surface)] text-[var(--text-muted)] text-[10px]">GUEST SESSION ACTIVE · Authenticate below to upgrade this backend session before repository execution.</div>}
              <form onSubmit={submitAccountKey} className="space-y-2 p-3.5 rounded-lg bg-[var(--carbon-surface)] border border-white/10">
                <label htmlFor="vnext-account-key" className="text-[9.5px] text-[var(--text-muted)] tracking-wider">ACCOUNT KEY · SENT ONCE TO BACKEND, NEVER PERSISTED HERE</label>
                <div className="relative"><KeyRound size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--red-laser)]" /><input id="vnext-account-key" type="password" autoComplete="off" value={accountKey} onChange={(e) => setAccountKey(e.target.value)} placeholder="svk_…" className="w-full min-h-11 pl-9 pr-3 rounded bg-[var(--carbon-deep)] border border-white/10 focus:border-[var(--red-laser)] outline-none text-xs text-white" /></div>
                <button type="submit" disabled={!accountKey.trim() || isLoading} className="w-full min-h-11 rounded bg-[var(--red-pulse)] text-white font-black text-xs disabled:opacity-40">{isLoading ? 'VERIFYING SERVER SESSION…' : 'AUTHENTICATE WITH ACCOUNT KEY'}</button>
              </form>
              <div className="flex items-center gap-2 text-[9px] text-[var(--text-dim)]"><div className="h-px flex-1 bg-white/5" />OR PASSWORD SESSION<div className="h-px flex-1 bg-white/5" /></div>
              <form onSubmit={submitPassword} className="space-y-2">
                <div className="relative"><User size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" /><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="account@example.com" className="w-full min-h-11 pl-9 pr-3 rounded bg-[var(--carbon-surface)] border border-white/10 focus:border-[var(--red-laser)] outline-none text-xs text-white" /></div>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" className="w-full min-h-11 px-3 rounded bg-[var(--carbon-surface)] border border-white/10 focus:border-[var(--red-laser)] outline-none text-xs text-white" />
                <button type="submit" disabled={!email.trim() || !password || isLoading} className="w-full min-h-11 rounded border border-white/15 bg-[var(--carbon-surface)] text-white font-bold text-xs disabled:opacity-40">SIGN IN</button>
              </form>
            </>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
