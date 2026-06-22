import type { LlmAdapter } from './llmAdapter';
import { createMlvocaAdapter } from './adapters/mlvocaAdapter';
import { createPollinationsAdapter } from './adapters/pollinationsAdapter';
import { createGroqAdapter } from './adapters/groqAdapter';
import { createLocalSafeAdapter } from './adapters/localSafeAdapter';
import type { Card, ProjectSettings } from '../types';

export interface SovereignLlmAdapterOptions {
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
    createMlvocaAdapter(),
    createPollinationsAdapter(),
  ];

  // Add user key adapters if keys are provided
  if (options.groqApiKey) {
    adapters.push(createGroqAdapter(options.groqApiKey));
  }

  // Add local safe adapter as fallback
  adapters.push(createLocalSafeAdapter({
    cards: options.cards,
    settings: options.settings,
  }));

  return adapters;
}