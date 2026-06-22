import { describe, it, expect, vi, beforeEach } from 'vitest';
import { buildSovereignMemoryContext } from './sovereignMemoryContext';
import { createExternalMemorySyncConfig } from './externalMemorySync';
import { createSolutionPatternStore } from './solutionPatternMemory';

describe('sovereignMemoryContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should build memory context from pattern memory when remote memory is disabled', async () => {
    const config = createExternalMemorySyncConfig();
    config.enabled = false;
    
    const store = createSolutionPatternStore();
    
    const result = await buildSovereignMemoryContext({
      mission: 'fix runtime issues',
      repoPaths: ['src/App.tsx'],
      config,
      solutionPatternStore: store,
    });

    expect(result.ok).toBe(false); // No patterns in empty store
    expect(result.source).toBe('none');
    expect(result.contextLines).toEqual([]);
  });

  it('should return empty context when no memory sources are available', async () => {
    const config = createExternalMemorySyncConfig();
    config.enabled = false;
    
    const result = await buildSovereignMemoryContext({
      mission: 'add feature',
      repoPaths: ['src/index.ts'],
      config,
      solutionPatternStore: null,
    });

    expect(result.ok).toBe(false);
    expect(result.source).toBe('none');
    expect(result.contextLines).toEqual([]);
  });
});