import { describe, expect, it } from 'vitest';
import {
  createSessionMemorySnapshot,
  formatSessionMemoryAge,
  parseSessionMemory,
  serializeSessionMemory,
} from './sovereignSessionMemory';

describe('sovereignSessionMemory', () => {
  it('serializes and parses valid snapshots', () => {
    const snapshot = createSessionMemorySnapshot({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      repoBranch: 'main',
      repoStatus: 'loaded',
      repoFiles: [{ path: 'README.md', type: 'blob' }],
      mission: 'README + Update History',
      sovereignSummary: 'summary',
      sovereignPreview: 'preview',
    });

    const parsed = parseSessionMemory(serializeSessionMemory(snapshot));
    expect(parsed?.repoUrl).toContain('Sovereign-Studio-ato');
    expect(parsed?.repoFiles).toHaveLength(1);
  });

  it('rejects invalid memory payloads', () => {
    expect(parseSessionMemory(null)).toBeNull();
    expect(parseSessionMemory('{bad json')).toBeNull();
    expect(parseSessionMemory(JSON.stringify({ version: 99 }))).toBeNull();
  });

  it('formats memory age', () => {
    const snapshot = createSessionMemorySnapshot({
      repoUrl: '',
      repoBranch: '',
      repoStatus: '',
      repoFiles: [],
      mission: '',
      sovereignSummary: '',
      sovereignPreview: '',
    });
    expect(formatSessionMemoryAge({ ...snapshot, savedAt: 0 }, 45_000)).toBe('45s ago');
    expect(formatSessionMemoryAge({ ...snapshot, savedAt: 0 }, 120_000)).toBe('2m ago');
  });
});
