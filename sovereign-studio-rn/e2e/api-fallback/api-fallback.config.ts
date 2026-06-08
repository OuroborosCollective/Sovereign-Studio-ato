/**
 * API Fallback Chain Tests
 * Tests the multi-provider AI fallback: MLVoca → P8lination → Gemini → Groq
 */

export interface APIProvider {
  name: string;
  endpoint: string;
  priority: number;
  timeout: number;
  retryCount: number;
}

export interface APIFallbackConfig {
  providers: APIProvider[];
  maxRetries: number;
  circuitBreakerThreshold: number;
  healthCheckInterval: number;
}

export const API_PROVIDERS: Record<string, APIProvider> = {
  mlvoca: {
    name: 'MLVoca',
    endpoint: process.env.MLVOCA_API_URL || 'https://api.mlvoca.com/v1',
    priority: 1,
    timeout: 10000,
    retryCount: 3,
  },
  p8lination: {
    name: 'P8lination',
    endpoint: process.env.P8LINATION_API_URL || 'https://api.p8lination.io/v1',
    priority: 2,
    timeout: 15000,
    retryCount: 2,
  },
  gemini: {
    name: 'Gemini',
    endpoint: process.env.GEMINI_API_URL || 'https://generativelanguage.googleapis.com/v1beta',
    priority: 3,
    timeout: 20000,
    retryCount: 2,
  },
  groq: {
    name: 'Groq',
    endpoint: process.env.GROQ_API_URL || 'https://api.groq.com/openai/v1',
    priority: 4,
    timeout: 15000,
    retryCount: 3,
  },
};

export const FALLBACK_CONFIG: APIFallbackConfig = {
  providers: [
    API_PROVIDERS.mlvoca,
    API_PROVIDERS.p8lination,
    API_PROVIDERS.gemini,
    API_PROVIDERS.groq,
  ],
  maxRetries: 5,
  circuitBreakerThreshold: 5,
  healthCheckInterval: 60000,
};

export const TEST_PROMPTS = [
  'Explain what Sovereign Studio does',
  'Generate a simple React Native component',
  'List the main features of the app',
  'What is the current version?',
  'How do I connect to GitHub?',
];

export const EXPECTED_RESPONSE_LATENCY = {
  mlvoca: 5000,
  p8lination: 10000,
  gemini: 15000,
  groq: 8000,
};

export interface TestResult {
  provider: string;
  success: boolean;
  latency: number;
  response: string | null;
  error: string | null;
  fallbackTriggered: boolean;
}

export interface FallbackTestReport {
  timestamp: string;
  totalTests: number;
  passed: number;
  failed: number;
  providerStats: Record<string, {
    attempts: number;
    successes: number;
    failures: number;
    avgLatency: number;
  }>;
  fallbackChain: string[];
}