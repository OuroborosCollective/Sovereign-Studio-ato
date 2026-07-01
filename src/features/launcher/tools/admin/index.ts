/**
 * Admin Tool — Launcher-Tool-Eintrag für das Admin-Panel.
 *
 * Nur sichtbar/startbar wenn AdminGate die Rolle prüft.
 * Issue #460
 */

import { Settings } from 'lucide-react';
import type { LauncherEntry } from '../../launcherRegistry';
import { AdminPanel } from '../../../admin/AdminPanel';

export const adminToolEntry: LauncherEntry = {
  id:          'sovereign-admin',
  label:       'Admin',
  description: 'User, Billing & Routing verwalten',
  icon:        Settings,
  color:       'bg-rose-600',
  component:   AdminPanel,
  badge:       undefined,
  disabled:    false,
};
