const DEFAULT_BACKEND_URL = 'https://sovereign-backend.arelorian.de';

type ImportMetaWithEnv = ImportMeta & { env?: Record<string, string | undefined> };

function readBuildEnv(name: string): string | undefined {
  try {
    const value = (import.meta as ImportMetaWithEnv).env?.[name]?.trim();
    return value && !value.startsWith('REPLACE_WITH_') ? value : undefined;
  } catch {
    return undefined;
  }
}

function readWindowOverride(name: string): string | undefined {
  if (typeof window === 'undefined') return undefined;
  const value = (window as unknown as Record<string, unknown>)[name];
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

export interface PrimaryBridgeConfig {
  accountId: string;
  routeName: string;
  upstreamUrl: string;
  proxyUrl: string;
  proxyKey: string;
  model: string;
  backendBaseUrl: string;
  routesUrl: string;
  chatUrl: string;
  ready: boolean;
  reason: string;
}

export function resolvePrimaryBridgeConfig(overrides: { proxyUrl?: string; model?: string; proxyKey?: string } = {}): PrimaryBridgeConfig {
  const backendBaseUrl = normalizePrimaryBridgeUrl(
    overrides.proxyUrl?.trim()
      || readWindowOverride('__SOVEREIGN_ADMIN_API_BASE__')
      || readBuildEnv('VITE_ADMIN_API_BASE')
      || DEFAULT_BACKEND_URL,
  );

  return {
    accountId: '',
    routeName: 'private-litellm',
    upstreamUrl: `${backendBaseUrl}/api/llm/chat`,
    proxyUrl: backendBaseUrl,
    proxyKey: '',
    model: overrides.model?.trim() || '',
    backendBaseUrl,
    routesUrl: `${backendBaseUrl}/api/llm/routes`,
    chatUrl: `${backendBaseUrl}/api/llm/chat`,
    ready: true,
    reason: 'Online model traffic is routed through the authenticated Sovereign Backend: paid through direct OpenRouter and free through direct FreeLLM.',
  };
}

export function normalizePrimaryBridgeUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) throw new Error('Sovereign backend URL is missing.');
  if (!/^https:\/\//i.test(trimmed)) throw new Error('Sovereign backend URL must use HTTPS.');
  return trimmed.replace(/\/+$/, '');
}
