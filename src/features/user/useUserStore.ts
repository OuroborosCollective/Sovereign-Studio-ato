/**
 * useUserStore — Zustand-Store für den eingeloggten User.
 *
 * Hält den aktuellen Nutzer (Rolle, Credits, Session).
 * Session-only: kein persistierter Zustand — Capacitor-Preferences
 * werden bei Bedarf in einem separaten Auth-Layer genutzt.
 *
 * Issue #459 (User Account System) liefert den vollen Auth-Flow.
 * Dieses Modul stellt die minimale Basis für Issue #460 (Admin).
 */

import { create } from 'zustand';

// ── Typen ────────────────────────────────────────────────────────────────────

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
}

interface UserStore {
  user: CurrentUser | null;
  /** Nutzer setzen (nach Login / Session-Restore) */
  setUser: (user: CurrentUser) => void;
  /** Abmelden */
  clearUser: () => void;
  /** Credits lokal aktualisieren (Optimistic Update) */
  adjustCredits: (delta: number) => void;
}

// ── Store ────────────────────────────────────────────────────────────────────

export const useUserStore = create<UserStore>((set, get) => ({
  /**
   * Demo-Default: Admin-User damit das Admin-Panel direkt nutzbar ist.
   * Issue #459 ersetzt dies durch echte Auth-Session-Restore-Logik.
   */
  user: {
    id: 'demo-admin-001',
    email: 'admin@sovereign.local',
    displayName: 'Admin',
    role: 'admin',
    credits: 9999,
    subscriptionStatus: 'active',
    isBanned: false,
    createdAt: Date.now() - 86_400_000 * 30,
  },

  setUser: (user) => set({ user }),

  clearUser: () => set({ user: null }),

  adjustCredits: (delta) => {
    const { user } = get();
    if (!user) return;
    set({ user: { ...user, credits: Math.max(0, user.credits + delta) } });
  },
}));
