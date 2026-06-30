import { describe, expect, it } from 'vitest';
import { maskSecrets } from './crypto';

describe('maskSecrets', () => {
  it('masks GitHub Classic PATs', () => {
    const secret = 'ghp_1234567890abcdefghijklmnopqrstuvwx';
    const text = `Error: Failed to use token ${secret}`;
    expect(maskSecrets(text)).toBe('Error: Failed to use token ghp_****');
  });

  it('masks GitHub Fine-grained PATs', () => {
    const secret = 'github_pat_11AABCXYZ0123456789012_abcdefghijklmnopqrstuvwxyz012345678901234567890123456789012345678';
    const text = `Could not authenticate with ${secret}`;
    expect(maskSecrets(text)).toBe('Could not authenticate with github_pat_****');
  });

  it('masks GitHub token variants', () => {
    expect(maskSecrets('gho_1234567890abcdefghijklmnopqrstuvwx')).toBe('gho_****');
    expect(maskSecrets('ghu_1234567890abcdefghijklmnopqrstuvwx')).toBe('ghu_****');
    expect(maskSecrets('ghs_1234567890abcdefghijklmnopqrstuvwx')).toBe('ghs_****');
    expect(maskSecrets('ghr_1234567890abcdefghijklmnopqrstuvwx')).toBe('ghr_****');
  });

  it('masks Google API keys', () => {
    const secret = 'AIzaSyA-1234567890_abcdefghijklmnopqrst';
    const text = `API key ${secret} is invalid`;
    expect(maskSecrets(text)).toBe('API key AIza**** is invalid');
    expect(maskSecrets('AIza_anything_long_enough_abcdefghijklmnopqrstuv')).toBe('AIza****');
  });

  it('masks OpenRouter style keys', () => {
    const secret = 'sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789';
    expect(maskSecrets(`Using ${secret}`)).toBe('Using sk-or-v1-****');
  });

  it('masks HuggingFace, Together AI and Pollinations AI keys', () => {
    expect(maskSecrets('hf_abcdefghijklmnopqrstuvwxyz')).toBe('hf_****');
    expect(maskSecrets('together_abcdefghijklmnopqrstuvwxyz')).toBe('together_****');
    expect(maskSecrets('pollinations_abcdefghijklmnopqrstuvwxyz')).toBe('pollinations_****');
  });

  it('masks Bearer tokens', () => {
    const secret = 'Bearer ya29.a0AfB_ByD_E-fGhIjKlMnOpQrStUvWxYz1234567890';
    const text = `Authorization: ${secret}`;
    expect(maskSecrets(text)).toBe('Authorization: Bearer ****');
  });

  it('masks AI provider style keys', () => {
    const secret = 'sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmnopqrstuvwxyz01';
    expect(maskSecrets(`Using ${secret}`)).toBe('Using sk-****');
  });

  it('masks Groq style keys', () => {
    const secret = 'gsk_abcdefghijklmnopqrstuvwxyz0123456789';
    expect(maskSecrets(`Failed with ${secret}`)).toBe('Failed with gsk_****');
  });

  it('masks OpenAI Project keys', () => {
    const secret = 'sk-proj-abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmnopqrstuvwxyz01';
    expect(maskSecrets(`Using ${secret}`)).toBe('Using sk-proj-****');
  });

  it('masks long OpenAI Project keys without leaking suffixes', () => {
    const credentialBody = `${'a'.repeat(140)}_${'Z'.repeat(40)}-tail`;
    const secret = `sk-proj-${credentialBody}`;
    const masked = maskSecrets(`Using ${secret}; next field`);

    expect(masked).toBe('Using sk-proj-****; next field');
    expect(masked).not.toContain('tail');
    expect(masked).not.toContain('ZZZZ');
  });

  it('masks label-based credentials', () => {
    expect(maskSecrets('password: my-secret-password')).toBe('password: ****');
    expect(maskSecrets('passwd=some-pass')).toBe('passwd=****');
    expect(maskSecrets('token=ghp_12345')).toBe('token=****');
    expect(maskSecrets('api_key=abcdefghijklmnopqrstuvwxyz1234567890')).toBe('api_key=****');
    expect(maskSecrets('access-token=abcdefghijklmnopqrstuvwxyz1234567890')).toBe('access-token=****');
    expect(maskSecrets('secret: somevalue')).toBe('secret: ****');
  });

  it('masks quoted label-based credentials and base64 characters', () => {
    expect(maskSecrets('"password": "my-secret-password"')).toBe('"password": ****');
    expect(maskSecrets("'api_key': 'abc123+/~='")).toBe("'api_key': ****");
    expect(maskSecrets('token: value_with_@#$%^&*')).toBe('token: ****');
  });

  it('masks multiple secrets in one string', () => {
    const text = 'Keys: ghp_1234567890abcdefghijklmnopqrstuvwx and AIzaSyA-1234567890_abcdefghijklmnopqrst';
    expect(maskSecrets(text)).toBe('Keys: ghp_**** and AIza****');
  });

  it('leaves normal text untouched', () => {
    const text = 'This is a normal error message with no secrets.';
    expect(maskSecrets(text)).toBe(text);
  });

  it('handles empty or null input', () => {
    expect(maskSecrets('')).toBe('');
    // @ts-ignore
    expect(maskSecrets(null)).toBe(null);
  });
});
