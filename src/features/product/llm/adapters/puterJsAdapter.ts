import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';
import { maskSecrets } from '../../../../shared/utils/crypto';

/**
 * Puter.js Opt-In Adapter
 *
 * Puter.js exposes GPT-4o-mini (and other models) for free via the user's
 * browser session without requiring an API key from the developer.
 * The user must be signed in to puter.com or the SDK must be loaded in the page.
 *
 * kind: 'opt-in' — skipped unless context.allowOptInRoutes is true.
 * Loaded via the globally-available `window.puter` object (injected by the Puter SDK).
 */

interface PuterAiChat {
  chat(
    prompt: string,
    testMode?: boolean,
    options?: { model?: string },
  ): Promise<{ message?: { content?: string }; toString?: () => string } | string>;
}

interface PuterWindow {
  puter?: {
    ai?: PuterAiChat;
  };
}

const PUTER_MODEL = 'gpt-4o-mini';
const PUTER_TIMEOUT_MS = 30_000;

async function callPuterJs(prompt: string): Promise<string> {
  const w = (typeof window !== 'undefined' ? window : {}) as PuterWindow;

  if (!w.puter?.ai) {
    throw new Error('Puter.js SDK not available in this environment. window.puter.ai is undefined.');
  }

  const timeoutPromise = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error('Puter.js request timed out')), PUTER_TIMEOUT_MS),
  );

  const chatPromise = w.puter.ai.chat(prompt, false, { model: PUTER_MODEL });

  const result = await Promise.race([chatPromise, timeoutPromise]);

  let text = '';
  if (typeof result === 'string') {
    text = result;
  } else if (result && typeof result === 'object') {
    text =
      (result as { message?: { content?: string } }).message?.content ??
      (typeof (result as { toString?: () => string }).toString === 'function'
        ? (result as { toString: () => string }).toString()
        : '');
  }

  if (!text.trim()) throw new Error('Puter.js returned empty content');
  return text;
}

export function createPuterJsAdapter(): LlmAdapter {
  return {
    id: 'puter-js-opt-in',
    label: 'Puter.js – GPT-4o-mini (browser opt-in)',
    kind: 'opt-in',
    priority: 10,
    enabled: true,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);

      try {
        const raw = await callPuterJs(prompt);
        const parsed = parseSovereignBrainJson(raw);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('puter-js-opt-in', context.mission, parsed);

        return { providerId: 'puter-js-opt-in', brain: parsed, raw };
      } catch (error) {
        throw new Error(
          `Puter.js opt-in provider failed: ${error instanceof Error ? maskSecrets(error.message) : 'Unknown error'}`,
        );
      }
    },
  };
}
