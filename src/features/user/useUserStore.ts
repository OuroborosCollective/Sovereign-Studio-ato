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

function toStringValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function toNumberValue(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function toUserRole(value: unknown): UserRole {
  return value === 'admin' || value === 'superadmin' || value === 'user'
    ? value
    : 'user';
}

function toSubscriptionStatus(value: unknown): SubscriptionStatus {
  return value === 'active' || value === 'canceled' || value === 'past_due' ||
    value === 'trialing' || value === 'free'
    ? value
    : 'free';
}

function normalizeCurrentUser(input: unknown): CurrentUser | null {
  if (!input || typeof input !== 'object') return null;
  const raw = input as Partial<CurrentUser>;

  return {
    id: toStringValue(raw.id),
    email: toStringValue(raw.email),
    displayName: toStringValue(raw.displayName),
    role: toUserRole(raw.role),
    credits: Math.max(0, toNumberValue(raw.credits)),
    subscriptionStatus: toSubscriptionStatus(raw.subscriptionStatus),
    isBanned: Boolean(raw.isBanned),
    createdAt: toNumberValue(raw.createdAt),
    avatarUrl: raw.avatarUrl === undefined ? undefined : toStringValue(raw.avatarUrl),
    googleId: raw.googleId === undefined ? undefined : toStringValue(raw.googleId),
  };
}

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

      setUser: (user) => set({ user: normalizeCurrentUser(user) }),
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
          const user = normalizeCurrentUser(await res.json());
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
            const user = normalizeCurrentUser(await res.json());
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
      partialize: (s) => ({ user: normalizeCurrentUser(s.user) }),
      merge: (persisted, current) => ({
        ...current,
        ...(persisted as Partial<UserStore>),
        user: normalizeCurrentUser((persisted as Partial<UserStore> | undefined)?.user),
      }),
    },
  ),
);
