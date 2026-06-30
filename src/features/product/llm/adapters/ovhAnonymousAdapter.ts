import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';
import { maskSecrets } from '../../../../shared/utils/crypto';

const OVH_CODE_URL = 'https://deepseek-r1.endpoints.kepler.ai.cloud.ovh.net/api/openai_compat/v1/chat/completions';
const OVH_CODE_MODEL = 'DeepSeek-R1';

const OVH_FIXED_URL = 'https://llama-3-3-70b-instruct.endpoints.kepler.ai.cloud.ovh.net/api/openai_compat/v1/chat/completions';
const OVH_FIXED_MODEL = 'Llama-3.3-70B-Instruct';

const OVH_TIMEOUT_MS = 15_000;

async function callOvhEndpoint(
  url: string,
  model: string,
  prompt: string,
  providerId: 'ovh-anonymous-code-chat' | 'ovh-anonymous-fixed-model',
): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), OVH_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.2,
        max_tokens: 4096,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new Error(maskSecrets(`OVH ${providerId} HTTP ${response.status}: ${body.slice(0, 300)}`));
    }

    const data = await response.json();
    const text: string = data?.choices?.[0]?.message?.content ?? '';
    if (!text.trim()) throw new Error(`OVH ${providerId} returned empty content`);
    return text;
  } finally {
    clearTimeout(timer);
  }
}

export function createOvhAnonymousCodeChatAdapter(): LlmAdapter {
  return {
    id: 'ovh-anonymous-code-chat',
    label: 'OVH AI Endpoints – DeepSeek-R1 (anonymous)',
    kind: 'no-key',
    priority: 7,
    enabled: true,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);

      try {
        const raw = await callOvhEndpoint(OVH_CODE_URL, OVH_CODE_MODEL, prompt, 'ovh-anonymous-code-chat');
        const parsed = parseSovereignBrainJson(raw);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('ovh-anonymous-code-chat', context.mission, parsed);

        return { providerId: 'ovh-anonymous-code-chat', brain: parsed, raw };
      } catch (error) {
        throw new Error(
          `OVH anonymous code-chat failed: ${error instanceof Error ? maskSecrets(error.message) : 'Unknown error'}`,
        );
      }
    },
  };
}

export function createOvhAnonymousFixedModelAdapter(): LlmAdapter {
  return {
    id: 'ovh-anonymous-fixed-model',
    label: 'OVH AI Endpoints – Llama-3.3-70B (anonymous)',
    kind: 'no-key',
    priority: 8,
    enabled: true,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);

      try {
        const raw = await callOvhEndpoint(OVH_FIXED_URL, OVH_FIXED_MODEL, prompt, 'ovh-anonymous-fixed-model');
        const parsed = parseSovereignBrainJson(raw);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('ovh-anonymous-fixed-model', context.mission, parsed);

        return { providerId: 'ovh-anonymous-fixed-model', brain: parsed, raw };
      } catch (error) {
        throw new Error(
          `OVH anonymous fixed-model failed: ${error instanceof Error ? maskSecrets(error.message) : 'Unknown error'}`,
        );
      }
    },
  };
}
