/**
 * useUserStore — Zustand-Store für den eingeloggten User.
 *
 * Defaults to null — no user until auth session is restored.
 * Issue #459 (User Account System) provides the real auth/session-restore.
 * Issue #460 (Admin Backend) reads the role to gate the AdminPanel.
 */

import { create } from 'zustand';

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
  setUser: (user: CurrentUser) => void;
  clearUser: () => void;
  adjustCredits: (delta: number) => void;
}

export const useUserStore = create<UserStore>((set, get) => ({
  // No default user — real session restore happens in Issue #459.
  user: null,

  setUser: (user) => set({ user }),
  clearUser: () => set({ user: null }),

  adjustCredits: (delta) => {
    const { user } = get();
    if (!user) return;
    set({ user: { ...user, credits: Math.max(0, user.credits + delta) } });
  },
}));
