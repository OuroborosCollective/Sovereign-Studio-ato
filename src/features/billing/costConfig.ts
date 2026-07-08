/**
 * costConfig — Credit cost definitions for all LLM calls, tool executions
 * and API requests in Sovereign Studio.
 *
 * 1 Credit = €0,0001 (one tenth of a Euro-cent).
 * LLM costs are token-based (per 1 000 tokens).
 * Tool / API costs are flat per invocation.
 *
 * Issue #458
 *
 * NOTE: LLM model costs are loaded dynamically from backend /api/llm/routes
 * and merged with these local fallbacks.
 */

export interface CostEntry {
  id: string;
  label: string;
  type: 'llm_call' | 'tool_exec' | 'api_request';
  creditsPerUnit: number;
  unitDefinition: string;
}

// Backend API base (same as billingSlice)
const API_BASE: string =
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined) ||
  'https://sovereign-backend.arelorian.de';

export const EUR_PER_CREDIT = 0.0001 as const;

// Fallback LLM costs (used when backend is unreachable)
const FALLBACK_LLM_COSTS: CostEntry[] = [
  {
    id: 'gemini-2.0-flash',
    label: 'Gemini 2.0 Flash',
    type: 'llm_call',
    creditsPerUnit: 1,
    unitDefinition: '1.000 Tokens',
  },
  {
    id: 'gemini-2.5-pro',
    label: 'Gemini 2.5 Pro',
    type: 'llm_call',
    creditsPerUnit: 8,
    unitDefinition: '1.000 Tokens',
  },
  {
    id: 'gemini-2.5-flash',
    label: 'Gemini 2.5 Flash',
    type: 'llm_call',
    creditsPerUnit: 2,
    unitDefinition: '1.000 Tokens',
  },
];

// Tool/API costs (always local, not from backend)
const TOOL_COSTS: CostEntry[] = [
  {
    id: 'tool_vps_exec',
    label: 'VPS Befehl',
    type: 'tool_exec',
    creditsPerUnit: 5,
    unitDefinition: '1 Befehl',
  },
  {
    id: 'tool_github_pr',
    label: 'Draft PR erstellen',
    type: 'api_request',
    creditsPerUnit: 10,
    unitDefinition: '1 PR',
  },
  {
    id: 'tool_repo_load',
    label: 'Repo laden',
    type: 'api_request',
    creditsPerUnit: 3,
    unitDefinition: '1 Repo-Snapshot',
  },
];

// Cached LLM costs from backend
let cachedLlmCosts: CostEntry[] | null = null;
let cacheTime = 0;
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Load LLM model costs from backend /api/llm/routes.
 * Returns cached value if still fresh.
 */
export async function loadLlmCostsFromBackend(): Promise<CostEntry[]> {
  const now = Date.now();
  if (cachedLlmCosts && (now - cacheTime) < CACHE_TTL_MS) {
    return cachedLlmCosts;
  }

  try {
    const res = await fetch(`${API_BASE}/api/llm/routes`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json() as { routes?: { defaultModelId: string; label: string; creditsPerKTokens: number }[] };
    const routes = data.routes ?? [];

    cachedLlmCosts = routes.map((route) => ({
      id: route.defaultModelId,
      label: route.label,
      type: 'llm_call' as const,
      creditsPerUnit: route.creditsPerKTokens,
      unitDefinition: '1.000 Tokens',
    }));
    cacheTime = now;
    return cachedLlmCosts;
  } catch (error) {
    // Fallback to local costs on error
    console.warn('[costConfig] Failed to load LLM costs from backend, using fallbacks:', error);
    return FALLBACK_LLM_COSTS;
  }
}

/**
 * Get all cost entries (LLM + Tool costs).
 * For async LLM costs, use loadLlmCostsFromBackend() first.
 */
export function getToolCosts(): CostEntry[] {
  return TOOL_COSTS;
}

/**
 * Returns the combined cost config (LLM + Tool costs).
 * NOTE: LLM costs may need to be loaded asynchronously via loadLlmCostsFromBackend().
 */
export function getDefaultCostConfig(): CostEntry[] {
  return [...FALLBACK_LLM_COSTS, ...TOOL_COSTS];
}

// Export for direct access
export { FALLBACK_LLM_COSTS, TOOL_COSTS };

/** Legacy alias for backwards compatibility with tests */
export const COST_CONFIG: CostEntry[] = getDefaultCostConfig();

/**
 * Returns the credit cost for a given cost entry.
 *
 * For llm_call entries: cost = ceil(tokenCount / 1000) * creditsPerUnit
 * For tool_exec / api_request entries: flat creditsPerUnit regardless of tokens.
 * Returns 0 for unknown ids so callers can skip unknown entries safely.
 */
export function calculateCredits(costId: string, tokenCount = 0, llmCosts?: CostEntry[]): number {
  const config = llmCosts ?? getDefaultCostConfig();
  const entry = config.find((e) => e.id === costId);
  if (!entry) return 0;
  if (entry.type === 'llm_call') {
    return Math.ceil((tokenCount / 1000) * entry.creditsPerUnit);
  }
  return entry.creditsPerUnit;
}

/** Human-readable EUR representation of a credit amount (4 decimal places). */
export function creditsToEur(credits: number): string {
  return (credits * EUR_PER_CREDIT).toFixed(4);
}

/** Returns the CostEntry for the given id, or undefined. */
export function getCostEntry(costId: string, llmCosts?: CostEntry[]): CostEntry | undefined {
  const config = llmCosts ?? getDefaultCostConfig();
  return config.find((e) => e.id === costId);
}
