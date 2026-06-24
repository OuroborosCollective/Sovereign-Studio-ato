import { describe, expect, it } from 'vitest';
import { normalizePrimaryBridgeUrl, resolvePrimaryBridgeConfig } from './primaryBridgeConfig';

describe('primaryBridgeConfig', () => {
  it('keeps non-secret route metadata and default model', () => {
    const config = resolvePrimaryBridgeConfig();
    expect(config.accountId).toBe('4a82319180f1f1cee60d85a971c3041d');
    expect(config.routeName).toBe('gatter');
    expect(config.upstreamUrl).toContain('/gatter/compat/chat/completions');
    expect(config.model).toBe('cerebras/zai-glm-4.7');
  });

  it('marks runtime bridge ready only when a hosted proxy URL is present', () => {
    const missing = resolvePrimaryBridgeConfig({ proxyUrl: '' });
    expect(missing.ready).toBe(false);

    const ready = resolvePrimaryBridgeConfig({ proxyUrl: 'https://sovereign-worker.example/v1/chat/completions' });
    expect(ready.ready).toBe(true);
  });

  it('normalizes HTTPS proxy URLs and rejects non-HTTPS paths', () => {
    expect(normalizePrimaryBridgeUrl('https://sovereign-worker.example/path///')).toBe('https://sovereign-worker.example/path');
    expect(() => normalizePrimaryBridgeUrl('http://bad.example')).toThrow('HTTPS');
  });
});
