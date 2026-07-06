/**
 * OpenHands Tool — Launcher-Tool-Eintrag für User-spezifische AI-Coding-Jobs.
 *
 * Integriert mit OpenHands Enterprise via Backend API.
 * Issue #529
 */

import { Bot } from 'lucide-react';
import type { LauncherEntry } from '../../launcherRegistry';
import { OpenHandsTool } from './OpenHandsTool';

export const openHandsToolEntry: LauncherEntry = {
  id:          'openhands-jobs',
  label:       'OpenHands',
  description: 'AI-Coding Jobs für Repositories',
  icon:        Bot,
  color:       'bg-indigo-600',
  component:   OpenHandsTool,
  badge:       undefined,
  disabled:    false,
};
