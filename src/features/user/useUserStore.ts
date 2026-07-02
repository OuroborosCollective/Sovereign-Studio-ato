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
}

const API_BASE: string =
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined) ||
  'https://sovereign-backend.arelorian.de';

async function authFetch(path: string, options?: RequestInit) {
  return fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
  });
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
          const user = await res.json() as CurrentUser;
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
          const user = await res.json() as CurrentUser;
          set({ user, isLoading: false, error: null });
        } catch {
          set({ isLoading: false, error: 'Verbindungsfehler' });
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
          const user = await res.json() as CurrentUser;
          set({ user, isLoading: false, error: null });
        } catch {
          set({ isLoading: false, error: 'Verbindungsfehler' });
        }
      },

      logout: async () => {
        await authFetch('/api/auth/logout', { method: 'POST' }).catch(() => null);
        set({ user: null, error: null });
      },

      refreshUser: async () => {
        try {
          const res = await authFetch('/api/auth/me');
          if (res.ok) {
            const user = await res.json() as CurrentUser;
            set({ user });
          } else {
            set({ user: null });
          }
        } catch {
          // network error — keep existing user state
        }
      },
    }),
    {
      name: 'sovereign-user',
      // Only persist the user object — no credentials, no tokens
      partialize: (s) => ({ user: s.user }),
    },
  ),
);
