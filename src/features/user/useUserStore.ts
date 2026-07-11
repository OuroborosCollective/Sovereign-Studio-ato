/**
 * useUserStore — Zustand-Store für den eingeloggten User.
 *
 * Implementiert Login (E-Mail/Passwort + Google OAuth), Register,
 * Logout und Session-Restore via /api/auth/me.
 *
 * Session läuft über HTTP-Only Cookie (kein Token im localStorage).
 * Issue #459
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { loginWithAccountKey as securityAccountKeyLogin, loginWithPasskey as securityPasskeyLogin } from '../security/securityApi';

export type UserRole = 'user' | 'admin' | 'superadmin';
export type SubscriptionStatus = 'active' | 'canceled' | 'past_due' | 'trialing' | 'free';

export interface CurrentUser {
  id: string;
  email: string;
  displayName: string;
  role: UserRole;
  credits: number;
  subscriptionStatus: SubscriptionStatus;
  isBanned: boolean;
  createdAt: number;
  avatarUrl?: string;
  googleId?: string;
  githubId?: string;
  githubUsername?: string;
  // NOTE: githubAccessToken wird NICHT im Frontend gespeichert
  // Token bleibt verschlüsselt im Backend für sichere API-Operationen
}

const configuredApiBase = (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined)?.trim();
const API_BASE: string = configuredApiBase || 'https://sovereign-backend.arelorian.de';

async function authFetch(path: string, options?: RequestInit) {
  return fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
  });
}

const USER_ROLES: readonly UserRole[] = ['user', 'admin', 'superadmin'];
const SUBSCRIPTION_STATUSES: readonly SubscriptionStatus[] = ['active', 'canceled', 'past_due', 'trialing', 'free'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function pickString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeCurrentUser(value: unknown): CurrentUser | null {
  if (!isRecord(value)) return null;

  const id = pickString(value, 'id');
  const email = pickString(value, 'email');
  if (!id || !email) return null;

  const displayName = pickString(value, 'displayName') || email.split('@')[0] || 'User';
  const roleValue = pickString(value, 'role');
  const statusValue = pickString(value, 'subscriptionStatus');
  const credits = typeof value.credits === 'number' && Number.isFinite(value.credits)
    ? Math.max(0, value.credits)
    : 0;
  const createdAt = typeof value.createdAt === 'number' && Number.isFinite(value.createdAt)
    ? value.createdAt
    : Date.now();

  return {
    id,
    email,
    displayName,
    role: USER_ROLES.includes(roleValue as UserRole) ? roleValue as UserRole : 'user',
    credits,
    subscriptionStatus: SUBSCRIPTION_STATUSES.includes(statusValue as SubscriptionStatus)
      ? statusValue as SubscriptionStatus
      : 'free',
    isBanned: value.isBanned === true,
    createdAt,
    avatarUrl: pickString(value, 'avatarUrl') || undefined,
    googleId: pickString(value, 'googleId') || undefined,
    githubId: pickString(value, 'githubId') || undefined,
    githubUsername: pickString(value, 'githubUsername') || undefined,
    // githubAccessToken wird NIEMALS ins Frontend übertragen
  };
}

export interface GitHubOAuthExchange {
  code: string;
  state: string;
  codeVerifier: string;
}

interface UserStore {
  user: CurrentUser | null;
  isLoading: boolean;
  error: string | null;
  // Internal helpers used by admin panel (Issue #460)
  setUser: (user: CurrentUser) => void;
  clearUser: () => void;
  adjustCredits: (delta: number) => void;
  // Auth actions (Issue #459)
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: (idToken: string) => Promise<void>;
  loginWithGitHub: (exchange: GitHubOAuthExchange) => Promise<void>;
  loginWithPasskey: (email?: string) => Promise<void>;
  loginWithAccountKey: (key: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  clearError: () => void;
}

export const useUserStore = create<UserStore>()(
  persist(
    (set, get) => ({
      user: null,
      isLoading: false,
      error: null,

      setUser: (user) => set({ user }),
      clearUser: () => set({ user: null }),
      adjustCredits: (delta) => {
        const { user } = get();
        if (!user) return;
        set({ user: { ...user, credits: Math.max(0, user.credits + delta) } });
      },
      clearError: () => set({ error: null }),

      login: async (email, password) => {
        set({ isLoading: true, error: null });
        try {
          const res = await authFetch('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password }),
          });
          if (!res.ok) {
            const d = await res.json().catch(() => ({}));
            set({ isLoading: false, error: (d as { error?: string }).error ?? 'Login fehlgeschlagen' });
            return;
          }
          const user = normalizeCurrentUser(await res.json());
          if (!user) {
            set({ isLoading: false, error: 'Ungültige User-Antwort vom Server' });
            return;
          }
          set({ user, isLoading: false, error: null });
        } catch {
          set({ isLoading: false, error: 'Verbindungsfehler' });
        }
      },

      loginWithGoogle: async (idToken) => {
        set({ isLoading: true, error: null });
        try {
          const res = await authFetch('/api/auth/google', {
            method: 'POST',
            body: JSON.stringify({ idToken }),
          });
          if (!res.ok) {
            const d = await res.json().catch(() => ({}));
            set({ isLoading: false, error: (d as { error?: string }).error ?? 'Google-Login fehlgeschlagen' });
            return;
          }
          const user = normalizeCurrentUser(await res.json());
          if (!user) {
            set({ isLoading: false, error: 'Ungültige User-Antwort vom Server' });
            return;
          }
          set({ user, isLoading: false, error: null });
        } catch {
          set({ isLoading: false, error: 'Verbindungsfehler' });
        }
      },

      loginWithGitHub: async (exchange) => {
        set({ isLoading: true, error: null });
        try {
          const res = await authFetch('/api/auth/github', {
            method: 'POST',
            body: JSON.stringify({
              code: exchange.code,
              state: exchange.state,
              code_verifier: exchange.codeVerifier,
            }),
          });
          if (!res.ok) {
            const d = await res.json().catch(() => ({}));
            set({ isLoading: false, error: (d as { error?: string }).error ?? 'GitHub-Login fehlgeschlagen' });
            return;
          }
          const user = normalizeCurrentUser(await res.json());
          if (!user) {
            set({ isLoading: false, error: 'Ungültige User-Antwort vom Server' });
            return;
          }
          set({ user, isLoading: false, error: null });
        } catch {
          set({ isLoading: false, error: 'Verbindungsfehler' });
        }
      },

      loginWithPasskey: async (email = '') => {
        set({ isLoading: true, error: null });
        try {
          const user = normalizeCurrentUser(await securityPasskeyLogin(email));
          if (!user) throw new Error('Ungültige User-Antwort vom Server');
          set({ user, isLoading: false, error: null });
        } catch (reason) {
          set({ isLoading: false, error: reason instanceof Error ? reason.message : 'Passkey-Login fehlgeschlagen' });
        }
      },

      loginWithAccountKey: async (key) => {
        set({ isLoading: true, error: null });
        try {
          const user = normalizeCurrentUser(await securityAccountKeyLogin(key));
          if (!user) throw new Error('Ungültige User-Antwort vom Server');
          set({ user, isLoading: false, error: null });
        } catch (reason) {
          set({ isLoading: false, error: reason instanceof Error ? reason.message : 'Account-Key-Login fehlgeschlagen' });
        }
      },

      register: async (email, password, displayName) => {
        set({ isLoading: true, error: null });
        try {
          const res = await authFetch('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify({ email, password, displayName }),
          });
          if (!res.ok) {
            const d = await res.json().catch(() => ({}));
            set({ isLoading: false, error: (d as { error?: string }).error ?? 'Registrierung fehlgeschlagen' });
            return;
          }
          const user = normalizeCurrentUser(await res.json());
          if (!user) {
            set({ isLoading: false, error: 'Ungültige User-Antwort vom Server' });
            return;
          }
          set({ user, isLoading: false, error: null });
        } catch {
          set({ isLoading: false, error: 'Verbindungsfehler' });
        }
      },

      logout: async () => {
        set({ isLoading: true, error: null });
        try {
          const response = await authFetch('/api/auth/logout', { method: 'POST' });
          if (!response.ok) {
            const payload = await response.json().catch(() => ({})) as { error?: string };
            set({ isLoading: false, error: payload.error || `Logout HTTP ${response.status}` });
            return;
          }
          set({ user: null, isLoading: false, error: null });
        } catch {
          set({ isLoading: false, error: 'Logout konnte die Backend-Session nicht bestätigen.' });
        }
      },

      refreshUser: async () => {
        set({ isLoading: true, error: null });
        try {
          const res = await authFetch('/api/auth/me');
          if (!res.ok) {
            set({ user: null, isLoading: false, error: `Session nicht bestätigt (HTTP ${res.status}).` });
            return;
          }
          const user = normalizeCurrentUser(await res.json());
          if (!user) {
            set({ user: null, isLoading: false, error: 'Backend lieferte keine gültige Session-Evidence.' });
            return;
          }
          set({ user, isLoading: false, error: null });
        } catch {
          set({
            user: null,
            isLoading: false,
            error: 'Session konnte wegen eines Verbindungsfehlers nicht bestätigt werden.',
          });
        }
      },
    }),
    {
      name: 'sovereign-user',
      // Only persist the user object — no credentials, no tokens
      partialize: (s) => ({ user: s.user }),
      merge: (persisted, current) => {
        const persistedRecord = isRecord(persisted) ? persisted : {};
        return {
          ...current,
          user: normalizeCurrentUser(persistedRecord.user),
        };
      },
    },
  ),
);
