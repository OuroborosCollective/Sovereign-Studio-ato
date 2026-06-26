import { assertSovereignBrainResult, parseSovereignBrainJson } from '../../brain/sovereignBrainContract';
import { assertPushableBrain } from '../llmRuntimeChecks';
import type { LlmAdapter, LlmAdapterContext, LlmAdapterResult } from '../llmAdapter';
import { buildSovereignLlmPrompt } from '../llmAdapter';
import { normalizePrimaryBridgeUrl, resolvePrimaryBridgeConfig } from '../primaryBridgeConfig';
import { maskSecrets } from '../../../../shared/utils/crypto';

export interface PrimaryBridgeAdapterOptions {
  proxyUrl?: string;
  model?: string;
  proxyKey?: string;
}

type ChatCompletionResponse = {
  choices?: Array<{ message?: { content?: string } }>;
  output_text?: string;
  response?: string;
  error?: unknown;
};

function providerError(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (typeof error === 'string' && error.trim()) return error;
  if (error && typeof error === 'object') {
    const record = error as Record<string, unknown>;
    const status = record.status ?? record.statusCode;
    const message = record.message ?? record.error ?? record.statusText;
    return [status ? `status=${String(status)}` : '', message ? String(message) : ''].filter(Boolean).join(' ') || JSON.stringify(record).slice(0, 500);
  }
  return 'Unknown error';
}

function extractText(payload: ChatCompletionResponse): string {
  const choiceText = payload.choices?.[0]?.message?.content;
  if (choiceText?.trim()) return choiceText;
  if (payload.output_text?.trim()) return payload.output_text;
  if (payload.response?.trim()) return payload.response;
  throw new Error(`Primary bridge returned no assistant text: ${JSON.stringify(payload).slice(0, 500)}`);
}

async function readBridgeResponse(response: Response): Promise<ChatCompletionResponse> {
  const text = await response.text();
  let payload: ChatCompletionResponse;
  try {
    payload = text ? JSON.parse(text) as ChatCompletionResponse : {};
  } catch {
    payload = { response: text };
  }

  if (!response.ok) {
    const message = typeof payload.error === 'string'
      ? payload.error
      : payload.error
        ? JSON.stringify(payload.error)
        : text || response.statusText || `HTTP ${response.status}`;
    throw { provider: 'primary-llm-bridge', status: response.status, error: maskSecrets(message), isRetryable: response.status === 429 || response.status >= 500 };
  }

  return payload;
}

export function createPrimaryBridgeAdapter(options: PrimaryBridgeAdapterOptions = {}): LlmAdapter {
  const config = resolvePrimaryBridgeConfig({ proxyUrl: options.proxyUrl, model: options.model, proxyKey: options.proxyKey });

  return {
    id: 'optional-user-keys',
    label: 'Hosted primary LLM bridge',
    kind: 'user-key',
    priority: -10,
    enabled: config.ready,
    async run(context: LlmAdapterContext): Promise<LlmAdapterResult> {
      const prompt = buildSovereignLlmPrompt(context);
      const proxyUrl = normalizePrimaryBridgeUrl(config.proxyUrl);

      try {
        const response = await fetch(proxyUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Sovereign-Client': 'android-webview',
            ...(config.proxyKey ? { 'X-API-Key': config.proxyKey } : {}),
          },
          body: JSON.stringify({
            model: config.model,
            messages: [{ role: 'user', content: prompt }],
            temperature: 0.2,
            max_tokens: 4096,
            reasoning_format: 'parsed',
          }),
          signal: context.signal,
        });

        const payload = await readBridgeResponse(response);
        const raw = extractText(payload);
        const parsed = parseSovereignBrainJson(raw);
        assertSovereignBrainResult(parsed);
        assertPushableBrain('optional-user-keys', context.mission, parsed);

        return { providerId: 'optional-user-keys', brain: parsed, raw };
      } catch (error) {
        throw new Error(`Primary bridge provider failed: ${maskSecrets(providerError(error))}`);
      }
    },
  };
}
