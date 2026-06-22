import type { LlmAdapter } from './llmAdapter';
import { createMlvocaAdapter } from './adapters/mlvocaAdapter';
import { createPollinationsAdapter } from './adapters/pollinationsAdapter';
import { createGroqAdapter } from './adapters/groqAdapter';
import { createHuggingFaceAdapter } from './adapters/huggingfaceAdapter';
import { createTogetherAdapter } from './adapters/togetherAdapter';
import { createOpenRouterAdapter } from './adapters/openrouterAdapter';
import { createGeminiAdapter } from './adapters/geminiAdapter';
import { createLocalSafeAdapter } from './adapters/localSafeAdapter';
import type { Card, ProjectSettings } from '../types';

export interface SovereignLlmAdapterOptions {
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
  const adapters: LlmAdapter[] = [
    createPollinationsAdapter(options.pollinationsApiKey),
    createMlvocaAdapter(),
  ];

  // Add user key adapters if keys are provided
  if (options.groqApiKey) {
    adapters.push(createGroqAdapter(options.groqApiKey));
  }
  if (options.huggingfaceApiKey) {
    adapters.push(createHuggingFaceAdapter(options.huggingfaceApiKey));
  }
  if (options.togetherApiKey) {
    adapters.push(createTogetherAdapter(options.togetherApiKey));
  }
  if (options.openrouterApiKey) {
    adapters.push(createOpenRouterAdapter(options.openrouterApiKey));
  }
  if (options.geminiApiKey) {
    adapters.push(createGeminiAdapter(options.geminiApiKey));
  }

  // Add local safe adapter as fallback (priority 999)
  adapters.push(createLocalSafeAdapter({
    cards: options.cards,
    settings: options.settings,
  }));

  return adapters;
}