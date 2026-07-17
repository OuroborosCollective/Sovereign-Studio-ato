import type { LlmAdapter } from './llmAdapter';
import { createPrimaryBridgeAdapter } from './adapters/primaryBridgeAdapter';
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
      proxyUrl: bridgeConfig.backendBaseUrl,
      model: bridgeConfig.model,
    }));
  }

  // The client has exactly one online model path. Provider credentials,
  // routing, fallback and billing are owned by the backend and private LiteLLM.
  adapters.push(createLocalSafeAdapter({
    cards: options.cards,
    settings: options.settings,
  }));

  return adapters;
}
