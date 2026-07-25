/**
 * Canonical direct LLM intent boundary.
 *
 * Productive requests are routed by the authenticated Sovereign Backend to
 * direct OpenRouter paid routes or direct FreeLLM free routes. LiteLLM is not
 * part of the productive architecture; the legacy module path remains only as
 * a temporary compatibility surface for older imports.
 */
export {
  fetchSovereignDirectLlmInterpretation,
  SOVEREIGN_DIRECT_LLM_CHAT,
  SOVEREIGN_DIRECT_LLM_ROUTES,
  SOVEREIGN_INTENT_TIMEOUT_MS,
} from './sovereignLiteLlmIntentRuntime';
export type { SovereignDirectLlmIntentRequest } from './sovereignLiteLlmIntentRuntime';
