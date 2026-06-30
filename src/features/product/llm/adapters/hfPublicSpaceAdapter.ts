import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';
import { maskSecrets } from '../../../../shared/utils/crypto';

/**
 * HuggingFace Serverless Inference API – no API key required for rate-limited access.
 * Endpoint: https://api-inference.huggingface.co/models/{model}/v1/chat/completions
 * Falls back through a curated list of models; tries each in order until one responds.
 */

const HF_BASE = 'https://api-inference.huggingface.co/models';
const HF_TIMEOUT_MS = 20_000;

const CURATED_MODELS = [
  'Qwen/Qwen2.5-7B-Instruct',
  'microsoft/Phi-3.5-mini-instruct',
  'HuggingFaceH4/zephyr-7b-beta',
];

async function callHfPublicInference(model: string, prompt: string): Promise<string> {
  const url = `${HF_BASE}/${model}/v1/chat/completions`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), HF_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.2,
        max_tokens: 4096,
        stream: false,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new Error(`HF ${model} HTTP ${response.status}: ${body.slice(0, 200)}`);
    }

    const data = await response.json();

    const text: string =
      data?.choices?.[0]?.message?.content ??
      (Array.isArray(data) ? data[0]?.generated_text : data?.generated_text) ??
      '';

    if (!text.trim()) throw new Error(`HF public space model ${model} returned empty content`);
    return text;
  } finally {
    clearTimeout(timer);
  }
}

export function createHfPublicSpaceAdapter(): LlmAdapter {
  return {
    id: 'hf-curated-public-space',
    label: 'HuggingFace Serverless Inference (keyless)',
    kind: 'no-key',
    priority: 9,
    enabled: true,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);
      const errors: string[] = [];

      for (const model of CURATED_MODELS) {
        try {
          const raw = await callHfPublicInference(model, prompt);
          const parsed = parseSovereignBrainJson(raw);
          assertSovereignBrainResult(parsed);
          assertPushableBrain('hf-curated-public-space', context.mission, parsed);

          return { providerId: 'hf-curated-public-space', brain: parsed, raw };
        } catch (err) {
          errors.push(`${model}: ${err instanceof Error ? maskSecrets(err.message) : 'Unknown error'}`);
        }
      }

      throw new Error(`HF curated public space exhausted all models: ${errors.join(' | ')}`);
    },
  };
}
