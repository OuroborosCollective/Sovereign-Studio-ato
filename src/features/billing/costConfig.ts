/**
 * costConfig — Credit cost definitions for all LLM calls, tool executions
 * and API requests in Sovereign Studio.
 *
 * 1 Credit = €0,0001 (one tenth of a Euro-cent).
 * LLM costs are token-based (per 1 000 tokens).
 * Tool / API costs are flat per invocation.
 *
 * Issue #458
 */

export interface CostEntry {
  id: string;
  label: string;
  type: 'llm_call' | 'tool_exec' | 'api_request';
  creditsPerUnit: number;
  unitDefinition: string;
}

export const EUR_PER_CREDIT = 0.0001 as const;

export const COST_CONFIG: CostEntry[] = [
  // LLM models — cost per 1 000 tokens (input + output combined)
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
  // Tool executions — flat per invocation
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

/**
 * Returns the credit cost for a given cost entry.
 *
 * For llm_call entries: cost = ceil(tokenCount / 1000) * creditsPerUnit
 * For tool_exec / api_request entries: flat creditsPerUnit regardless of tokens.
 * Returns 0 for unknown ids so callers can skip unknown entries safely.
 */
export function calculateCredits(costId: string, tokenCount = 0): number {
  const entry = COST_CONFIG.find((e) => e.id === costId);
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
export function getCostEntry(costId: string): CostEntry | undefined {
  return COST_CONFIG.find((e) => e.id === costId);
}
