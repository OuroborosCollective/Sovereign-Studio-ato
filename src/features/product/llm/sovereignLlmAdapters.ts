import type { LlmAdapter } from './llmAdapter';
import { createPrimaryBridgeAdapter } from './adapters/primaryBridgeAdapter';
import { createMlvocaAdapter } from './adapters/mlvocaAdapter';
import { createPollinationsAdapter } from './adapters/pollinationsAdapter';
import { createGroqAdapter } from './adapters/groqAdapter';
import { createHuggingFaceAdapter } from './adapters/huggingfaceAdapter';
import { createTogetherAdapter } from './adapters/togetherAdapter';
import { createOpenRouterAdapter } from './adapters/openrouterAdapter';
import { createGeminiAdapter } from './adapters/geminiAdapter';
import { createLocalSafeAdapter } from './adapters/localSafeAdapter';
import { resolvePrimaryBridgeConfig } from './primaryBridgeConfig';
import type { Card, ProjectSettings } from '../types';

export interface SovereignLlmAdapterOptions {
  primaryBridgeProxyUrl?: string;
  primaryBridgeModel?: string;
  pollinationsApiKey?: string;
  groqApiKey?: string;
  huggingfaceApiKey?: string;
  togetherApiKey?: string;
  openrouterApiKey?: string;
  geminiApiKey?: string;
  cards: Card[];
  settings: ProjectSettings;
}

export function buildSovereignLlmAdapters(options: SovereignLlmAdapterOptions): LlmAdapter[] {
  const bridgeConfig = resolvePrimaryBridgeConfig({
    proxyUrl: options.primaryBridgeProxyUrl,
    model: options.primaryBridgeModel,
  });

  const adapters: LlmAdapter[] = [];

  if (bridgeConfig.ready) {
    adapters.push(createPrimaryBridgeAdapter({
      proxyUrl: bridgeConfig.proxyUrl,
      model: bridgeConfig.model,
    }));
  }

  adapters.push(
    createMlvocaAdapter(),
    createPollinationsAdapter(options.pollinationsApiKey),
  );

  if (options.groqApiKey) adapters.push(createGroqAdapter(options.groqApiKey));
  if (options.huggingfaceApiKey) adapters.push(createHuggingFaceAdapter(options.huggingfaceApiKey));
  if (options.togetherApiKey) adapters.push(createTogetherAdapter(options.togetherApiKey));
  if (options.openrouterApiKey) adapters.push(createOpenRouterAdapter(options.openrouterApiKey));
  if (options.geminiApiKey) adapters.push(createGeminiAdapter(options.geminiApiKey));

  adapters.push(createLocalSafeAdapter({
    cards: options.cards,
    settings: options.settings,
  }));

  return adapters;
}
