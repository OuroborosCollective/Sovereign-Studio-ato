import { describe, expect, it } from 'vitest';
import { normalizePrimaryBridgeUrl, resolvePrimaryBridgeConfig } from './primaryBridgeConfig';

describe('primaryBridgeConfig', () => {
  it('uses the authenticated Sovereign backend as the only online route', () => {
    const config = resolvePrimaryBridgeConfig();
    expect(config.ready).toBe(true);
    expect(config.backendBaseUrl).toBe('https://sovereign-backend.arelorian.de');
    expect(config.routesUrl).toBe('https://sovereign-backend.arelorian.de/api/llm/routes');
    expect(config.chatUrl).toBe('https://sovereign-backend.arelorian.de/api/llm/chat');
    expect(config.accountId).toBe('');
    expect(config.proxyKey).toBe('');
    expect(config.model).toBe('');
  });

  it('allows release builds to override only the backend base URL', () => {
    const ready = resolvePrimaryBridgeConfig({ proxyUrl: 'https://backend.example/api/' });
    expect(ready.ready).toBe(true);
    expect(ready.backendBaseUrl).toBe('https://backend.example/api');
    expect(ready.chatUrl).toBe('https://backend.example/api/api/llm/chat');
  });

  it('normalizes HTTPS backend URLs and rejects non-HTTPS paths', () => {
    expect(normalizePrimaryBridgeUrl('https://backend.example/path///')).toBe('https://backend.example/path');
    expect(() => normalizePrimaryBridgeUrl('http://bad.example')).toThrow('HTTPS');
  });
});
