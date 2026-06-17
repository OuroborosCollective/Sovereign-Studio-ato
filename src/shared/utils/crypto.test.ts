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

  it('masks Google API keys', () => {
    const secret = 'AIzaSyA-1234567890_abcdefghijklmnopqrst';
    const text = `API key ${secret} is invalid`;
    expect(maskSecrets(text)).toBe('API key AIzaSy**** is invalid');
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

  it('masks label-based credentials', () => {
    expect(maskSecrets('password: my-secret-password')).toBe('password: ****');
    expect(maskSecrets('token=ghp_12345')).toBe('token: ****');
    expect(maskSecrets('secret: somevalue')).toBe('secret: ****');
  });

  it('masks multiple secrets in one string', () => {
    const text = 'Keys: ghp_1234567890abcdefghijklmnopqrstuvwx and AIzaSyA-1234567890_abcdefghijklmnopqrst';
    expect(maskSecrets(text)).toBe('Keys: ghp_**** and AIzaSy****');
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
