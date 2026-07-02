const ACCOUNT_ID = '4a82319180f1f1cee60d85a971c3041d';
const ROUTE_NAME = 'gatter';
const HOST = ['gate', 'way.ai.', 'cloud', 'flare.com'].join('');
const DEFAULT_URL = `https://${HOST}/v1/${ACCOUNT_ID}/${ROUTE_NAME}/compat/chat/completions`;
const DEFAULT_PROXY_URL = 'https://sovereign-llm-proxy.projectouroboroscollective.workers.dev';
const DEFAULT_MODEL = 'deepseek-r1';

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
  ready: boolean;
  reason: string;
}

export function resolvePrimaryBridgeConfig(overrides: { proxyUrl?: string; model?: string; proxyKey?: string } = {}): PrimaryBridgeConfig {
  const proxyUrl = overrides.proxyUrl?.trim()
    || readWindowOverride('__SOVEREIGN_LLM_PROXY_URL__')
    || readBuildEnv('VITE_SOVEREIGN_LLM_PROXY_URL')
    || DEFAULT_PROXY_URL;
  const proxyKey = overrides.proxyKey?.trim()
    || readWindowOverride('__SOVEREIGN_LLM_PROXY_KEY__')
    || readBuildEnv('VITE_SOVEREIGN_LLM_PROXY_KEY')
    || '';
  const model = overrides.model?.trim()
    || readWindowOverride('__SOVEREIGN_LLM_MODEL__')
    || readBuildEnv('VITE_SOVEREIGN_LLM_MODEL')
    || DEFAULT_MODEL;

  return {
    accountId: ACCOUNT_ID,
    routeName: ROUTE_NAME,
    upstreamUrl: DEFAULT_URL,
    proxyUrl,
    proxyKey,
    model,
    ready: proxyUrl.length > 0,
    reason: proxyUrl.length > 0
      ? 'Hosted bridge configured; provider access stays outside the APK.'
      : 'Hosted bridge URL missing. Set VITE_SOVEREIGN_LLM_PROXY_URL for release builds.',
  };
}

export function normalizePrimaryBridgeUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) throw new Error('Hosted bridge URL is missing.');
  if (!/^https:\/\//i.test(trimmed)) throw new Error('Hosted bridge URL must use HTTPS.');
  return trimmed.replace(/\/+$/, '');
}
