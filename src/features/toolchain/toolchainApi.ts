/**
 * toolchainApi — Typed API client for Sovereign App Toolchain.
 *
 * Alle Calls gehen über das eigene Backend (HTTP-Only Cookie Auth).
 * Kein GitHub-Token in der APK — alles serverseitig.
 *
 * Guardrails (identisch Backend):
 *   - GitHub lesen: nur nach Login
 *   - Schreiben: niemals direkt; nur Draft PR mit confirm=true
 *   - Push auf main: nie
 *   - Audit-Log: automatisch server-seitig
 */

const API_BASE: string =
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined) ||
  'https://sovereign-backend.arelorian.de';

async function tcFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ToolchainTool {
  id: string;
  label: string;
  write: boolean;
  confirm_required?: boolean;
}

export interface ToolchainRules {
  auto_load: boolean;
  github_read: 'after_login' | 'never';
  auto_write: boolean;
  push_to_main: boolean;
  pr_mode: 'draft_only';
  confirm_required: boolean;
  audit_log: boolean;
}

export interface UserToolsResponse {
  tools: ToolchainTool[];
  allowed_repos: string[];
  rules: ToolchainRules;
}

export interface GithubFileResponse {
  sha: string;
  html_url: string;
  bytes: number;
  content: string;
  truncated?: boolean;
}

export interface GithubDirItem {
  name: string;
  type: 'file' | 'dir';
  path: string;
  size: number | null;
}

export interface PreviewPatchResponse {
  ok: boolean;
  write_action: false;
  base_sha: string;
  block_report: { index: number; delta_chars: number }[];
  diff: string;
  lines_before: number;
  lines_after: number;
}

export interface DraftPrResponse {
  created: boolean;
  reason?: string;
  preview_diff?: string;
  write_mode: string;
  pr_number?: number;
  pr_url?: string;
  branch?: string;
  base?: string;
  draft?: boolean;
  block_report?: { index: number; delta_chars: number }[];
  diff?: string;
}

export interface PatchBlock {
  search: string;
  replace: string;
}

export interface AuditEntry {
  id: string;
  admin_email: string;
  action: string;
  target_id: string;
  changes: Record<string, unknown>;
  ts: string;
}

export interface SandboxPlanResponse {
  goal: string;
  commands: string[];
  note: string;
  rules: { push_to_main: boolean; draft_pr: boolean; confirm: boolean };
}

export interface UniversalToolchainTool {
  name: string;
  description: string;
  write_action: boolean;
  requires_confirm?: boolean;
  execution_runtime?: string;
}

export interface UniversalToolchainManifest {
  name: string;
  version: string;
  runtime: 'embedded' | string;
  tools: UniversalToolchainTool[];
  policy: {
    autoLoad: boolean;
    pushToMain: boolean;
    draftPrOnly: boolean;
    confirmRequired: boolean;
    arbitraryShell: boolean;
    directProductionRunner: boolean;
    directGithubToken: boolean;
    auditEvidence: boolean;
  };
}

export interface UniversalToolchainDiagnosis {
  ok: boolean;
  runtime: string;
  version: string;
  evidenceHash: string;
  failureFamilies: Array<{
    code: string;
    title: string;
    severity: string;
    score: number;
    checks: string[];
  }>;
  nextLogicalFailures: Array<{
    fromFamily: string;
    prediction: string;
    checkNext: string;
  }>;
  policy: Record<string, unknown>;
}

// ── API functions ─────────────────────────────────────────────────────────────

export const toolchainApi = {
  /** Embedded universal manifest; safe to auto-load without a second service. */
  getUniversalManifest(): Promise<UniversalToolchainManifest> {
    return tcFetch('/api/toolchain/universal/manifest');
  },

  /** Read-only predictive diagnosis. Raw evidence is hashed and not reflected. */
  diagnoseRuntime(params: { mission?: string; evidence_text?: string }): Promise<{ ok: boolean; result: UniversalToolchainDiagnosis }> {
    return tcFetch('/api/toolchain/universal/invoke', {
      method: 'POST',
      body: JSON.stringify({ tool: 'runtime_failure_diagnose', args: params }),
    });
  },

  /** Auto-loads after login — lists available tools for the current user. */
  getUserTools(): Promise<UserToolsResponse> {
    return tcFetch('/api/toolchain/user-tools');
  },

  /** Read a file from an allowed GitHub repo. */
  readGithubFile(params: {
    owner: string;
    repo: string;
    path: string;
    ref?: string;
  }): Promise<GithubFileResponse> {
    return tcFetch('/api/toolchain/github/read-file', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /** List directory contents from an allowed GitHub repo. */
  listDirectory(params: {
    owner: string;
    repo: string;
    path?: string;
    ref?: string;
  }): Promise<{ items: GithubDirItem[] }> {
    return tcFetch('/api/toolchain/github/list-directory', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /** List branches of an allowed GitHub repo. */
  listBranches(params: {
    owner: string;
    repo: string;
  }): Promise<{ branches: { name: string }[] }> {
    return tcFetch('/api/toolchain/github/list-branches', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /** Search code in an allowed GitHub repo. */
  searchCode(params: {
    owner: string;
    repo: string;
    q: string;
  }): Promise<{ items: { path: string; html_url: string }[]; total: number }> {
    return tcFetch('/api/toolchain/github/search-code', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /**
   * Preview SEARCH/REPLACE blocks against a GitHub file.
   * Read-only — shows diff before any write.
   */
  previewPatch(params: {
    owner: string;
    repo: string;
    path: string;
    blocks: PatchBlock[];
    ref?: string;
  }): Promise<PreviewPatchResponse> {
    return tcFetch('/api/toolchain/preview-patch', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /**
   * Create a Draft PR with SEARCH/REPLACE blocks.
   * confirm=false → returns preview only, no write.
   * confirm=true  → creates Draft PR, never pushes to main directly.
   */
  createDraftPr(params: {
    owner: string;
    repo: string;
    path: string;
    message: string;
    blocks: PatchBlock[];
    confirm: boolean;
    branch_name?: string;
    title?: string;
    body?: string;
    base_branch?: string;
  }): Promise<DraftPrResponse> {
    return tcFetch('/api/toolchain/create-draft-pr', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /**
   * Send blocks to the external Sovereign patch worker.
   * confirm=true required — admin only.
   */
  applyPatchWorker(params: {
    owner: string;
    repo: string;
    path: string;
    message: string;
    blocks: PatchBlock[];
    confirm: boolean;
    worker_url?: string;
  }): Promise<{ sent: boolean; status?: number; response?: unknown; reason?: string }> {
    return tcFetch('/api/toolchain/apply-patch-worker', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /**
   * Plan Playwright/verify/doctor commands for a given goal.
   * Read-only — returns command suggestions for the sandbox.
   */
  sandboxPlan(params: { goal: string }): Promise<SandboxPlanResponse> {
    return tcFetch('/api/toolchain/sandbox-plan', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /** Get toolchain audit log (own entries for user, all for admin). */
  getAuditLog(): Promise<{ entries: AuditEntry[] }> {
    return tcFetch('/api/toolchain/audit-log');
  },
};
