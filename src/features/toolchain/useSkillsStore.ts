/**
 * useSkillsStore — Zustand-Store für Sovereign App Skills.
 *
 * Skills können aus beliebigen Repos gescannt und adaptiert werden.
 * Aktive Skills sind ausdrücklich per /skill-slug auswählbar.
 * Kein Skill-Prompt wird ungefragt in andere Aufträge injiziert.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { skillsApi, type UserSkill, type FoundSkill, type ScanResult } from './skillsApi';

interface SkillsState {
  skills: UserSkill[];
  loaded: boolean;
  loading: boolean;
  error: string | null;

  // Scan state
  scanResult: ScanResult | null;
  scanning: boolean;
  scanError: string | null;

  // Actions
  loadSkills: () => Promise<void>;
  scanRepo: (owner: string, repo: string) => Promise<ScanResult>;
  adaptAndInstall: (
    owner: string,
    repo: string,
    found: FoundSkill,
    onProgress?: (msg: string) => void,
  ) => Promise<UserSkill>;
  toggleSkill: (id: string, is_active: boolean) => Promise<void>;
  deleteSkill: (id: string) => Promise<void>;
  reset: () => void;

  // Metadata-only catalog. Workflow prompts are used only after explicit /skill invocation.
  getActiveSkillContext: () => string;

  // For /command palette — active skills as slash commands with persisted provenance.
  getSkillSlashCommands: () => {
    cmd: string;
    label: string;
    description: string;
    adapted_prompt: string;
    skill_id: string;
    source_sha?: string;
    content_sha256?: string;
  }[];
}

export const useSkillsStore = create<SkillsState>()(
  persist(
    (set, get) => ({
      skills: [],
      loaded: false,
      loading: false,
      error: null,
      scanResult: null,
      scanning: false,
      scanError: null,

      loadSkills: async () => {
        if (get().loading) return;
        set({ loading: true, error: null });
        try {
          const data = await skillsApi.listSkills();
          set({ skills: data.skills, loaded: true, loading: false });
        } catch (e) {
          set({ loading: false, error: (e as Error).message });
        }
      },

      scanRepo: async (owner, repo) => {
        set({ scanning: true, scanError: null, scanResult: null });
        try {
          const result = await skillsApi.scanRepo({ owner, repo });
          set({ scanning: false, scanResult: result });
          return result;
        } catch (e) {
          set({ scanning: false, scanError: (e as Error).message });
          throw e;
        }
      },

      adaptAndInstall: async (owner, repo, found, onProgress) => {
        onProgress?.(`Lese ${found.path}…`);
        const readData = await skillsApi.readSkillFile({ owner, repo, path: found.path });

        onProgress?.(`Adaptiere Skill für Sovereign…`);
        const adapted = await skillsApi.adaptSkill({
          owner,
          repo,
          path: found.path,
          raw_content: readData.content,
          framework: readData.framework,
          source_sha: readData.sha,
        });

        onProgress?.(`Installiere ${adapted.name}…`);
        const installed = await skillsApi.installSkill({
          name: adapted.name,
          slug: adapted.slug,
          description: adapted.description,
          source_repo: `${owner}/${repo}`,
          source_path: found.path,
          framework: adapted.framework,
          adapted_prompt: adapted.adapted_prompt,
          source_sha: adapted.source_sha,
          content_sha256: adapted.content_sha256,
        });

        const newSkill: UserSkill = installed.skill;

        set((s) => ({ skills: [...s.skills.filter((x) => x.slug !== newSkill.slug), newSkill] }));
        return newSkill;
      },

      toggleSkill: async (id, is_active) => {
        await skillsApi.toggleSkill(id, is_active);
        set((s) => ({
          skills: s.skills.map((sk) => (sk.id === id ? { ...sk, is_active } : sk)),
        }));
      },

      deleteSkill: async (id) => {
        await skillsApi.deleteSkill(id);
        set((s) => ({ skills: s.skills.filter((sk) => sk.id !== id) }));
      },

      reset: () =>
        set({ skills: [], loaded: false, loading: false, error: null, scanResult: null }),

      getActiveSkillContext: () => {
        const active = get().skills.filter((s) => s.is_active);
        if (active.length === 0) return '';
        return [
          `── Explizit auswählbare Skills (${active.length}) ──`,
          ...active.map((s) => `/${s.slug} — ${s.description}`),
          'Skill-Workflows werden nur bei ausdrücklichem Slash-Aufruf in einen Auftrag übernommen.',
        ].join('\n');
      },

      getSkillSlashCommands: () =>
        get()
          .skills.filter((s) => s.is_active)
          .map((s) => ({
            cmd: `/${s.slug}`,
            label: s.name,
            description: s.description,
            adapted_prompt: s.adapted_prompt,
            skill_id: s.id,
            source_sha: s.source_sha,
            content_sha256: s.content_sha256,
          })),
    }),
    { name: 'sovereign-skills-store', partialize: (s) => ({ skills: s.skills }) },
  ),
);
