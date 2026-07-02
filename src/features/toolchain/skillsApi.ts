/**
 * skillsApi — Typed API client for Sovereign App Toolchain Skills.
 *
 * Skills können aus beliebigen Repos gescannt, adaptiert und
 * als /command-Tools im Chat genutzt werden.
 */

const API_BASE: string =
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined) ||
  'https://sovereign-backend.arelorian.de';

async function skillFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface FoundSkill {
  path: string;
  name: string;
  framework: string;
  preview: string;
  size: number;
}

export interface UserSkill {
  id: string;
  name: string;
  slug: string;
  description: string;
  source_repo: string;
  source_path: string;
  framework: string;
  adapted_prompt: string;
  is_active: boolean;
  created_at: string;
}

export interface ScanResult {
  owner: string;
  repo: string;
  found: FoundSkill[];
  total: number;
  frameworks_detected: string[];
}

export interface AdaptResult {
  name: string;
  slug: string;
  description: string;
  adapted_prompt: string;
  framework: string;
}

// ── API functions ─────────────────────────────────────────────────────────────

export const skillsApi = {
  /** Scan a GitHub repo for usable skills — any framework/structure. */
  scanRepo(params: { owner: string; repo: string; ref?: string }): Promise<ScanResult> {
    return skillFetch('/api/toolchain/skills/scan', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /** Read a specific skill file from GitHub. */
  readSkillFile(params: { owner: string; repo: string; path: string }): Promise<{ content: string; framework: string }> {
    return skillFetch('/api/toolchain/skills/read', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /** Adapt a raw skill to the Sovereign system (AI-powered). */
  adaptSkill(params: {
    owner: string;
    repo: string;
    path: string;
    raw_content: string;
    framework: string;
  }): Promise<AdaptResult> {
    return skillFetch('/api/toolchain/skills/adapt', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /** Install an adapted skill into the user's library. */
  installSkill(params: {
    name: string;
    slug: string;
    description: string;
    source_repo: string;
    source_path: string;
    framework: string;
    adapted_prompt: string;
  }): Promise<{ id: string; slug: string }> {
    return skillFetch('/api/toolchain/skills/install', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /** List all installed skills for the current user. */
  listSkills(): Promise<{ skills: UserSkill[] }> {
    return skillFetch('/api/toolchain/skills/list');
  },

  /** Toggle a skill on/off. */
  toggleSkill(id: string, is_active: boolean): Promise<{ ok: boolean }> {
    return skillFetch(`/api/toolchain/skills/${id}/toggle`, {
      method: 'POST',
      body: JSON.stringify({ is_active }),
    });
  },

  /** Delete a skill from the library. */
  deleteSkill(id: string): Promise<{ ok: boolean }> {
    return skillFetch(`/api/toolchain/skills/${id}`, { method: 'DELETE' });
  },
};
