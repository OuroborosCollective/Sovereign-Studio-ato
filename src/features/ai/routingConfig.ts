/**
 * routingConfig — Static default LLM route definitions for Sovereign Studio.
 *
 * Admins can override these defaults via the Admin Panel (→ LlmRouteEditor).
 * The backend merges these defaults with DB overrides and serves them via
 * GET /api/llm/routes/:id (public) and GET /api/admin/llm/routes (admin).
 *
 * Issue #461
 */

export interface LlmRoute {
  id: string;
  label: string;
  description: string;
  defaultModelId: string;
  creditsPerKTokens: number;
  enabled: boolean;
  /** When true the user can supply their own API key and skip credit deduction. */
  userKeyOverride: boolean;
  maxTokensPerRequest: number;
}

export const DEFAULT_ROUTES: LlmRoute[] = [
  {
    id: 'chat_standard',
    label: 'Standard-Chat',
    description: 'Normaler Auftrag im Chat',
    defaultModelId: 'gemini-2.0-flash',
    creditsPerKTokens: 1,
    enabled: true,
    userKeyOverride: true,
    maxTokensPerRequest: 32_000,
  },
  {
    id: 'chat_pro',
    label: 'Pro-Chat',
    description: 'Komplexe Analyse und lange Kontexte',
    defaultModelId: 'gemini-2.5-pro',
    creditsPerKTokens: 8,
    enabled: true,
    userKeyOverride: true,
    maxTokensPerRequest: 128_000,
  },
  {
    id: 'repo_analysis',
    label: 'Repo-Analyse',
    description: 'Repository laden und bewerten',
    defaultModelId: 'gemini-2.5-flash',
    creditsPerKTokens: 2,
    enabled: true,
    userKeyOverride: false,
    maxTokensPerRequest: 64_000,
  },
  {
    id: 'draft_pr',
    label: 'Draft PR erstellen',
    description: 'Dateien generieren und PR öffnen',
    defaultModelId: 'gemini-2.5-pro',
    creditsPerKTokens: 8,
    enabled: true,
    userKeyOverride: false,
    maxTokensPerRequest: 128_000,
  },
  {
    id: 'vps_chat',
    label: 'VPS-Chat',
    description: 'Natürlichsprache → Shell-Befehl (VPS Connector)',
    defaultModelId: 'gemini-2.0-flash',
    creditsPerKTokens: 1,
    enabled: true,
    userKeyOverride: true,
    maxTokensPerRequest: 8_000,
  },
];

/** Lookup a default route by id. Returns undefined for unknown ids. */
export function getDefaultRoute(routeId: string): LlmRoute | undefined {
  return DEFAULT_ROUTES.find((r) => r.id === routeId);
}

/** Map from route id → cost entry id used for calculateCredits() calls. */
export const ROUTE_TO_COST_ID: Record<string, string> = {
  chat_standard: 'gemini-2.0-flash',
  chat_pro:      'gemini-2.5-pro',
  repo_analysis: 'gemini-2.5-flash',
  draft_pr:      'gemini-2.5-pro',
  vps_chat:      'gemini-2.0-flash',
};
