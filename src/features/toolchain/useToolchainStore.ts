/**
 * useToolchainStore — Zustand-Store für die Sovereign App Toolchain.
 *
 * Lädt automatisch nach User-Login via loadTools().
 * Die KI im BuilderContainer kann über getToolContext() den
 * aktuellen Tool-Status als System-Prompt-Kontext abrufen.
 */

import { create } from 'zustand';
import {
  toolchainApi,
  type ToolchainTool,
  type ToolchainRules,
  type PatchBlock,
  type PreviewPatchResponse,
  type DraftPrResponse,
  type UniversalToolchainDiagnosis,
  type UniversalToolchainManifest,
} from './toolchainApi';

interface ToolchainState {
  tools: ToolchainTool[];
  allowedRepos: string[];
  rules: ToolchainRules | null;
  universalManifest: UniversalToolchainManifest | null;
  loaded: boolean;
  loading: boolean;
  error: string | null;

  // Actions
  loadTools: () => Promise<void>;
  reset: () => void;

  // Repo-Operationen (read-only)
  readFile: (owner: string, repo: string, path: string, ref?: string) => Promise<{ content: string; sha: string; html_url: string }>;
  listDir: (owner: string, repo: string, path?: string) => Promise<{ name: string; type: string; path: string }[]>;
  searchCode: (owner: string, repo: string, q: string) => Promise<{ path: string; html_url: string }[]>;

  // Patch-Workflow (read + write mit confirm)
  previewPatch: (owner: string, repo: string, path: string, blocks: PatchBlock[]) => Promise<PreviewPatchResponse>;
  createDraftPr: (params: {
    owner: string; repo: string; path: string;
    message: string; blocks: PatchBlock[]; confirm: boolean;
    title?: string; branch_name?: string;
  }) => Promise<DraftPrResponse>;

  // Sandbox-Plan (read-only)
  sandboxPlan: (goal: string) => Promise<string[]>;
  diagnoseRuntime: (mission: string, evidenceText?: string) => Promise<UniversalToolchainDiagnosis>;

  // Für KI-Kontext
  getToolContext: () => string;
}

const DEFAULT_RULES: ToolchainRules = {
  auto_load: true,
  github_read: 'after_login',
  auto_write: false,
  push_to_main: false,
  pr_mode: 'draft_only',
  confirm_required: true,
  audit_log: true,
};

export const useToolchainStore = create<ToolchainState>()((set, get) => ({
  tools: [],
  allowedRepos: [],
  rules: null,
  universalManifest: null,
  loaded: false,
  loading: false,
  error: null,

  loadTools: async () => {
    if (get().loading) return;
    set({ loading: true, error: null });
    try {
      const [data, universalManifest] = await Promise.all([
        toolchainApi.getUserTools(),
        toolchainApi.getUniversalManifest(),
      ]);
      set({
        tools: data.tools,
        allowedRepos: data.allowed_repos,
        rules: data.rules,
        universalManifest,
        loaded: true,
        loading: false,
        error: null,
      });
    } catch (e) {
      set({ loading: false, error: (e as Error).message, loaded: false });
    }
  },

  reset: () => set({ tools: [], allowedRepos: [], rules: null, universalManifest: null, loaded: false, loading: false, error: null }),

  readFile: async (owner, repo, path, ref) => {
    const data = await toolchainApi.readGithubFile({ owner, repo, path, ref });
    return { content: data.content, sha: data.sha, html_url: data.html_url };
  },

  listDir: async (owner, repo, path) => {
    const data = await toolchainApi.listDirectory({ owner, repo, path });
    return data.items.map(i => ({ name: i.name, type: i.type, path: i.path }));
  },

  searchCode: async (owner, repo, q) => {
    const data = await toolchainApi.searchCode({ owner, repo, q });
    return data.items;
  },

  previewPatch: async (owner, repo, path, blocks) => {
    return toolchainApi.previewPatch({ owner, repo, path, blocks });
  },

  createDraftPr: async (params) => {
    return toolchainApi.createDraftPr(params);
  },

  sandboxPlan: async (goal) => {
    const data = await toolchainApi.sandboxPlan({ goal });
    return data.commands;
  },

  diagnoseRuntime: async (mission, evidenceText = '') => {
    const data = await toolchainApi.diagnoseRuntime({ mission, evidence_text: evidenceText });
    return data.result;
  },

  getToolContext: () => {
    const { tools, allowedRepos, rules, universalManifest, loaded } = get();
    if (!loaded) return '';
    const readTools  = tools.filter(t => !t.write).map(t => `  • ${t.label} (${t.id})`).join('\n');
    const writeTools = tools.filter(t =>  t.write).map(t => `  • ${t.label} [confirm=true erforderlich]`).join('\n');
    return [
      '── Sovereign App Toolchain ──',
      `Erlaubte Repos: ${allowedRepos.join(', ') || 'keine'}`,
      `Lese-Tools:\n${readTools || '  (keine)'}`,
      writeTools ? `Schreib-Tools (nur mit User-Bestätigung):\n${writeTools}` : '',
      universalManifest ? [
        `Eingebettete Universal Toolchain: ${universalManifest.version} (${universalManifest.runtime})`,
        `Predictive Tools: ${universalManifest.tools.map(tool => tool.name).join(', ')}`,
        'Predictive Übergabe: Fehlerfamilie erkennen, genau vier logisch benachbarte Runtime-Risiken prüfen, danach bestehende Sovereign-Agent-Evidence-Gates verwenden.',
        `Arbitrary Shell aus Chat: ${universalManifest.policy.arbitraryShell ? 'erlaubt' : 'gesperrt'}`,
        `Direkter Production Runner: ${universalManifest.policy.directProductionRunner ? 'erlaubt' : 'gesperrt'}`,
      ].join('\n') : '',
      rules ? [
        'Guardrails:',
        `  • GitHub lesen: ${rules.github_read === 'after_login' ? 'Nur nach Login' : 'Nie'}`,
        `  • Auto-Schreiben: ${rules.auto_write ? 'Ja' : 'Nein'}`,
        `  • Push auf main: ${rules.push_to_main ? 'Ja' : 'NIEMALS'}`,
        `  • PR-Modus: ${rules.pr_mode} (Entwurf)`,
        `  • Bestätigung: ${rules.confirm_required ? 'Pflicht' : 'Optional'}`,
        `  • Audit-Log: ${rules.audit_log ? 'Aktiv' : 'Inaktiv'}`,
      ].join('\n') : '',
    ].filter(Boolean).join('\n');
  },
}));
